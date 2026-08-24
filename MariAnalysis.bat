@echo off
title MariAnalysis
setlocal EnableExtensions

set "ROOT=C:\Users\Harshal\marianalysis"
set "PY=%ROOT%\backend\.venv\Scripts\python.exe"
set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"

rem -- backend (Flask :5001) start if not running --
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue)) { Start-Process -FilePath '%PY%' -ArgumentList 'dev_restart.py' -WorkingDirectory '%ROOT%\backend' -WindowStyle Hidden }"

rem -- frontend (React :3000) start if not running --
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)) { Start-Process cmd.exe -ArgumentList '/c npm start > \"%ROOT%\frontend.log\" 2>&1' -WorkingDirectory '%ROOT%\frontend' -WindowStyle Hidden }"

rem -- wait for both servers (cold compile ~2 min) --
powershell -NoProfile -Command "$d=(Get-Date).AddSeconds(180); while((Get-Date) -lt $d){ $b=Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue; $f=Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue; if($b -and $f){break}; Start-Sleep 2 }"
ping -n 3 127.0.0.1 >nul

rem -- open in Chrome --
if exist "%CHROME%" (
    start "" "%CHROME%" --new-window "http://localhost:3000"
) else (
    start "" "http://localhost:3000"
)
exit
