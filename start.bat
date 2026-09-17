@echo off
pushd "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "rc=%ERRORLEVEL%"
popd
exit /b %rc%
