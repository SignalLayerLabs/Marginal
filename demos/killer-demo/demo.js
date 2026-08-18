(() => {
  "use strict";

  const dataNode = document.querySelector("#demo-data");
  if (!dataNode) return;
  const data = JSON.parse(dataNode.textContent || "{}");
  const ticks = Array.isArray(data.ticks) ? data.ticks : [];

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const number = new Intl.NumberFormat("en-US");
  const money = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  });

  const state = {
    cursor: -1,
    playing: false,
    speed: 1,
    timer: null,
  };

  const dom = {
    run: $('[data-action="run"]'),
    pause: $('[data-action="pause"]'),
    step: $('[data-action="step"]'),
    reset: $('[data-action="reset"]'),
    speed: $("#speed"),
    progress: $("#race-progress"),
    tick: $("#tick-counter"),
    waste: $("#waste-fill"),
    result: $("#result-reveal"),
    baselineTerminal: $("#terminal-baseline"),
    marginalTerminal: $("#terminal-marginal"),
    baselineState: $("#state-baseline"),
    marginalState: $("#state-marginal"),
    decision: $("#decision-live"),
    reason: $("#decision-reason"),
    score: $("#decision-score"),
    gain: $("#decision-gain"),
    currentCandidate: $("#current-candidate"),
    stages: $$('[data-stage]'),
    baselineLane: $('[data-lane="baseline"]'),
    marginalLane: $('[data-lane="marginal"]'),
  };

  function metric(lane, name) {
    return $(`[data-metric="${lane}-${name}"]`);
  }

  function setMetric(lane, cumulative) {
    metric(lane, "calls").textContent = number.format(cumulative.calls || 0);
    metric(lane, "tokens").textContent = number.format(cumulative.tokens || 0);
    metric(lane, "usd").textContent = `$${money.format(cumulative.usd || 0)}`;
    const seconds = (cumulative.latency_ms || 0) / 1000;
    metric(lane, "latency").textContent = `${seconds.toFixed(2)}s`;
  }

  function setWorkspace(node, value) {
    node.textContent = value;
    node.dataset.state = value;
  }

  function appendLine(terminal, kind, text) {
    const line = document.createElement("p");
    line.className = `term-line ${kind}`;
    line.textContent = text;
    terminal.appendChild(line);
    terminal.scrollTop = terminal.scrollHeight;
  }

  function pulse(node) {
    if (!node) return;
    node.classList.remove("flash");
    void node.offsetWidth;
    node.classList.add("flash");
  }

  function updateStages(tick) {
    dom.stages.forEach((node, index) => {
      const stageIndex = index + 1;
      node.classList.toggle("active", stageIndex === tick.stage_index);
      node.classList.toggle("done", stageIndex < tick.stage_index);
    });
  }

  function updateWaste(tick) {
    const base = tick.baseline.cumulative.tokens || 0;
    const governed = tick.marginal.cumulative.tokens || 0;
    const avoided = Math.max(0, base - governed);
    const finalBase = data.final.baseline.tokens || 1;
    const percent = Math.min(100, (avoided / finalBase) * 100);
    if (window.matchMedia("(max-width: 980px)").matches) {
      dom.waste.style.height = "100%";
      dom.waste.style.width = `${percent}%`;
    } else {
      dom.waste.style.width = "100%";
      dom.waste.style.height = `${percent}%`;
    }
  }

  function renderDecision(tick) {
    const decision = tick.marginal.decision;
    dom.decision.textContent = decision;
    dom.decision.classList.toggle("fund", tick.marginal.funded);
    dom.decision.classList.toggle("reject", !tick.marginal.funded);
    dom.reason.textContent = tick.marginal.reason;
    dom.score.textContent = `score ${tick.marginal.score.toFixed(3)}`;
    dom.gain.textContent = `gain ${tick.marginal.expected_gain.toFixed(3)}`;
  }

  function revealResult() {
    if (dom.result.classList.contains("show")) return;
    dom.result.classList.add("show");
    dom.stages.forEach((node) => {
      node.classList.remove("active");
      node.classList.add("done");
    });
    appendLine(dom.baselineTerminal, "pass", "VERIFIER PASS");
    appendLine(dom.marginalTerminal, "pass", "VERIFIER PASS");
    dom.run.disabled = false;
    dom.pause.disabled = true;
  }

  function advanceRace() {
    if (state.cursor >= ticks.length - 1) {
      state.playing = false;
      revealResult();
      return false;
    }

    state.cursor += 1;
    const tick = ticks[state.cursor];
    const position = state.cursor + 1;
    const progress = (position / ticks.length) * 100;
    dom.progress.style.width = `${progress}%`;
    dom.tick.textContent = `${position}/${ticks.length}`;
    dom.currentCandidate.textContent = `${tick.stage} · ${tick.candidate.name}`;
    updateStages(tick);

    appendLine(dom.baselineTerminal, "command", `> ${tick.candidate.name}`);
    appendLine(dom.baselineTerminal, "execute", tick.baseline.output);
    setMetric("baseline", tick.baseline.cumulative);
    setWorkspace(dom.baselineState, tick.baseline.workspace);
    pulse(dom.baselineLane);

    renderDecision(tick);
    if (tick.marginal.funded) {
      appendLine(dom.marginalTerminal, "command", `> ${tick.candidate.name}`);
      appendLine(dom.marginalTerminal, "fund", tick.marginal.output);
    } else {
      appendLine(dom.marginalTerminal, "reject", tick.candidate.name);
      appendLine(dom.marginalTerminal, "output", tick.marginal.reason);
    }
    setMetric("marginal", tick.marginal.cumulative);
    setWorkspace(dom.marginalState, tick.marginal.workspace);
    updateWaste(tick);
    pulse(dom.marginalLane);

    if (state.cursor === ticks.length - 1) revealResult();
    return true;
  }

  function delayForCurrentTick() {
    const tick = ticks[Math.max(0, state.cursor)];
    const declared = tick ? tick.candidate.latency_ms : 700;
    const accelerated = Math.max(600, Math.min(1400, declared * 0.22));
    return accelerated / state.speed;
  }

  function scheduleNext() {
    window.clearTimeout(state.timer);
    if (!state.playing) return;
    state.timer = window.setTimeout(() => {
      const advanced = advanceRace();
      if (advanced && state.playing && state.cursor < ticks.length - 1) {
        scheduleNext();
      } else {
        state.playing = false;
      }
    }, delayForCurrentTick());
  }

  function playRace() {
    if (state.cursor >= ticks.length - 1) resetRace();
    state.playing = true;
    dom.run.disabled = true;
    dom.pause.disabled = false;
    if (state.cursor < 0) advanceRace();
    scheduleNext();
  }

  function pauseRace() {
    state.playing = false;
    window.clearTimeout(state.timer);
    dom.run.disabled = false;
    dom.pause.disabled = true;
  }

  function resetTerminal(terminal, label) {
    terminal.replaceChildren();
    appendLine(terminal, "command", `$ ${label}`);
    appendLine(terminal, "output", "initial verifier: FAIL");
    appendLine(terminal, "output", "ready — same task, same workspace snapshot");
  }

  function resetRace() {
    pauseRace();
    state.cursor = -1;
    dom.progress.style.width = "0%";
    dom.tick.textContent = `0/${ticks.length}`;
    dom.currentCandidate.textContent = "Ready";
    dom.result.classList.remove("show");
    dom.waste.style.width = "0";
    dom.waste.style.height = "0";
    setMetric("baseline", {});
    setMetric("marginal", {});
    setWorkspace(dom.baselineState, "FAIL");
    setWorkspace(dom.marginalState, "FAIL");
    dom.decision.textContent = "WAITING";
    dom.decision.className = "decision";
    dom.reason.textContent = "Press RUN. MARGINAL will score each candidate before spend.";
    dom.score.textContent = "score —";
    dom.gain.textContent = "gain —";
    dom.stages.forEach((node) => node.classList.remove("active", "done"));
    resetTerminal(dom.baselineTerminal, "agent --governor off");
    resetTerminal(dom.marginalTerminal, "agent --governor marginal");
    dom.run.disabled = false;
    dom.pause.disabled = true;
  }

  dom.run?.addEventListener("click", playRace);
  dom.pause?.addEventListener("click", pauseRace);
  dom.step?.addEventListener("click", () => {
    pauseRace();
    advanceRace();
  });
  dom.reset?.addEventListener("click", resetRace);
  dom.speed?.addEventListener("change", () => {
    state.speed = Number(dom.speed.value) || 1;
    if (state.playing) scheduleNext();
  });

  document.addEventListener("keydown", (event) => {
    const tag = document.activeElement?.tagName || "";
    if (["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(tag)) return;
    if (event.code === "Space") {
      event.preventDefault();
      state.playing ? pauseRace() : playRace();
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      pauseRace();
      advanceRace();
    }
    if (event.key.toLowerCase() === "r") resetRace();
  });

  resetRace();
})();
