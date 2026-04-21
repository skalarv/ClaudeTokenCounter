from __future__ import annotations

import subprocess
from unittest.mock import patch, MagicMock

from tokenfollow.gpu import GPUMonitor


def _ok(stdout: str):
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    return m


def test_picks_nvidia_when_available():
    with patch("subprocess.run", return_value=_ok("42\n")):
        gm = GPUMonitor()
    assert gm.source == "nvidia-smi"


def test_falls_back_to_perfcounter_when_nvidia_missing():
    def fake_run(cmd, *a, **kw):
        if "nvidia-smi" in (cmd[0] if isinstance(cmd, list) else cmd):
            raise FileNotFoundError
        return _ok("27\n")
    with patch("subprocess.run", side_effect=fake_run):
        gm = GPUMonitor()
    assert gm.source == "perfcounter"


def test_source_none_when_both_fail():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        gm = GPUMonitor()
    assert gm.source == "none"
    assert gm.read() is None


def test_nvidia_parse_single_gpu():
    with patch("subprocess.run", return_value=_ok("42\n")):
        gm = GPUMonitor()
    with patch("subprocess.run", return_value=_ok("42\n")):
        assert gm.read() == 42


def test_nvidia_parse_multi_gpu_takes_max():
    with patch("subprocess.run", return_value=_ok("12\n88\n55\n")):
        gm = GPUMonitor()
    with patch("subprocess.run", return_value=_ok("12\n88\n55\n")):
        assert gm.read() == 88


def test_nvidia_read_returns_none_on_garbled_output():
    with patch("subprocess.run", return_value=_ok("42\n")):
        gm = GPUMonitor()
    with patch("subprocess.run", return_value=_ok("not a number\n")):
        assert gm.read() is None


def test_perfcounter_clamp_upper():
    with patch("subprocess.run", side_effect=[FileNotFoundError, _ok("137.5\n")]):
        gm = GPUMonitor()
    assert gm.source == "perfcounter"
    with patch("subprocess.run", return_value=_ok("137.5\n")):
        assert gm.read() == 100


def test_perfcounter_clamp_lower():
    with patch("subprocess.run", side_effect=[FileNotFoundError, _ok("5\n")]):
        gm = GPUMonitor()
    with patch("subprocess.run", return_value=_ok("-3\n")):
        assert gm.read() == 0


def test_timeout_returns_last_good():
    with patch("subprocess.run", return_value=_ok("42\n")):
        gm = GPUMonitor()
    with patch("subprocess.run", return_value=_ok("42\n")):
        assert gm.read() == 42
    with patch("subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1.5)):
        assert gm.read() == 42


def test_none_source_read_is_none():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        gm = GPUMonitor()
    assert gm.read() is None
