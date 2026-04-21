# TokenFollow — Installation Guide

## Prerequisites

| Requirement | Minimum | Notes |
|---|---|---|
| **OS** | Windows 10 (1903+) | Windows 11 recommended; the GPU perfcounter fallback requires Windows 10 build 1903 or later |
| **Python** | 3.8+ | Must include `tkinter`; the official [python.org](https://www.python.org/downloads/) installer bundles it |
| **tkinter** | bundled | Absent in some slim distributions — see Troubleshooting |
| **Claude Code** | any | `~/.claude/projects/` must exist; TokenFollow reads JSONL logs from there |

---

## Option 1 — Automated install (recommended)

Double-click **`install.bat`** in the repository root.

What it does, step by step:

1. **[1/4] Python check** — runs `where python` and verifies `sys.version_info >= (3, 8)`.
   Exits with a clear error message if Python is missing or too old.
2. **[2/4] tkinter check** — runs `python -c "import tkinter"`.
   Exits with instructions if tkinter is unavailable (slim distributions).
3. **[3/4] Test dependencies** — runs
   `pip install --quiet pytest pytest-cov`.
   The app still works if this step fails; you just cannot run the test suite.
4. **[4/4] Desktop shortcut** — uses a PowerShell `WScript.Shell` COM call to
   create `TokenFollow.lnk` on your Desktop pointing at `TokenFollow.bat` in the
   repo directory.

When the installer finishes you will see:

```
============================================================
  Install complete.
============================================================

  Double-click 'TokenFollow' on your Desktop to launch the
  overlay.  Config is written next to the script on first run
  (config.json, cache.json).  Close the overlay from its title
  bar; position and budgets are remembered between runs.

  To run the test suite:   run_tests.bat
```

---

## Option 2 — Manual install

### Step 1 — Get the code

```
git clone https://github.com/yourname/TokenFollow.git
cd TokenFollow
```

Or download and unzip a release archive anywhere on your machine.

### Step 2 — Verify Python

```
python --version
```

Must print `Python 3.8.x` or higher.  If the command is not found, install
Python from [python.org](https://www.python.org/downloads/) and tick
**"Add python.exe to PATH"** during setup.

```
python -c "import tkinter; print('tkinter OK')"
```

Must print `tkinter OK`.  If it raises `ModuleNotFoundError`, see
Troubleshooting below.

### Step 3 — Optional: install test dependencies

Only needed if you want to run `run_tests.bat`:

```
pip install pytest pytest-cov
```

### Step 4 — Create a Desktop shortcut (optional)

Two approaches:

**Copy the launcher:**

```
copy TokenFollow.bat "%USERPROFILE%\Desktop\"
```

The `.bat` uses `%~dp0` to resolve `token_follow.py` next to itself, so the
copy must sit in the same folder as the Python files **or** you must create a
`.lnk` shortcut instead.

**Create a shortcut via Explorer:**

1. Right-click `TokenFollow.bat` → **Send to** → **Desktop (create shortcut)**.
2. The shortcut's "Start in" directory is set automatically.

---

## First-run behaviour

When the overlay starts for the first time:

* **`config.json`** is created next to `token_follow.py` with default budgets
  (`88 M` tokens for the 5-hour window, `70 M` for weekly Opus,
  `440 M` for weekly Sonnet).
* **`cache.json`** is written on graceful close; it records file byte-offsets
  for diagnostic purposes only and is not read on startup.
* The window appears in the **upper-left area** of the screen (Tk default
  position).  It is always-on-top.
* If `~/.claude/projects/` does not exist yet (no Claude Code sessions ever
  run), all bars show zero — this is expected.

---

## Uninstall

TokenFollow makes **no registry changes** and installs **no services**.

To remove it completely:

1. Delete the repo folder (e.g. `C:\Users\you\TokenFollow\`).
2. Delete the Desktop shortcut `TokenFollow.lnk`.
3. Optionally remove `pytest` / `pytest-cov` if you installed them only for
   this project: `pip uninstall pytest pytest-cov`.

That's it — nothing else to clean up.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `'python' is not recognized as an internal or external command` | Python not on PATH | Reinstall Python from [python.org](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"** during setup |
| `ModuleNotFoundError: No module named 'tkinter'` | Slim Python distribution (conda minimal env, Microsoft Store Python) | Reinstall Python from the official [python.org](https://www.python.org/downloads/) Windows installer, which bundles tkinter |
| `QA FAILED: coverage` when running `run_tests.bat` | A source change broke a test or dropped coverage below 97% | Run `python -m pytest -v tests/` to identify the failing test; this is expected only after code changes |
| **GPU row shows N/A** | `nvidia-smi` not on PATH **and** GPU performance counters inaccessible | Expected on some systems (integrated graphics, locked-down corp images). Token tracking still works normally |
| **Window appears briefly, then vanishes** | An unhandled exception in the `tick` callback | Run `python token_follow.py` from a Command Prompt (not `pythonw`); the traceback will appear in the console |
| `install.bat` exits at step [4/4] with "Could not create Desktop shortcut" | PowerShell execution policy or COM restriction | Create the shortcut manually: right-click `TokenFollow.bat` → Send to → Desktop (create shortcut) |
| **Bars never move / always zero** | `~/.claude/projects/` is empty or Claude Code hasn't been used | Run Claude Code at least once; the parser needs at least one `.jsonl` file |
| **Config.json replaced with `.bak`** | File was corrupted (e.g. power loss mid-write) | The original is preserved as `config.json.bak`; defaults are used. Edit `config.json` to restore custom budgets |
