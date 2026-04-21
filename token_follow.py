"""TokenFollow — always-on-top Claude Code usage + GPU overlay."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from tokenfollow.aggregator import aggregate
from tokenfollow.budget import BudgetManager
from tokenfollow.gpu import GPUMonitor
from tokenfollow.parser import UsageParser
from tokenfollow.ui import OverlayWindow


HERE = Path(__file__).resolve().parent
CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    bm = BudgetManager(HERE / "config.json")
    parser = UsageParser(CLAUDE_PROJECTS_ROOT)
    gpu = GPUMonitor()

    def on_close():
        x, y = win.current_position()
        bm.save_position(x, y)
        parser.save_cache(HERE / "cache.json")
        bm.save()

    win = OverlayWindow(on_close=on_close)
    win.restore_position(bm.window_position)

    def tick():
        try:
            records = parser.scan()
            snap = aggregate(records, bm.budgets, bm.observed,
                             datetime.now(tz=timezone.utc), bm.weights)
            snap.gpu_percent = gpu.read()
            bm.maybe_bump(snap)
            win.update(snap)
        except Exception:                     # pragma: no cover
            logging.exception("tick failed; keeping last snapshot")
        win.root.after(bm.refresh_seconds * 1000, tick)

    tick()
    win.root.mainloop()


if __name__ == "__main__":
    main()
