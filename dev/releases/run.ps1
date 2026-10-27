# SPDX-License-Identifier: GPL-3.0-or-later
# Starts Nexus Releases on Windows with the checkout's Windows venv and bc250_core from core\, as run.sh does on
# Linux. It only edits files; committing, tagging and pushing stay with you.
#
#   dev\releases\run.ps1            # open the window
#   dev\releases\run.ps1 --list     # list the apps, their tags and what needs a release
#   dev\releases\install.ps1        # Start-menu entry and Desktop shortcut for this checkout
$ErrorActionPreference = 'Stop'
$app = $PSScriptRoot
$repo = (Resolve-Path (Join-Path $app '..\..')).Path
if ($args -contains '-h' -or $args -contains '--help') {
    Get-Content -LiteralPath $PSCommandPath | Select-Object -Skip 1 -First 6 | ForEach-Object { $_ -replace '^# ?', '' }
    exit 0
}
$python = Join-Path $repo '.venv-windows\Scripts\python.exe'
if ($env:PYTHON) { $python = $env:PYTHON }
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "No Windows venv in $repo. Create it from the repository's root:" -ForegroundColor Red
    Write-Host '  py -m venv .venv-windows; .venv-windows\Scripts\python.exe -m pip install -r requirements-dev.txt'
    exit 1
}
if ($args -contains '--list') {
    & $python (Join-Path $app 'nexus_releases\plan.py')
    exit $LASTEXITCODE
}
Set-Location -LiteralPath $app
$env:PYTHONPATH = Join-Path $repo 'core'
& $python -m nexus_releases @args
exit $LASTEXITCODE
