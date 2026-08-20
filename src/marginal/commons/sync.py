"""Bounded fail-open orchestration for optional Commons network modes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .cache import CommonsCache
from .client import (
    CommonsClientProtocol,
    CommonsHTTPError,
    CommonsProtocolError,
    CommonsTransportError,
)
from .config import CommonsConfig, CommonsMode
from .evidence import CommonsEvidenceAtom
from .outbox import CommonsOutbox


class SyncFailure(str, Enum):
    """Closed local diagnostic categories that never contain raw error details."""

    DOWNLOAD_HTTP = "download_http"
    DOWNLOAD_PROTOCOL = "download_protocol"
    DOWNLOAD_TRANSPORT = "download_transport"
    CACHE_REJECTED = "cache_rejected"
    OUTBOX_WRITE = "outbox_write"
    OUTBOX_READ = "outbox_read"
    SUBMIT_PROTOCOL = "submit_protocol"
    SUBMIT_TRANSPORT = "submit_transport"
    OUTBOX_TRANSITION = "outbox_transition"


@dataclass(frozen=True, slots=True)
class CommonsSyncResult:
    """Fail-open bounded outcomes with no endpoint, evidence, or exception text."""

    network_calls: int = 0
    cache_refreshed: bool = False
    submitted: int = 0
    acked: int = 0
    quarantined: int = 0
    retained: int = 0
    failures: tuple[SyncFailure, ...] = ()


def synchronize_commons(
    config: CommonsConfig,
    *,
    cache: CommonsCache,
    outbox: CommonsOutbox,
    client: CommonsClientProtocol,
    model_namespace: str | None = None,
    atoms: tuple[CommonsEvidenceAtom, ...] = (),
    max_submissions: int = 8,
) -> CommonsSyncResult:
    """Download and optionally contribute without allowing any failure to block local work."""

    if not isinstance(config, CommonsConfig):
        raise TypeError("Commons sync requires a CommonsConfig")
    if (
        isinstance(max_submissions, bool)
        or not isinstance(max_submissions, int)
        or not 1 <= max_submissions <= 100
    ):
        raise ValueError("Commons submission bound must be between 1 and 100")
    if config.mode is CommonsMode.LOCAL_ONLY:
        return CommonsSyncResult()

    network_calls = 1
    cache_refreshed = False
    submitted = 0
    acked = 0
    quarantined = 0
    retained = 0
    failures: list[SyncFailure] = []
    try:
        pack = client.download()
    except CommonsHTTPError:
        failures.append(SyncFailure.DOWNLOAD_HTTP)
    except CommonsProtocolError:
        failures.append(SyncFailure.DOWNLOAD_PROTOCOL)
    except (CommonsTransportError, OSError, TimeoutError):
        failures.append(SyncFailure.DOWNLOAD_TRANSPORT)
    except Exception:
        failures.append(SyncFailure.DOWNLOAD_TRANSPORT)
    else:
        try:
            cache_refreshed = cache.refresh(pack)
        except Exception:
            cache_refreshed = False
        if not cache_refreshed:
            failures.append(SyncFailure.CACHE_REJECTED)

    if config.mode is CommonsMode.READ_ONLY:
        return CommonsSyncResult(
            network_calls=network_calls,
            cache_refreshed=cache_refreshed,
            failures=tuple(failures),
        )

    if model_namespace is not None and atoms:
        try:
            outbox.enqueue(model_namespace=model_namespace, atoms=atoms)
        except Exception:
            failures.append(SyncFailure.OUTBOX_WRITE)

    try:
        scan = outbox.pending(limit=max_submissions)
    except Exception:
        failures.append(SyncFailure.OUTBOX_READ)
        return CommonsSyncResult(
            network_calls=network_calls,
            cache_refreshed=cache_refreshed,
            failures=tuple(failures),
        )
    quarantined += scan.quarantined

    for entry in scan.entries:
        network_calls += 1
        submitted += 1
        try:
            client.submit(entry)
        except CommonsHTTPError as exc:
            if 400 <= exc.status < 500:
                try:
                    moved = outbox.quarantine(entry)
                except Exception:
                    moved = False
                if moved:
                    quarantined += 1
                else:
                    retained += 1
                    failures.append(SyncFailure.OUTBOX_TRANSITION)
            else:
                retained += 1
        except CommonsProtocolError:
            retained += 1
            failures.append(SyncFailure.SUBMIT_PROTOCOL)
        except (CommonsTransportError, OSError, TimeoutError):
            retained += 1
            failures.append(SyncFailure.SUBMIT_TRANSPORT)
        except Exception:
            retained += 1
            failures.append(SyncFailure.SUBMIT_TRANSPORT)
        else:
            try:
                deleted = outbox.ack(entry)
            except Exception:
                deleted = False
            if deleted:
                acked += 1
            else:
                retained += 1
                failures.append(SyncFailure.OUTBOX_TRANSITION)

    return CommonsSyncResult(
        network_calls=network_calls,
        cache_refreshed=cache_refreshed,
        submitted=submitted,
        acked=acked,
        quarantined=quarantined,
        retained=retained,
        failures=tuple(failures),
    )
