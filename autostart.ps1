# MariAnalysis autostart - run at Windows logon (via Startup shortcut).
# Starts backend watcher + frontend dev server if not already running,
# waits for them to come up, then opens the site in the default browser.
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$log = Join-Path $root "autostart.log"

# Prefer the project venv; fall back to global python (already has deps).
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { (Get-Command python -ErrorAction SilentlyContinue).Source }
$hasWatcher = Test-Path $venvPython

function Log($msg) {
    "$([DateTime]::Now.ToString('HH:mm:ss')) $msg" | Out-File -FilePath $log -Append -Encoding utf8
}

function Port-Open([int]$port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

Log "=== autostart run ==="

if (-not (Port-Open 5001)) {
    if (-not $python) {
        Log "ERROR: python not found; backend not started"
    } elseif ($hasWatcher) {
        Log "starting backend watcher"
        Start-Process -FilePath $python -ArgumentList "dev_restart.py" -WorkingDirectory $backend -WindowStyle Hidden
    } else {
        Log "starting backend (global python)"
        $beLog = Join-Path $backend "dev_server.log"
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$python`" run.py > `"$beLog`" 2>&1" -WorkingDirectory $backend -WindowStyle Hidden
    }
} else {
    Log "backend already running"
}

if (-not (Port-Open 3000)) {
    Log "starting frontend dev server"
    $feLog = Join-Path $root "frontend.log"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm start > `"$feLog`" 2>&1" -WorkingDirectory $frontend -WindowStyle Hidden
} else {
    Log "frontend already running"
}

# Cold-start compile can take ~90s; give it up to 150s.
$deadline = (Get-Date).AddSeconds(150)
while ((Get-Date) -lt $deadline) {
    if ((Port-Open 5001) -and (Port-Open 3000)) {
        Log "both servers up"
        break
    }
    Start-Sleep -Seconds 2
}

Start-Sleep -Seconds 3
Start-Process "http://localhost:3000"
Log "browser opened"
