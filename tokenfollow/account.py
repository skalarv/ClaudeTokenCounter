"""account — real account usage from the OAuth endpoint behind ``/usage``.

Inputs: the OAuth access token in ``~/.claude/.credentials.json`` plus the
``https://api.anthropic.com/api/oauth/usage`` endpoint (the same source the
Claude Code ``/usage`` panel renders).
Outputs: an :class:`AccountUsage` with the session / weekly limit percentages
and reset times as Anthropic's rate limiter actually tracks them.

The HTTPS call is made through a PowerShell subprocess so certificate
validation uses the Windows trust store (SChannel) — this survives
TLS-intercepting proxies whose CA Python's bundled OpenSSL rejects.  Fetches
run on a daemon thread and are cached, so the Tk main loop never blocks; a
last-good value is returned while a fetch is in flight or after a transient
failure (offline, expired token).
"""
from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

from tokenfollow.gpu import _NO_WINDOW_KWARGS


USAGE_URL = "https://api.anthropic.com/api/oauth/usage"

# The token travels via an environment variable (never argv, which other
# processes can read); TLS 1.2 is forced for Windows PowerShell 5.1.
FETCH_CMD = [
    "powershell", "-NoProfile", "-NonInteractive", "-Command",
    "[Net.ServicePointManager]::SecurityProtocol="
    "[Net.SecurityProtocolType]::Tls12;"
    "$h=@{Authorization=('Bearer '+$env:TOKENFOLLOW_OAUTH);"
    "'anthropic-beta'='oauth-2025-04-20'};"
    f"Invoke-RestMethod -Uri '{USAGE_URL}' -Headers $h -TimeoutSec 10"
    "|ConvertTo-Json -Depth 8",
]

_TIMEOUT_S = 20.0


@dataclass(frozen=True)
class AccountLimit:
    """One rate-limit window as reported by the account endpoint."""

    percent: float
    resets_at: Optional[datetime]
    severity: str = "normal"
    is_active: bool = False


@dataclass
class AccountUsage:
    """Parsed account usage: session + weekly_all + per-model scoped limits."""

    session: Optional[AccountLimit] = None
    weekly_all: Optional[AccountLimit] = None
    scoped: Dict[str, AccountLimit] = field(default_factory=dict)


def read_oauth_token(creds_path: Path) -> Optional[str]:
    """Extract the OAuth access token from ``.credentials.json``, or ``None``.

    Handles both a top-level ``accessToken`` and the usual one-level nesting
    (``{"claudeAiOauth": {"accessToken": ...}}``).
    """
    try:
        data = json.loads(Path(creds_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    tok = data.get("accessToken")
    if isinstance(tok, str) and tok:
        return tok
    for value in data.values():
        if isinstance(value, dict):
            tok = value.get("accessToken")
            if isinstance(tok, str) and tok:
                return tok
    return None


def _parse_reset(raw) -> Optional[datetime]:
    """Parse an ISO-8601 reset timestamp to aware UTC, or ``None``."""
    if not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_usage_payload(text: str) -> Optional[AccountUsage]:
    """Parse the endpoint's JSON into an :class:`AccountUsage`, or ``None``.

    The ``limits`` array is authoritative (it is what the ``/usage`` panel
    renders); ``five_hour`` / ``seven_day`` are used as a fallback for older
    payload shapes.
    """
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None

    usage = AccountUsage()

    for lim in obj.get("limits") or []:
        if not isinstance(lim, dict):
            continue
        entry = AccountLimit(
            percent=float(lim.get("percent") or 0),
            resets_at=_parse_reset(lim.get("resets_at")),
            severity=str(lim.get("severity") or "normal"),
            is_active=bool(lim.get("is_active")),
        )
        kind = lim.get("kind")
        if kind == "session":
            usage.session = entry
        elif kind == "weekly_all":
            usage.weekly_all = entry
        elif kind == "weekly_scoped":
            scope = lim.get("scope") or {}
            model = (scope.get("model") or {}).get("display_name")
            if isinstance(model, str) and model:
                usage.scoped[model.lower()] = entry

    if usage.session is None:
        fh = obj.get("five_hour")
        if isinstance(fh, dict) and fh.get("utilization") is not None:
            usage.session = AccountLimit(
                percent=float(fh["utilization"]),
                resets_at=_parse_reset(fh.get("resets_at")),
            )
    if usage.weekly_all is None:
        sd = obj.get("seven_day")
        if isinstance(sd, dict) and sd.get("utilization") is not None:
            usage.weekly_all = AccountLimit(
                percent=float(sd["utilization"]),
                resets_at=_parse_reset(sd.get("resets_at")),
            )

    if usage.session is None and usage.weekly_all is None and not usage.scoped:
        return None
    return usage


class AccountUsageMonitor:
    """Polls the account usage endpoint on a background thread.

    :meth:`read` never blocks: it returns the last-good :class:`AccountUsage`
    (or ``None`` before the first success) and, when the cached value is older
    than ``refresh_seconds``, kicks off one background fetch.
    """

    def __init__(self, creds_path: Path, refresh_seconds: int = 60, *,
                 runner: Callable = subprocess.run,
                 spawner: Optional[Callable[[Callable[[], None]], None]] = None):
        """
        Args:
            creds_path: Path to ``~/.claude/.credentials.json``.
            refresh_seconds: Minimum seconds between endpoint fetches.
            runner: ``subprocess.run``-compatible callable (test seam).
            spawner: Callable that executes a thunk, by default on a daemon
                thread (tests inject a synchronous one).
        """
        self._creds_path = Path(creds_path)
        self._refresh_seconds = int(refresh_seconds)
        self._runner = runner
        self._spawner = spawner or self._spawn_thread
        self._lock = threading.Lock()
        self._last_good: Optional[AccountUsage] = None
        self._last_attempt: Optional[datetime] = None
        self._in_flight = False

    @staticmethod
    def _spawn_thread(thunk: Callable[[], None]) -> None:
        threading.Thread(target=thunk, daemon=True).start()

    def read(self, now: Optional[datetime] = None) -> Optional[AccountUsage]:
        """Return the cached account usage; refresh in the background if stale."""
        now = now or datetime.now(tz=timezone.utc)
        spawn = False
        with self._lock:
            stale = (self._last_attempt is None or
                     (now - self._last_attempt).total_seconds()
                     >= self._refresh_seconds)
            if stale and not self._in_flight:
                self._in_flight = True
                self._last_attempt = now
                spawn = True
        if spawn:
            # Spawned outside the lock: a synchronous spawner (tests) calls
            # _fetch_once inline, which needs to re-acquire the lock.
            self._spawner(self._fetch_once)
        with self._lock:
            return self._last_good

    def _fetch_once(self) -> None:
        """Fetch and parse once; keep the last-good value on any failure."""
        try:
            usage = self._fetch()
            if usage is not None:
                with self._lock:
                    self._last_good = usage
        finally:
            with self._lock:
                self._in_flight = False

    def _fetch(self) -> Optional[AccountUsage]:
        """One synchronous endpoint call; ``None`` on any failure."""
        token = read_oauth_token(self._creds_path)
        if token is None:
            return None
        try:
            cp = self._runner(FETCH_CMD, capture_output=True, text=True,
                              timeout=_TIMEOUT_S, check=False,
                              env=self._fetch_env(token),
                              **_NO_WINDOW_KWARGS)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None
        if cp.returncode != 0:
            return None
        return parse_usage_payload(cp.stdout)

    @staticmethod
    def _fetch_env(token: str) -> Dict[str, str]:
        import os
        env = dict(os.environ)
        env["TOKENFOLLOW_OAUTH"] = token
        return env
