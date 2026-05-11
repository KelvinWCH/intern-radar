@echo off
setlocal
pushd "%~dp0backend" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
    echo Backend environment is missing. Follow the setup instructions in README.md. 1>&2
    popd
    exit /b 1
)
".venv\Scripts\python.exe" -m uvicorn job_backend.main:app --host 127.0.0.1 --port 8000 %*
set "backendExitCode=%errorlevel%"
popd
exit /b %backendExitCode%
