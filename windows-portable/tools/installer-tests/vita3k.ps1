# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise apps/vita3k/install.ps1: install from a release folder, an update without the Desktop shortcut, the
# refusals (administrator, --purge alone, an unknown option, the checkout without a built program), uninstall
# (settings and log kept) and --purge. The user's folders are a temp folder's: LOCALAPPDATA, APPDATA and the
# Desktop (WPS_DESKTOP_DIR); WPS_ELEVATED stands in for the administrator check, since CI's runner is one. Also a
# program running from the folder, which is refused with nothing changed, and an install by hand from a download
# (the download removed on a yes).
#
#   powershell -ExecutionPolicy Bypass -File windows-portable\tools\installer-tests\vita3k.ps1
#   ... vita3k.ps1 -Release dist\wp-vita3k-v0.1.0.zip     # the built release instead of a stand-in program
param([string]$Release = '')
$ErrorActionPreference = 'Stop'
$Suite = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$T = Join-Path ([IO.Path]::GetTempPath()) 'windows-portable-vita3k-installer'
if (Test-Path -LiteralPath $T) { Remove-Item -LiteralPath $T -Recurse -Force }
New-Item -ItemType Directory -Path $T | Out-Null
$script:fail = 0
function Check($label, [scriptblock]$test) {
    if (& $test) { Write-Host "  ok   $label" } else { Write-Host "  FAIL $label"; $script:fail = 1 }
}

$env:LOCALAPPDATA = Join-Path $T 'local'
$env:APPDATA = Join-Path $T 'roaming'
$env:WPS_DESKTOP_DIR = Join-Path $T 'desktop'
$env:WPS_ELEVATED = '0'
$AppId = 'windows-portable-vita3k'
$Exe = 'Vita3K-Manager.exe'
$AppHome = Join-Path $env:LOCALAPPDATA "windows-portable-suite\$AppId"
$A = Join-Path $AppHome 'app'
$Ini = Join-Path $env:APPDATA "windows-portable-suite\$AppId.ini"
$MenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Windows Portable Suite'
$Menu = Join-Path $MenuDir 'Vita3K Manager.lnk'
$Desk = Join-Path $env:WPS_DESKTOP_DIR 'Vita3K Manager.lnk'

# The release folder: the built one, or a stand-in with the same layout (a program\ with the exe and _internal\).
if ($Release) {
    Expand-Archive -LiteralPath $Release -DestinationPath (Join-Path $T 'release')
    $R = (Get-ChildItem -LiteralPath (Join-Path $T 'release') -Directory | Select-Object -First 1).FullName
} else {
    $R = Join-Path $T 'release\wp-vita3k-v0.0.0'
    New-Item -ItemType Directory -Force -Path (Join-Path $R 'program\_internal') | Out-Null
    Set-Content -LiteralPath (Join-Path $R "program\$Exe") -Value 'stand-in' -Encoding ascii
    Set-Content -LiteralPath (Join-Path $R 'program\_internal\marker.txt') -Value 'marker' -Encoding ascii
    Copy-Item -LiteralPath (Join-Path $Suite 'apps\vita3k\install.ps1'), (Join-Path $Suite 'apps\vita3k\LICENSE') -Destination $R
}
$Installer = Join-Path $R 'install.ps1'

function Run($log, [string[]]$options, $installer = $Installer) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer @options *> (Join-Path $T $log)
    return $LASTEXITCODE
}
function Log($log) { Get-Content -Raw -LiteralPath (Join-Path $T $log) }
function Target($link) { (New-Object -ComObject WScript.Shell).CreateShortcut($link).TargetPath }

Write-Host '== 1. install from the release folder'
$rc = Run 'log1' @()
Check 'exit 0' { $rc -eq 0 }
Check 'program copied with its _internal folder' { (Test-Path (Join-Path $A $Exe)) -and (Test-Path (Join-Path $A '_internal')) }
Check 'LICENSE copied, install.ps1 not' { (Test-Path (Join-Path $A 'LICENSE')) -and -not (Test-Path (Join-Path $A 'install.ps1')) }
Check 'Start-menu entry starts the installed exe' { (Test-Path $Menu) -and ((Target $Menu) -eq (Join-Path $A $Exe)) }
Check 'Desktop shortcut' { (Test-Path $Desk) -and ((Target $Desk) -eq (Join-Path $A $Exe)) }

Write-Host '== 2. update without the Desktop shortcut'
Set-Content -LiteralPath (Join-Path $A 'stale.txt') -Value 'from an older release' -Encoding ascii
$rc = Run 'log2' @('--no-desktop-shortcut')
Check 'exit 0' { $rc -eq 0 }
Check 'the old program replaced, nothing left over' { -not (Test-Path (Join-Path $A 'stale.txt')) -and -not (Test-Path "$A.new") }
Check 'Desktop shortcut removed, Start-menu entry kept' { -not (Test-Path $Desk) -and (Test-Path $Menu) }

Write-Host '== 2b. a program running from the folder is not replaced'
Copy-Item -LiteralPath (Join-Path $env:WINDIR 'System32\PING.EXE') -Destination (Join-Path $A 'running.exe')
$running = Start-Process (Join-Path $A 'running.exe') -ArgumentList '-n', '60', '127.0.0.1' -WindowStyle Hidden -PassThru
Start-Sleep -Milliseconds 800
$rc = Run 'log2b' @('--no-desktop-shortcut')
Stop-Process -Id $running.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
Check 'refused: close it first' { $rc -ne 0 -and (Log 'log2b') -match 'close .* first' }
Check 'the installed program untouched' { (Test-Path (Join-Path $A $Exe)) -and (Test-Path (Join-Path $A 'running.exe')) -and -not (Test-Path "$A.new") }
Remove-Item -LiteralPath (Join-Path $A 'running.exe') -Force

Write-Host '== 3. refusals'
$env:WPS_ELEVATED = '1'
$rc = Run 'log3' @()
$env:WPS_ELEVATED = '0'
Check 'administrator refused' { $rc -ne 0 -and (Log 'log3') -match 'not as administrator' }
$rc = Run 'log3' @('--purge')
Check '--purge alone refused' { $rc -ne 0 -and (Log 'log3') -match 'only goes with --uninstall' }
$rc = Run 'log3' @('--bogus')
Check 'unknown option refused' { $rc -ne 0 -and (Log 'log3') -match 'Unknown option: --bogus' }
$rc = Run 'log3' @() (Join-Path $Suite 'apps\vita3k\install.ps1')
Check 'the checkout has no program to install' { $rc -ne 0 -and (Log 'log3') -match 'No program' }
$rc = Run 'log3' @('--help')
Check '--help shows the usage' { $rc -eq 0 -and (Log 'log3') -match '(?m)^Installs Vita3K Manager' -and (Log 'log3') -match '--uninstall --purge' }
Check 'the installed app untouched' { Test-Path (Join-Path $A $Exe) }

Write-Host '== 4. uninstall keeps the settings and the log'
New-Item -ItemType Directory -Force -Path $AppHome, (Split-Path -Parent $Ini) | Out-Null
Set-Content -LiteralPath $Ini, (Join-Path $AppHome "$AppId.log") -Value 'x' -Encoding ascii
$rc = Run 'log4' @('--uninstall')
Check 'exit 0' { $rc -eq 0 }
Check 'app gone' { -not (Test-Path $A) }
Check 'Start-menu entry and its folder gone' { -not (Test-Path $Menu) -and -not (Test-Path $MenuDir) }
Check 'settings and log kept' { (Test-Path $Ini) -and (Test-Path (Join-Path $AppHome "$AppId.log")) }

Write-Host '== 5. reinstall, then uninstall --purge'
$rc = Run 'log5' @()
if ($rc -eq 0) { $rc = Run 'log5b' @('--uninstall', '--purge') }
Check 'exit 0' { $rc -eq 0 }
Check 'Desktop shortcut removed' { -not (Test-Path $Desk) }
Check 'settings and log removed' { -not (Test-Path $Ini) -and -not (Test-Path $AppHome) }
Check 'the empty suite folders removed' { -not (Test-Path (Join-Path $env:LOCALAPPDATA 'windows-portable-suite')) -and -not (Test-Path (Join-Path $env:APPDATA 'windows-portable-suite')) }

Write-Host '== 6. installed by hand from a download: the download removed on a yes, kept on a no'
$Dl = Join-Path $T 'downloads'
$Tag = Split-Path -Leaf $R
New-Item -ItemType Directory -Force -Path $Dl | Out-Null
Copy-Item -LiteralPath $R -Destination $Dl -Recurse
Set-Content -LiteralPath (Join-Path $Dl "$Tag.zip") -Value 'the zip' -Encoding ascii
Set-Content -LiteralPath (Join-Path $Dl 'SHA256SUMS') -Value "abc  $Tag.zip" -Encoding ascii
$env:WPS_REMOVE_DOWNLOAD = 'n'
$rc = Run 'log6' @() (Join-Path $Dl "$Tag\install.ps1")
Check 'exit 0, the download kept on a no' { $rc -eq 0 -and (Test-Path (Join-Path $Dl "$Tag.zip")) -and (Test-Path (Join-Path $Dl $Tag)) }
$env:WPS_REMOVE_DOWNLOAD = 'y'
$rc = Run 'log6b' @() (Join-Path $Dl "$Tag\install.ps1")
$env:WPS_REMOVE_DOWNLOAD = ''
Check 'exit 0, installed' { $rc -eq 0 -and (Test-Path (Join-Path $A $Exe)) }
Check 'the zip, its SHA256SUMS and the unpacked folder removed' { -not (Test-Path (Join-Path $Dl "$Tag.zip")) -and -not (Test-Path (Join-Path $Dl 'SHA256SUMS')) -and -not (Test-Path (Join-Path $Dl $Tag)) }

if ($script:fail -eq 0) {
    Write-Host 'ALL OK'
} else {
    Get-ChildItem -LiteralPath $T -Filter 'log*' | ForEach-Object { Write-Host "--- $($_.Name)"; Get-Content -LiteralPath $_.FullName | Write-Host }
}
exit $script:fail
