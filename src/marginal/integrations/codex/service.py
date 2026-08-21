"""Per-session Codex governance service and fail-open hook entry point."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from marginal import BudgetLimits, Treasury
from marginal.commons._storage import atomic_replace_at, locked_directory, read_bounded_at
from marginal.commons.cache import CommonsCache, CommonsPrior
from marginal.commons.client import CommonsClient, CommonsClientProtocol
from marginal.commons.config import CommonsConfig, CommonsMode, load_commons_config
from marginal.commons.evidence import compile_verified_evidence
from marginal.commons.identity import CanonicalModelIdentity, resolve_canonical_model
from marginal.commons.outbox import CommonsOutbox
from marginal.commons.sync import CommonsSyncResult, synchronize_commons
from marginal.protocol import AgentCapabilities
from marginal.reason_codes import ReasonCode
from marginal.runtime import UniversalRuntime

from .autopilot import AutopilotController
from .events import (
    PostToolUseEvent,
    PreToolUseEvent,
    SessionEvent,
    UserPromptSubmitEvent,
    build_pre_tool_output,
    parse_hook_event,
)
from .evidence import EvidenceStore, summarize_verified_evidence
from .identity import current_promotion_identity, repository_identity_hash
from .installer import autopilot_consent_configured
from .promotion import PromotionIdentity, demote_enforcement, enforcement_is_active
from .runtime import CodexSessionRuntime
from .transport import ConnectionInfo, SessionServer, connection_filename, request_session

_SERVERS: dict[tuple[Path, str], tuple[SessionServer, CodexSessionRuntime]] = {}
_COMMONS_PACK_ORIGIN = "https://marginal-commons.pages.dev"
_COMMONS_INGRESS_ORIGIN = "https://marginal-ingress.signallayerlabs.workers.dev"


@dataclass(slots=True)
class _CommonsSession:
    config: CommonsConfig
    identity: CanonicalModelIdentity | None = None
    cache: CommonsCache | None = None
    outbox: CommonsOutbox | None = None
    client: CommonsClientProtocol | None = None
    priors: tuple[CommonsPrior, ...] = ()
    attribution_valid: bool = True


@dataclass(frozen=True, slots=True)
class HookResult:
    exit_code: int
    output: dict[str, Any] | None = None
    warning_code: str = ""


def _commons_client() -> CommonsClientProtocol:
    return CommonsClient(
        pack_origin=_COMMONS_PACK_ORIGIN,
        ingress_origin=_COMMONS_INGRESS_ORIGIN,
    )


def _commons_status_path(data_root: Path) -> Path:
    return data_root / "commons" / "status.json"


def _safe_queue_count(outbox: CommonsOutbox | None) -> int:
    if outbox is None:
        return 0
    try:
        return len(outbox.pending(limit=100).entries)
    except Exception:
        return 0


def _write_commons_status(
    data_root: Path,
    commons: _CommonsSession,
    result: CommonsSyncResult | None,
) -> None:
    path = _commons_status_path(data_root)
    payload = {
        "schema_version": "1.0",
        "mode": commons.config.mode.value,
        "endpoint": _COMMONS_INGRESS_ORIGIN,
        "model_namespace": commons.identity.namespace if commons.identity is not None else None,
        "sharing_allowed": (
            commons.config.mode is CommonsMode.CONTRIBUTOR and commons.identity is not None
        ),
        "safe_queue_count": _safe_queue_count(commons.outbox),
        "last_sync_status": (
            "not_attempted"
            if result is None
            else "ok"
            if not result.failures
            else "+".join(failure.value for failure in result.failures)
        ),
        "cache_revision": commons.cache.revision if commons.cache is not None else None,
    }
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        path.parent.chmod(0o700)
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor, name = tempfile.mkstemp(prefix=".status-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, encoded)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        if os.name == "posix":
            path.chmod(0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _start_commons(
    data_root: Path, *, model: str, evidence_store: EvidenceStore
) -> _CommonsSession:
    try:
        config = load_commons_config(data_root)
    except Exception:
        config = CommonsConfig()
    identity = resolve_canonical_model(provider="openai", model=model)
    commons = _CommonsSession(config=config, identity=identity)
    if config.mode is CommonsMode.LOCAL_ONLY or identity is None:
        with suppress(Exception):
            _write_commons_status(data_root, commons, None)
        return commons
    try:
        commons.cache = CommonsCache(
            data_root,
            model_namespace=identity.namespace,
        )
        commons.outbox = CommonsOutbox(data_root)
        commons.client = _commons_client()
        _recover_export_cursor(evidence_store, identity, commons.outbox)
        result = synchronize_commons(
            config,
            cache=commons.cache,
            outbox=commons.outbox,
            client=commons.client,
        )
        commons.priors = commons.cache.load_prior()
        _write_commons_status(data_root, commons, result)
    except Exception:
        with suppress(Exception):
            _write_commons_status(data_root, commons, None)
    return commons


def _finalize_local_session(
    runtime: CodexSessionRuntime,
    evidence_store: EvidenceStore,
    *,
    session_hash: str,
) -> bool:
    runtime.close()
    report = evidence_store.verified_governance_root()
    try:
        checkpoint = evidence_store.read_checkpoint()
    except (OSError, ValueError, json.JSONDecodeError):
        checkpoint = None
    if (
        report.valid
        and checkpoint is not None
        and checkpoint.get("event") == "session_finalized"
        and checkpoint.get("session_hash") == session_hash
        and checkpoint.get("ledger_root") == report.root_hash
        and checkpoint.get("ledger_records") == report.records
    ):
        return False
    evidence_store.append(
        {"schema_version": 1, "event": "session_end", "session_hash": session_hash}
    )
    finalized = evidence_store.verified_governance_root()
    if not finalized.valid:
        return False
    evidence_store.write_checkpoint(
        {
            "schema_version": 1,
            "event": "session_finalized",
            "session_hash": session_hash,
            "ledger_root": finalized.root_hash,
            "ledger_records": finalized.records,
        }
    )
    return True


def _end_commons(
    data_root: Path,
    commons: _CommonsSession,
    evidence_store: EvidenceStore,
) -> None:
    if (
        commons.config.mode is not CommonsMode.CONTRIBUTOR
        or commons.identity is None
        or not commons.attribution_valid
        or commons.cache is None
        or commons.outbox is None
        or commons.client is None
    ):
        return
    cursor = _read_export_cursor(evidence_store, commons.identity)
    if cursor is None:
        return
    report = evidence_store.verified_governance_root()
    if not report.valid or report.root_hash is None or report.records <= cursor[0]:
        return
    evidence = compile_verified_evidence(
        evidence_store,
        model_identity=commons.identity,
        after_records=cursor[0],
        through_records=report.records,
    )
    receipt_payload = (
        f"{commons.identity.namespace}:{cursor[0]}:{report.records}:{report.root_hash}"
    )
    receipt = (
        f"v1.{cursor[0]}.{report.records}.{report.root_hash}."
        f"{hashlib.sha256(receipt_payload.encode()).hexdigest()}"
    )
    if evidence is not None:
        queued = commons.outbox.enqueue(batch=evidence, export_receipt=receipt)
        if queued is None:
            return
    _write_export_cursor(evidence_store, commons.identity, report.records, report.root_hash)
    result = synchronize_commons(
        commons.config,
        cache=commons.cache,
        outbox=commons.outbox,
        client=commons.client,
    )
    _write_commons_status(data_root, commons, result)


def _export_cursor_name(identity: CanonicalModelIdentity) -> str:
    return f"{identity.model}.json"


def _read_export_cursor(
    store: EvidenceStore, identity: CanonicalModelIdentity
) -> tuple[int, str] | None:
    directory_path = store.root / "commons-export"
    try:
        with locked_directory(directory_path, create=False, lock_name=".export.lock") as directory:
            raw, _ = read_bounded_at(
                directory,
                _export_cursor_name(identity),
                maximum_bytes=4096,
                label="Commons export cursor",
            )
    except FileNotFoundError:
        return (0, "")
    except OSError:
        return None
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "model_namespace", "ledger_records", "ledger_root"}
        or payload.get("schema_version") != 1
        or payload.get("model_namespace") != identity.namespace
        or isinstance(payload.get("ledger_records"), bool)
        or not isinstance(payload.get("ledger_records"), int)
        or not isinstance(payload.get("ledger_root"), str)
    ):
        return None
    records = payload["ledger_records"]
    root = payload["ledger_root"]
    if records < 0 or (
        records and not store.verifies_governance_prefix(root_hash=root, records=records)
    ):
        return None
    return records, root


def _write_export_cursor(
    store: EvidenceStore,
    identity: CanonicalModelIdentity,
    records: int,
    root: str,
) -> None:
    payload = {
        "schema_version": 1,
        "model_namespace": identity.namespace,
        "ledger_records": records,
        "ledger_root": root,
    }
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with locked_directory(
        store.root / "commons-export", create=True, lock_name=".export.lock"
    ) as directory:
        atomic_replace_at(
            directory,
            _export_cursor_name(identity),
            encoded,
            temporary_prefix=".export-cursor-",
            label="Commons export cursor",
        )


def _recover_export_cursor(
    store: EvidenceStore,
    identity: CanonicalModelIdentity,
    outbox: CommonsOutbox,
) -> None:
    cursor = _read_export_cursor(store, identity)
    if cursor is None:
        return
    entries = sorted(
        outbox.pending(limit=100).entries,
        key=lambda entry: entry.export_receipt or "",
    )
    advanced = True
    while advanced:
        advanced = False
        for entry in entries:
            receipt = entry.export_receipt
            if receipt is None or entry.model_namespace != identity.namespace:
                continue
            parts = receipt.split(".")
            if len(parts) != 5 or parts[0] != "v1":
                continue
            try:
                after, through = int(parts[1]), int(parts[2])
            except ValueError:
                continue
            root, digest = parts[3], parts[4]
            payload = f"{identity.namespace}:{after}:{through}:{root}"
            if (
                after != cursor[0]
                or through <= after
                or hashlib.sha256(payload.encode()).hexdigest() != digest
                or not store.verifies_governance_prefix(root_hash=root, records=through)
            ):
                continue
            _write_export_cursor(store, identity, through, root)
            cursor = (through, root)
            advanced = True
            break


def _connection_path(data_root: Path, session_id: str) -> Path:
    return data_root / "sessions" / connection_filename(session_id)


def _handler(
    runtime: CodexSessionRuntime,
    *,
    evidence_store: EvidenceStore,
    session_hash: str,
    data_root: Path,
    identity: PromotionIdentity,
    commons: _CommonsSession,
    shutdown_event: threading.Event | None = None,
) -> Any:
    def handle(operation: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if operation == "status":
            return {
                **runtime.summary(),
                "repository_hash": identity.repository_hash,
                "commons_prior_count": len(commons.priors),
            }
        if operation == "close":
            finalized = _finalize_local_session(runtime, evidence_store, session_hash=session_hash)
            if finalized:
                with suppress(Exception):
                    _end_commons(data_root, commons, evidence_store)
            if shutdown_event is not None:
                threading.Timer(0.05, shutdown_event.set).start()
            return runtime.summary()
        event = parse_hook_event(payload)
        if getattr(event, "model", None) != (
            commons.identity.model if commons.identity is not None else None
        ):
            commons.attribution_valid = False
        if operation == "prompt" and isinstance(event, UserPromptSubmitEvent):
            runtime.user_prompt_submit(event)
            return None
        if operation == "pre" and isinstance(event, PreToolUseEvent):
            started = time.perf_counter_ns()
            decision = runtime.pre_tool_use(event)
            latency_ms = (time.perf_counter_ns() - started) / 1_000_000
            action_evidence = runtime.last_action_evidence or {}
            signal = runtime.last_no_progress_signal
            evidence_store.append(
                {
                    "schema_version": 1,
                    "event": "decision",
                    "session_hash": session_hash,
                    **action_evidence,
                    **(
                        {
                            "model_namespace": commons.identity.namespace,
                            "cost_bucket": "unknown",
                            "gain_bucket": "unknown",
                            "recommendation": "allow" if decision.allowed else "deny",
                            "applied_decision": "allow" if decision.allowed else "deny",
                        }
                        if commons.identity is not None and commons.attribution_valid
                        else {}
                    ),
                    "reason_code": decision.reason_code,
                    "latency_ms": latency_ms,
                    "covered": decision.reason_code != ReasonCode.CONTROL_PLANE_BYPASS.value,
                    "coverable": decision.reason_code != ReasonCode.CONTROL_PLANE_BYPASS.value,
                    "recommended_stop": bool(signal and signal.should_recommend_stop),
                    "reviewed": False,
                    "false_stop": False,
                    "pending": (
                        decision.allowed
                        and decision.reason_code != ReasonCode.CONTROL_PLANE_BYPASS.value
                    ),
                }
            )
            return build_pre_tool_output(
                allowed=decision.allowed,
                reason=decision.reason,
                reason_code=decision.reason_code,
            )
        if operation == "post" and isinstance(event, PostToolUseEvent):
            action_evidence = runtime.action_evidence(event.tool_use_id) or {}
            outcome = runtime.post_tool_use(event)
            evidence_store.append(
                {
                    "schema_version": 1,
                    "event": "outcome",
                    "session_hash": session_hash,
                    **action_evidence,
                    **(
                        {"model_namespace": commons.identity.namespace}
                        if commons.identity is not None and commons.attribution_valid
                        else {}
                    ),
                    "outcome": outcome.value,
                    "pending": False,
                }
            )
            if (
                outcome.value == "unknown"
                and read_mode(data_root, repository_hash=identity.repository_hash).get("mode")
                == "enforce"
            ):
                demote_enforcement(
                    data_root,
                    repository_hash=identity.repository_hash,
                    reason="OUTCOME_UNOBSERVABLE",
                )
                evidence_store.start_new_window(reason_code="OUTCOME_UNOBSERVABLE")
            return None
        raise ValueError("unsupported service operation")

    return handle


def _installed_plugin_root() -> Path | None:
    """Derive the trusted installation root from the running immutable zipapp path."""

    executable = Path(sys.argv[0])
    if executable.name != "marginal_runtime.pyz":
        return None
    try:
        root = executable.resolve(strict=True).parent.parent
    except OSError:
        return None
    return root if (root / ".codex-plugin" / "plugin.json").is_file() else None


def _session_hash(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def _identity_fingerprint(identity: PromotionIdentity) -> str:
    return hashlib.sha256(
        json.dumps(asdict(identity), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _evidence_store(data_root: Path, repository_hash: str) -> EvidenceStore:
    return EvidenceStore(data_root / "evidence" / repository_hash)


def _bootstrap_path(data_root: Path, session_id: str) -> Path:
    bootstrap_root = data_root / "bootstrap"
    bootstrap_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        bootstrap_root.chmod(0o700)
    session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return bootstrap_root / f"{session_key}-{secrets.token_hex(8)}.json"


def _bootstrap_event_payload(event: SessionEvent) -> dict[str, Any]:
    """Keep the ephemeral service bootstrap free of transcript and unrelated hook fields."""

    return {
        "session_id": event.session_id,
        "cwd": event.cwd,
        "hook_event_name": event.hook_event_name,
        "model": event.model,
        "permission_mode": event.permission_mode,
    }


def _spawn_session_service(
    event: SessionEvent,
    *,
    data_root: Path,
) -> ConnectionInfo:
    existing_path = _connection_path(data_root, event.session_id)
    if existing_path.exists():
        try:
            existing = ConnectionInfo.from_file(existing_path)
            if request_session(existing, operation="status", payload={}).get("ok") is True:
                return existing
        except (OSError, ValueError, KeyError):
            pass
        existing_path.unlink(missing_ok=True)

    bootstrap = _bootstrap_path(data_root, event.session_id)
    payload = {
        "event": _bootstrap_event_payload(event),
        "data_root": str(data_root),
        "token": secrets.token_hex(32),
        "identity": asdict(current_promotion_identity(event.cwd)),
    }
    descriptor = os.open(bootstrap, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(
            descriptor,
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

    executable = Path(sys.argv[0]).resolve()
    if executable.suffix == ".pyz":
        command = [sys.executable, str(executable), "--serve", str(bootstrap)]
    else:
        command = [
            sys.executable,
            "-m",
            "marginal.integrations.codex.service",
            "--serve",
            str(bootstrap),
        ]
    environment = {
        name: value
        for name in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "PYTHONPATH")
        if (value := os.environ.get(name)) is not None
    }
    subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
        close_fds=True,
        start_new_session=True,
    )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if existing_path.exists():
            try:
                connection = ConnectionInfo.from_file(existing_path)
                if request_session(connection, operation="status", payload={}).get("ok") is True:
                    return connection
            except (OSError, ValueError, KeyError):
                pass
        time.sleep(0.05)
    bootstrap.unlink(missing_ok=True)
    raise RuntimeError("Codex session service did not become ready")


def _serve_bootstrap(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    finally:
        path.unlink(missing_ok=True)
    event = parse_hook_event(payload["event"])
    if not isinstance(event, SessionEvent) or event.hook_event_name != "SessionStart":
        return 2
    data_root = Path(payload["data_root"]).resolve()
    token = str(payload["token"])
    identity = PromotionIdentity(**payload["identity"])
    evidence_store = _evidence_store(data_root, identity.repository_hash)
    session_hash = _session_hash(event.session_id)
    evidence_store.append(
        {"schema_version": 1, "event": "session_start", "session_hash": session_hash}
    )
    commons = _start_commons(data_root, model=event.model, evidence_store=evidence_store)
    treasury = Treasury(BudgetLimits(), mode="shadow")
    universal = UniversalRuntime(
        treasury,
        engine="codex",
        session_id=event.session_id,
        task_id=identity.repository_hash,
        capabilities=AgentCapabilities(block_actions=True),
    )
    runtime = CodexSessionRuntime(
        universal,
        workspace=event.cwd,
        enforcement_enabled=lambda: enforcement_is_active(
            data_root,
            identity=identity,
            summary=summarize_verified_evidence(evidence_store)[0],
            ledger_path=evidence_store.governance_ledger_path,
        ),
        plugin_root=_installed_plugin_root(),
        autopilot=AutopilotController(
            data_root,
            repository_hash=identity.repository_hash,
            evidence=evidence_store,
            identity_fingerprint=_identity_fingerprint(identity),
            user_consent=autopilot_consent_configured(data_root),
        ),
    )
    shutdown_event = threading.Event()
    server = SessionServer(
        data_root=data_root,
        session_id=event.session_id,
        token=token,
        handler=_handler(
            runtime,
            evidence_store=evidence_store,
            session_hash=session_hash,
            data_root=data_root,
            identity=identity,
            commons=commons,
            shutdown_event=shutdown_event,
        ),
    )
    server.start()
    shutdown_event.wait()
    server.stop()
    return 0


def start_session_service(
    event: SessionEvent,
    *,
    data_root: str | Path,
) -> ConnectionInfo:
    if event.hook_event_name != "SessionStart":
        raise ValueError("start_session_service requires SessionStart")
    root = Path(data_root).resolve()
    key = (root, event.session_id)
    active = _SERVERS.get(key)
    if active is not None:
        response = request_session(active[0].connection, operation="status", payload={})
        if response.get("ok") is True:
            return active[0].connection
        active[0].stop()
        _SERVERS.pop(key, None)

    identity = current_promotion_identity(event.cwd)
    evidence_store = _evidence_store(root, identity.repository_hash)
    session_hash = _session_hash(event.session_id)
    evidence_store.append(
        {"schema_version": 1, "event": "session_start", "session_hash": session_hash}
    )
    commons = _start_commons(root, model=event.model, evidence_store=evidence_store)
    treasury = Treasury(BudgetLimits(), mode="shadow")
    universal = UniversalRuntime(
        treasury,
        engine="codex",
        session_id=event.session_id,
        task_id=identity.repository_hash,
        capabilities=AgentCapabilities(block_actions=True),
    )
    runtime = CodexSessionRuntime(
        universal,
        workspace=event.cwd,
        enforcement_enabled=lambda: enforcement_is_active(
            root,
            identity=identity,
            summary=summarize_verified_evidence(evidence_store)[0],
            ledger_path=evidence_store.governance_ledger_path,
        ),
        plugin_root=_installed_plugin_root(),
        autopilot=AutopilotController(
            root,
            repository_hash=identity.repository_hash,
            evidence=evidence_store,
            identity_fingerprint=_identity_fingerprint(identity),
            user_consent=autopilot_consent_configured(root),
        ),
    )
    server = SessionServer(
        data_root=root,
        session_id=event.session_id,
        token=secrets.token_hex(32),
        handler=_handler(
            runtime,
            evidence_store=evidence_store,
            session_hash=session_hash,
            data_root=root,
            identity=identity,
            commons=commons,
        ),
    )
    connection = server.start()
    _SERVERS[key] = (server, runtime)
    return connection


def stop_session_service(session_id: str, *, data_root: str | Path) -> None:
    root = Path(data_root).resolve()
    key = (root, session_id)
    active = _SERVERS.pop(key, None)
    if active is not None:
        server, _runtime = active
        request_session(server.connection, operation="close", payload={})
        server.stop()
        return
    path = _connection_path(root, session_id)
    if path.exists():
        try:
            connection = ConnectionInfo.from_file(path)
            request_session(connection, operation="close", payload={})
        finally:
            path.unlink(missing_ok=True)


def _mode_path(data_root: Path, repository_hash: str) -> Path:
    return data_root / "repositories" / f"{repository_hash}.json"


def read_mode(data_root: str | Path, *, repository_hash: str) -> dict[str, Any]:
    target = _mode_path(Path(data_root).resolve(), repository_hash)
    if not target.exists():
        return {"schema_version": 1, "mode": "shadow", "reason": "default"}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("repository mode must be a JSON object")
    return payload


def _demote_all_enforced(data_root: Path, reason: str) -> None:
    repository_root = data_root / "repositories"
    if not repository_root.exists():
        return
    for path in repository_root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("mode") == "enforce":
            try:
                demote_enforcement(
                    data_root,
                    repository_hash=path.stem,
                    reason=reason,
                )
            except OSError:
                continue


def _fail_open_for_workspace(data_root: Path, cwd: str, reason: str) -> None:
    repository_hash = repository_identity_hash(cwd)
    try:
        store = _evidence_store(data_root, repository_hash)
        store.append(
            {
                "schema_version": 1,
                "event": "integration_failure",
                "reason_code": reason,
                "integration_failure": True,
            }
        )
        store.start_new_window(reason_code=reason)
        AutopilotController(
            data_root,
            repository_hash=repository_hash,
            evidence=store,
        ).revoke(reason)
    except OSError:
        pass
    with suppress(OSError):
        demote_enforcement(
            data_root,
            repository_hash=repository_hash,
            reason=reason,
        )


def run_hook(payload: dict[str, Any], *, data_root: str | Path) -> HookResult:
    """Execute one hook. Integration faults always fail open and demote enforcement."""

    root = Path(data_root).resolve()
    event: SessionEvent | PreToolUseEvent | PostToolUseEvent | UserPromptSubmitEvent | None = None
    try:
        event = parse_hook_event(payload)
        if isinstance(event, SessionEvent):
            if event.hook_event_name == "SessionStart":
                _spawn_session_service(event, data_root=root)
            else:
                stop_session_service(event.session_id, data_root=root)
            return HookResult(exit_code=0)

        connection_path = _connection_path(root, event.session_id)
        if not connection_path.exists():
            _fail_open_for_workspace(root, event.cwd, "SERVICE_UNAVAILABLE")
            return HookResult(exit_code=0, warning_code="SERVICE_UNAVAILABLE")
        connection = ConnectionInfo.from_file(connection_path)
        operation = (
            "pre"
            if isinstance(event, PreToolUseEvent)
            else "post"
            if isinstance(event, PostToolUseEvent)
            else "prompt"
        )
        response = request_session(connection, operation=operation, payload=payload)
        if response.get("ok") is not True:
            code = str(response.get("error_code", "SERVICE_ERROR"))
            _fail_open_for_workspace(root, event.cwd, code)
            return HookResult(exit_code=0, warning_code=code)
        result = response.get("result")
        output = result if isinstance(result, dict) else None
        return HookResult(exit_code=0, output=output)
    except Exception:
        if event is not None:
            _fail_open_for_workspace(root, event.cwd, "INTEGRATION_ERROR")
        else:
            _demote_all_enforced(root, "INTEGRATION_ERROR")
        return HookResult(exit_code=0, warning_code="INTEGRATION_ERROR")


def hook_main(argv: list[str] | None = None) -> int:
    """Zipapp entry point used by the native plugin hook shim."""

    selected = list(sys.argv[1:] if argv is None else argv)
    if len(selected) == 2 and selected[0] == "--serve":
        return _serve_bootstrap(Path(selected[1]).resolve())
    data_root_value = os.environ.get("PLUGIN_DATA")
    if not data_root_value:
        return 0
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    result = run_hook(payload, data_root=data_root_value)
    if result.output is not None:
        print(json.dumps(result.output, sort_keys=True, separators=(",", ":")))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(hook_main())
