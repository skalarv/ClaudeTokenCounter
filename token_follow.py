"""TokenFollow — always-on-top Claude Code usage + GPU overlay.

Entry point: call :func:`main` (or run this file directly).  Reads JSONL logs
from ``~/.claude/projects/``, aggregates token usage into rolling 5-hour and
weekly windows (Fable, Opus, Sonnet+Haiku), polls the GPU, and drives the
:class:`~tokenfollow.ui.OverlayWindow` Tk event loop.  Window position and observed-max budgets are persisted to
``config.json`` / ``cache.json`` next to this file on close.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from tokenfollow.account import AccountUsageMonitor
from tokenfollow.aggregator import aggregate
from tokenfollow.budget import BudgetManager
from tokenfollow.gpu import GPUMonitor
from tokenfollow.parser import UsageParser
from tokenfollow.ui import OverlayWindow


HERE = Path(__file__).resolve().parent
CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"
CLAUDE_CREDENTIALS = Path.home() / ".claude" / ".credentials.json"


def main() -> None:
    """Bootstrap all subsystems and start the Tk main loop.

    Creates :class:`~tokenfollow.budget.BudgetManager`,
    :class:`~tokenfollow.parser.UsageParser`, and
    :class:`~tokenfollow.gpu.GPUMonitor`, then enters a recurring ``tick``
    callback that updates the overlay every ``refresh_seconds``.
    """
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    bm = BudgetManager(HERE / "config.json")
    parser = UsageParser(CLAUDE_PROJECTS_ROOT)
    gpu = GPUMonitor()
    account = (AccountUsageMonitor(CLAUDE_CREDENTIALS,
                                   bm.account_refresh_seconds)
               if bm.account_enabled else None)

    def on_close():
        x, y = win.current_position()
        bm.save_position(x, y)
        parser.save_cache(HERE / "cache.json")

    win = OverlayWindow(on_close=on_close)
    win.restore_position(bm.window_position)

    def tick():
        try:
            records = parser.scan()
            snap = aggregate(records, bm.budgets, bm.observed,
                             datetime.now(tz=timezone.utc), bm.weights,
                             rate_windows=bm.rate_windows)
            snap.gpu_percent = gpu.read()
            snap.account = account.read() if account is not None else None
            bm.maybe_bump(snap)
            win.update(snap)
        except Exception:                     # pragma: no cover
            logging.exception("tick failed; keeping last snapshot")
        win.root.after(bm.refresh_seconds * 1000, tick)

    tick()
    win.root.mainloop()


if __name__ == "__main__":
    main()
