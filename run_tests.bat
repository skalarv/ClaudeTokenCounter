@echo off
pushd "%~dp0"
python -m pytest --cov=tokenfollow --cov-branch --cov-report=term-missing --cov-fail-under=97 tests/
if errorlevel 1 (
  echo QA FAILED: coverage or tests
  popd
  exit /b 1
)
python scripts\check_matrix.py
if errorlevel 1 (
  echo QA FAILED: feature matrix
  popd
  exit /b 1
)
echo QA PASSED
popd
