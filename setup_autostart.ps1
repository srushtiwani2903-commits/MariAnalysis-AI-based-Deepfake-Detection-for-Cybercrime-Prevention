# MariAnalysis - one-time setup + auto-start registration for ANY machine.
# Run once after cloning. It:
#   1. Creates the backend venv + installs requirements
#   2. Installs frontend dependencies
#   3. Creates backend/.env from .env.example if missing
#   4. Registers autostart.ps1 in THIS user's Windows Startup folder so the
#      website opens automatically at every login
# Usage:  powershell -ExecutionPolicy Bypass -File setup_autostart.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = "python"

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python not found on PATH. Install from https://www.python.org and re-run." -ForegroundColor Red
    exit 1
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js/npm not found. Install from https://nodejs.org and re-run." -ForegroundColor Red
    exit 1
}

Step "Backend virtualenv + requirements"
if (-not (Test-Path (Join-Path $backend ".venv\Scripts\python.exe"))) {
    & $python -m venv (Join-Path $backend ".venv")
    if ($LASTEXITCODE -ne 0) { exit 1 }
}
$py = Join-Path $backend ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -r (Join-Path $backend "requirements.txt")
if ($LASTEXITCODE -ne 0) { exit 1 }

Step "Optional AI extras (enables Kaggle reference)"
& $py -m pip install -r (Join-Path $backend "requirements-ai.txt")
if ($LASTEXITCODE -ne 0) { Write-Host "AI extras failed - continuing anyway." -ForegroundColor Yellow }

Step "backend/.env from example"
if (-not (Test-Path (Join-Path $backend ".env"))) {
    Copy-Item (Join-Path $backend ".env.example") (Join-Path $backend ".env")
    Write-Host "Created backend/.env - edit it with your secrets!" -ForegroundColor Yellow
} else {
    Write-Host "backend/.env already exists."
}

Step "Frontend dependencies"
Push-Location $frontend
npm install
Pop-Location
if ($LASTEXITCODE -ne 0) { exit 1 }

Step "Register auto-start at Windows login"
$startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut((Join-Path $startup "MariAnalysis.lnk"))
$lnk.TargetPath = "C:\windows\System32\WindowsPowerShell\v1.0\powershell.exe"
$lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$root\autostart.ps1`""
$lnk.Save()

Write-Host "`nSetup complete!" -ForegroundColor Green
Write-Host "The website will now open automatically at every login on this PC."
Write-Host "To test now, run:  powershell -ExecutionPolicy Bypass -File `"$root\autostart.ps1`""
