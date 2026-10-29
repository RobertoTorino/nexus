# SPDX-License-Identifier: GPL-3.0-or-later
# Starts shadPS4 Manager from the checkout, with the checkout's Windows venv and bc250_core from core\.
#
#   windows-portable\apps\shadps4\run.ps1             # full screen
#   windows-portable\apps\shadps4\run.ps1 --windowed  # in a window
$ErrorActionPreference = 'Stop'
$app = $PSScriptRoot
$repo = (Resolve-Path (Join-Path $app '..\..\..')).Path
$python = Join-Path $repo '.venv-windows\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "No Windows venv in $repo. Create it from the repository's root:" -ForegroundColor Red
    Write-Host '  py -m venv .venv-windows; .venv-windows\Scripts\python.exe -m pip install -r requirements-dev.txt'
    exit 1
}
$env:PYTHONPATH = (Join-Path $repo 'core') + ';' + $app
& $python -m shadps4_manager @args
exit $LASTEXITCODE
