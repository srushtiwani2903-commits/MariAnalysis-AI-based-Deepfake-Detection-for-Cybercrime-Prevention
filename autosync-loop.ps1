# MariAnalysis auto-sync loop - launched at every Windows logon.
# Runs autosync.ps1 immediately, then every 5 minutes forever.
$ErrorActionPreference = "SilentlyContinue"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$autosync = Join-Path $dir "autosync.ps1"

while ($true) {
    & $autosync
    Start-Sleep -Seconds 300
}
