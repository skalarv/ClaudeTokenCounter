from __future__ import annotations

import subprocess
from typing import Optional


NVIDIA_CMD = [
    "nvidia-smi",
    "--query-gpu=utilization.gpu",
    "--format=csv,noheader,nounits",
]

PERFCOUNTER_CMD = [
    "powershell", "-NoProfile", "-Command",
    "(Get-Counter '\\GPU Engine(*engtype_3D)\\Utilization Percentage')"
    ".CounterSamples | Measure-Object -Property CookedValue -Sum | "
    "Select -ExpandProperty Sum",
]

_TIMEOUT_S = 1.5


class GPUMonitor:
    def __init__(self) -> None:
        self._last_good: Optional[int] = None
        self.source = self._detect_source()

    def _detect_source(self) -> str:
        if self._try(NVIDIA_CMD) is not None:
            return "nvidia-smi"
        if self._try(PERFCOUNTER_CMD) is not None:
            return "perfcounter"
        return "none"

    def _try(self, cmd) -> Optional[int]:
        try:
            cp = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=_TIMEOUT_S, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None
        if cp.returncode != 0:
            return None
        return self._parse(cp.stdout)

    @staticmethod
    def _parse(stdout: str) -> Optional[int]:
        vals = []
        for line in stdout.splitlines():
            line = line.strip().replace(",", ".")
            if not line:
                continue
            try:
                vals.append(float(line))
            except ValueError:
                return None
        if not vals:
            return None
        return int(round(max(0.0, min(100.0, max(vals)))))

    def read(self) -> Optional[int]:
        if self.source == "none":
            return None
        cmd = NVIDIA_CMD if self.source == "nvidia-smi" else PERFCOUNTER_CMD
        val = self._try(cmd)
        if val is not None:
            self._last_good = val
            return val
        return self._last_good
