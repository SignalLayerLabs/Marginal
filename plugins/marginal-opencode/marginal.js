// marginal-opencode-plugin
//
// Local-only MARGINAL Shadow Mode observation for OpenCode-compatible CLIs.
//
// The plugin owns one bridge child process and speaks newline-delimited JSON to it.
// It never blocks a tool call, never rewrites arguments, and never throws into
// OpenCode: if the bridge is missing or fails, every hook becomes a no-op.
//
// Tool output never leaves this process. The plugin sends a digest of the result
// plus an allowlist of outcome signals, so MARGINAL never sees file content or
// command output, not even in memory.

import { createHash } from "node:crypto"
import { spawn } from "node:child_process"

const ENGINE_TARGET = process.env.MARGINAL_TARGET || "opencode"
const PYTHON = process.env.MARGINAL_PYTHON || "python3"
const REQUEST_TIMEOUT_MS = Number(process.env.MARGINAL_TIMEOUT_MS || 5000)
const OUTCOME_SIGNAL_KEYS = ["exit", "exit_code", "exitCode", "success", "status"]

const digest = (value) => {
  try {
    return createHash("sha256").update(JSON.stringify(value ?? null)).digest("hex")
  } catch {
    return ""
  }
}

// Only signals that distinguish success from a completed failure are forwarded.
// Everything else in metadata is left behind.
const outcomeSignals = (metadata) => {
  const signals = {}
  if (metadata && typeof metadata === "object") {
    for (const key of OUTCOME_SIGNAL_KEYS) {
      const value = metadata[key]
      if (typeof value === "number" || typeof value === "boolean" || typeof value === "string") {
        signals[key] = value
      }
    }
  }
  return signals
}

class Bridge {
  constructor(dataRoot) {
    this.pending = []
    this.buffer = ""
    this.available = false
    const args = ["-m", "marginal.integrations.opencode.bridge", "--target", ENGINE_TARGET]
    if (dataRoot) args.push("--data-root", dataRoot)
    const env = { ...process.env }
    if (process.env.MARGINAL_RUNTIME) {
      env.PYTHONPATH = env.PYTHONPATH
        ? `${process.env.MARGINAL_RUNTIME}:${env.PYTHONPATH}`
        : process.env.MARGINAL_RUNTIME
    }
    try {
      this.child = spawn(PYTHON, args, { stdio: ["pipe", "pipe", "ignore"], env })
    } catch {
      this.child = null
      return
    }
    this.child.on("error", () => this.fail())
    this.child.on("exit", () => this.fail())
    this.child.stdout.setEncoding("utf8")
    this.child.stdout.on("data", (chunk) => this.receive(chunk))
    this.available = true
  }

  fail() {
    this.available = false
    while (this.pending.length) this.pending.shift().resolve(null)
  }

  receive(chunk) {
    this.buffer += chunk
    let newline = this.buffer.indexOf("\n")
    while (newline >= 0) {
      const line = this.buffer.slice(0, newline)
      this.buffer = this.buffer.slice(newline + 1)
      const waiter = this.pending.shift()
      if (waiter) {
        let parsed = null
        try {
          parsed = JSON.parse(line)
        } catch {
          parsed = null
        }
        waiter.resolve(parsed)
      }
      newline = this.buffer.indexOf("\n")
    }
  }

  request(operation, payload) {
    if (!this.available || !this.child || !this.child.stdin.writable) return Promise.resolve(null)
    return new Promise((resolve) => {
      const waiter = { resolve }
      this.pending.push(waiter)
      const timer = setTimeout(() => {
        const index = this.pending.indexOf(waiter)
        if (index >= 0) this.pending.splice(index, 1)
        resolve(null)
      }, REQUEST_TIMEOUT_MS)
      waiter.resolve = (value) => {
        clearTimeout(timer)
        resolve(value)
      }
      try {
        this.child.stdin.write(JSON.stringify({ operation, payload }) + "\n")
      } catch {
        this.fail()
        resolve(null)
      }
    })
  }

  dispose() {
    if (!this.child) return
    try {
      this.child.stdin.end()
    } catch {
      // the bridge is already gone
    }
    this.available = false
  }
}

export const MarginalPlugin = async ({ directory, worktree }) => {
  const workspace = worktree || directory || process.cwd()
  const bridge = new Bridge(process.env.MARGINAL_DATA_ROOT)
  if (!bridge.available) return {}
  const started = new Set()

  const ensureSession = async (sessionID) => {
    if (started.has(sessionID)) return
    started.add(sessionID)
    await bridge.request("session_start", { session_id: sessionID, workspace })
  }

  return {
    event: async ({ event }) => {
      if (!event || typeof event.type !== "string") return
      const sessionID = event.properties?.sessionID
      if (!sessionID) return
      if (event.type === "session.created") {
        await ensureSession(sessionID)
      } else if (event.type === "session.deleted") {
        started.delete(sessionID)
        await bridge.request("session_end", { session_id: sessionID, workspace })
      }
    },

    "tool.execute.before": async (input, output) => {
      await ensureSession(input.sessionID)
      await bridge.request("tool_start", {
        session_id: input.sessionID,
        call_id: input.callID,
        tool_name: input.tool,
        arguments: output?.args ?? {},
        workspace,
      })
    },

    "tool.execute.after": async (input, output) => {
      await bridge.request("tool_end", {
        session_id: input.sessionID,
        call_id: input.callID,
        tool_name: input.tool,
        arguments: input.args ?? {},
        evidence_digest: digest({ title: output?.title, output: output?.output, metadata: output?.metadata }),
        signals: outcomeSignals(output?.metadata),
      })
    },

    dispose: async () => {
      for (const sessionID of started) {
        await bridge.request("session_end", { session_id: sessionID, workspace })
      }
      bridge.dispose()
    },
  }
}

export default MarginalPlugin
