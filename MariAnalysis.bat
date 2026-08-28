@echo off
title MariAnalysis
setlocal EnableExtensions

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PY=%ROOT%\backend\.venv\Scripts\python.exe"

rem -- backend (Flask :5001) start if not running --
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue)) { Start-Process -FilePath '%PY%' -ArgumentList 'dev_restart.py' -WorkingDirectory '%ROOT%\backend' -WindowStyle Hidden }"

rem -- frontend (React :3000) start if not running --
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)) { Start-Process cmd.exe -ArgumentList '/c npm start > \"%ROOT%\frontend.log\" 2>&1' -WorkingDirectory '%ROOT%\frontend' -WindowStyle Hidden }"

rem -- wait for both servers (cold compile ~2 min) --
powershell -NoProfile -Command "$d=(Get-Date).AddSeconds(180); while((Get-Date) -lt $d){ $b=Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue; $f=Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue; if($b -and $f){break}; Start-Sleep 2 }"
ping -n 3 127.0.0.1 >nul

rem -- open in browser only if no tab is already showing the app --
powershell -NoProfile -Command "$t=Get-Process chrome,msedge,firefox,brave -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -match 'marianalysis|localhost:3000' }; if(-not $t){ Start-Process 'http://localhost:3000' }"
exit
