# SPDX-License-Identifier: GPL-3.0-or-later
# Starts Nexus Installer Tests on Windows with the checkout's Windows venv and bc250_core from core\, as run.sh does
# on Linux. On Windows it runs a Windows suite's .ps1 installer tests.
#
#   dev\itests\run.ps1 [--suite NAME]   # open the window (on the suite named)
#   (dev\itests\install.sh is Linux only: no Windows installer yet; Nexus Dashboard's tile starts it)
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
& $python -m installer_tests @args
exit $LASTEXITCODE
