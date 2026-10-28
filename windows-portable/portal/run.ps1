# SPDX-License-Identifier: GPL-3.0-or-later
# Starts the Windows Portable Suite's portal from the checkout, with the checkout's Windows venv and bc250_core from
# core\. It installs the apps its apps.toml pins from their GitHub releases, as the installed portal does.
#
#   windows-portable\portal\run.ps1             # full screen
#   windows-portable\portal\run.ps1 --windowed  # in a window
$ErrorActionPreference = 'Stop'
$portal = $PSScriptRoot
$repo = (Resolve-Path (Join-Path $portal '..\..')).Path
$python = Join-Path $repo '.venv-windows\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "No Windows venv in $repo. Create it from the repository's root:" -ForegroundColor Red
    Write-Host '  py -m venv .venv-windows; .venv-windows\Scripts\python.exe -m pip install -r requirements-dev.txt'
    exit 1
}
$env:PYTHONPATH = (Join-Path $repo 'core') + ';' + $portal
& $python -m portable_portal @args
exit $LASTEXITCODE
