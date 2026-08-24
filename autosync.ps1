# MariAnalysis auto-sync: two-way sync with origin/main.
#  - PULL: collaborator changes from GitHub are fetched and applied (local
#    uncommitted edits are stashed first and restored after; on conflict the
#    stash is kept for manual resolution).
#  - PUSH: any local change (new/edited files included) is auto-committed and
#    pushed to GitHub, so work done on this PC reaches the repo automatically.
# Registered as a Scheduled Task (every 5 minutes + at logon).
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$log = Join-Path $root "autosync.log"
$py = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = (Get-Command python -ErrorAction SilentlyContinue).Source }

function Log($msg) {
    "$([DateTime]::Now.ToString('yyyy-MM-dd HH:mm:ss')) $msg" | Out-File -FilePath $log -Append -Encoding utf8
}
function Port-Open([int]$port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}
function Stop-Backends {
    # Only kill MariAnalysis processes (path contains MariAnalysis). Other
    # projects (e.g. Task Manager) also use port 5000 - never touch them.
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
        $_.CommandLine -match 'MariAnalysis'
    } | ForEach-Object { taskkill /PID $_.ProcessId /T /F | Out-Null }
    Start-Sleep -Seconds 1
}
function Stop-Port([int]$port) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) { $conn | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    } }
    Start-Sleep -Seconds 1
}

Log "=== autosync run ==="

Push-Location $root

git fetch origin --prune | Out-Null
if ($LASTEXITCODE -ne 0) { Log "git fetch failed - will retry next cycle"; Pop-Location; exit }

$pulled = $false
$before = git rev-parse HEAD
$behind = [int](git rev-list --count HEAD..origin/main 2>$null)
if ($behind -gt 0) {
    Log "behind origin/main by $behind commit(s)"

    $dirty = git status --porcelain | Where-Object { $_.Trim() -ne "" }
    $stashed = $false
    if ($dirty) {
        git stash push -u -m "autosync $(Get-Date -Format o)" | Out-Null
        if ($LASTEXITCODE -eq 0) { $stashed = $true; Log "stashed local changes ($($dirty.Count) file(s))" }
        else { Log "stash failed - aborting pull"; Pop-Location; exit }
    }

    git pull --ff-only origin main
    $ok = ($LASTEXITCODE -eq 0)
    if ($ok) {
        $after = git rev-parse HEAD
        $pulled = $true
        Log "pulled $($before.Substring(0,7)) -> $($after.Substring(0,7))"
    } else {
        Log "pull failed (likely conflict with local changes) - resolve manually"
        if ($stashed) { git stash pop | Out-Null; Log "stash popped (after failed pull)" }
        Pop-Location
        exit
    }

    if ($stashed) {
        git stash pop | Out-Null
        if ($LASTEXITCODE -eq 0) { Log "stash popped" }
        else { Log "stash pop CONFLICT - run 'git stash list' and 'git stash pop' to resolve" }
    }
}

# --- push local work to GitHub (auto-commit + auto-push) ---
$dirty = git status --porcelain | Where-Object { $_.Trim() -ne "" }
if ($dirty) {
    git add -A
    git commit -m "Auto-sync: local changes $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    if ($LASTEXITCODE -eq 0) { Log "auto-committed $($dirty.Count) file(s)" }
    else { Log "nothing to commit after add" }
}
$ahead = [int](git rev-list --count origin/main..HEAD 2>$null)
$pushed = $false
if ($ahead -gt 0) {
    git push origin main
    if ($LASTEXITCODE -eq 0) { $pushed = $true; Log "pushed $ahead commit(s) to origin/main" }
    else { Log "push failed (remote may have new commits) - will retry next cycle" }
}

if (-not $pulled -and -not $pushed) { Log "up to date"; Pop-Location; exit }

$changed = git diff --name-only $before..HEAD

if ($changed -match 'requirements') {
    Log "requirements changed - reinstalling backend deps"
    if ($py) {
        & $py -m pip install -r (Join-Path $backend "requirements.txt") --quiet
        & $py -m pip install -r (Join-Path $backend "requirements-ai.txt") --quiet
    }
}
if ($changed -match 'package\.json|package-lock') {
    Log "package.json changed - running npm install"
    Push-Location $frontend
    npm install --silent
    Pop-Location
}

Log "restarting servers with updated code"
Stop-Backends
Stop-Port 3000
$feLog = Join-Path $root "frontend.log"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm start > `"$feLog`" 2>&1" -WorkingDirectory $frontend -WindowStyle Hidden
if (Test-Path (Join-Path $backend ".venv\Scripts\python.exe")) {
    Start-Process -FilePath (Join-Path $backend ".venv\Scripts\python.exe") -ArgumentList "dev_restart.py" -WorkingDirectory $backend -WindowStyle Hidden
} else {
    $beLog = Join-Path $backend "dev_server.log"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$py`" run.py > `"$beLog`" 2>&1" -WorkingDirectory $backend -WindowStyle Hidden
}

$deadline = (Get-Date).AddSeconds(150)
while ((Get-Date) -lt $deadline) {
    if ((Port-Open 5001) -and (Port-Open 3000)) { Log "both servers up"; break }
    Start-Sleep -Seconds 2
}

Pop-Location
Log "autosync cycle complete"
