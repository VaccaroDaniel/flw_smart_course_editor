@echo off
setlocal
set "BUNDLE_DIR=%~dp0"
set "PYTHONHOME=%BUNDLE_DIR%runtime\python311"
set "PYTHONPATH="
pushd "%BUNDLE_DIR%app"
start "" "%BUNDLE_DIR%runtime\python311\pythonw.exe" "%BUNDLE_DIR%app\server.py" --host 127.0.0.1 --port 8788
popd
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8788
endlocal
