# SPDX-License-Identifier: GPL-3.0-or-later
# Starts Nexus Dashboard on Windows with the checkout's Windows venv and bc250_core from core\, as run.sh does on
# Linux.
#
#   dev\dash\run.ps1 [--suite NAME]   # open the window (on the suite named)
#   dev\dash\install.ps1              # Start-menu entry and Desktop shortcut for this checkout
$ErrorActionPreference = 'Stop'
$app = $PSScriptRoot
$repo = (Resolve-Path (Join-Path $app '..\..')).Path
if ($args -contains '-h' -or $args -contains '--help') {
    Get-Content -LiteralPath $PSCommandPath | Select-Object -Skip 1 -First 5 | ForEach-Object { $_ -replace '^# ?', '' }
    exit 0
}
$python = Join-Path $repo '.venv-windows\Scripts\python.exe'
if ($env:PYTHON) { $python = $env:PYTHON }
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "No Windows venv in $repo. Create it from the repository's root:" -ForegroundColor Red
    Write-Host '  py -m venv .venv-windows; .venv-windows\Scripts\python.exe -m pip install -r requirements-dev.txt'
    exit 1
}
Set-Location -LiteralPath $app
$env:PYTHONPATH = Join-Path $repo 'core'
& $python -m nexus_dashboard @args
exit $LASTEXITCODE
