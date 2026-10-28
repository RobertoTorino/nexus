# SPDX-License-Identifier: GPL-3.0-or-later
# Exercise portal/install.ps1: install from a release folder (the portal and, from its bundle, Windows Portable Test
# through its own installer, without a Desktop shortcut, recorded in installed.json), an update without the Desktop
# shortcut, the refusals (administrator, --purge and --all alone, an unknown option, the checkout without a built
# program, a bundle that does not match its SHA256SUMS), uninstall (the test app goes with the portal, another app
# the portal installed stays and is named; settings, log and records kept), --uninstall --all --purge. The user's
# folders are a temp folder's: LOCALAPPDATA, APPDATA and the Desktop (WPS_DESKTOP_DIR); WPS_ELEVATED stands in for
# the administrator check, since CI's runner is one.
# Also an update while a window has the program folder as its working directory, and a program running from it,
# which is refused with nothing changed, and an install by hand from a download (the download removed on a yes).
#
#   powershell -ExecutionPolicy Bypass -File windows-portable\tools\installer-tests\portal.ps1
#   ... portal.ps1 -Release dist\wp-portal-v0.1.0.zip   # the built release (with the real bundle) instead of a stand-in
param([string]$Release = '')
$ErrorActionPreference = 'Stop'
$Suite = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$T = Join-Path ([IO.Path]::GetTempPath()) 'windows-portable-portal-installer'
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
$Exe = 'Windows-Portable-Suite.exe'
$SuiteHome = Join-Path $env:LOCALAPPDATA 'windows-portable-suite'
$PortalHome = Join-Path $SuiteHome 'portal'
$A = Join-Path $PortalHome 'app'
$Releases = Join-Path $PortalHome 'releases'
$Records = Join-Path $PortalHome 'installed.json'
$Ini = Join-Path $env:APPDATA 'windows-portable-suite\portal.ini'
$TestApp = Join-Path $SuiteHome 'windows-portable-test\app'
$MenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Windows Portable Suite'
$Menu = Join-Path $MenuDir 'Windows Portable Suite.lnk'
$TestMenu = Join-Path $MenuDir 'Windows Portable Test.lnk'
$Desk = Join-Path $env:WPS_DESKTOP_DIR 'Windows Portable Suite.lnk'
$TestDesk = Join-Path $env:WPS_DESKTOP_DIR 'Windows Portable Test.lnk'

# The release folder: the built one, or a stand-in with the same layout: program\ with the exe and _internal\, and
# bundle\ with a stand-in Windows Portable Test release (its real install.ps1) and SHA256SUMS.
if ($Release) {
    Expand-Archive -LiteralPath $Release -DestinationPath (Join-Path $T 'release')
    $R = (Get-ChildItem -LiteralPath (Join-Path $T 'release') -Directory | Select-Object -First 1).FullName
} else {
    $R = Join-Path $T 'release\wp-portal-v0.0.0'
    New-Item -ItemType Directory -Force -Path (Join-Path $R 'program\_internal'), (Join-Path $R 'bundle') | Out-Null
    Set-Content -LiteralPath (Join-Path $R "program\$Exe") -Value 'stand-in' -Encoding ascii
    Set-Content -LiteralPath (Join-Path $R 'program\_internal\marker.txt') -Value 'marker' -Encoding ascii
    Copy-Item -LiteralPath (Join-Path $Suite 'portal\install.ps1'), (Join-Path $Suite 'portal\LICENSE') -Destination $R
    $TestRelease = Join-Path $T 'stand-in\wp-test-v0.0.0'
    New-Item -ItemType Directory -Force -Path (Join-Path $TestRelease 'program\_internal') | Out-Null
    Set-Content -LiteralPath (Join-Path $TestRelease 'program\Windows-Portable-Test.exe') -Value 'stand-in' -Encoding ascii
    Set-Content -LiteralPath (Join-Path $TestRelease 'program\_internal\marker.txt') -Value 'marker' -Encoding ascii
    Copy-Item -LiteralPath (Join-Path $Suite 'apps\test\install.ps1'), (Join-Path $Suite 'apps\test\LICENSE') -Destination $TestRelease
    $Zip = Join-Path $R 'bundle\wp-test-v0.0.0.zip'
    Compress-Archive -Path $TestRelease -DestinationPath $Zip
    $hash = (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToLower()
    Set-Content -LiteralPath (Join-Path $R 'bundle\SHA256SUMS') -Value "$hash  wp-test-v0.0.0.zip" -Encoding ascii
}
$Installer = Join-Path $R 'install.ps1'
$TestTag = (Get-ChildItem -LiteralPath (Join-Path $R 'bundle') -Filter 'wp-test-v*.zip' | Select-Object -First 1).BaseName

function Run($log, [string[]]$options, $installer = $Installer) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer @options *> (Join-Path $T $log)
    return $LASTEXITCODE
}
function Log($log) { Get-Content -Raw -LiteralPath (Join-Path $T $log) }
function Target($link) { (New-Object -ComObject WScript.Shell).CreateShortcut($link).TargetPath }
function RecordOf($key) {
    if (-not (Test-Path -LiteralPath $Records)) { return $null }
    $data = Get-Content -Raw -LiteralPath $Records | ConvertFrom-Json
    return $data.$key
}

Write-Host '== 1. install from the release folder: the portal and the bundled test app'
New-Item -ItemType Directory -Force -Path $env:WPS_DESKTOP_DIR | Out-Null
Set-Content -LiteralPath $TestDesk -Value 'the shortcut an older portal made' -Encoding ascii
$rc = Run 'log1' @()
Check 'exit 0' { $rc -eq 0 }
Check 'program copied with its _internal folder' { (Test-Path (Join-Path $A $Exe)) -and (Test-Path (Join-Path $A '_internal')) }
Check 'LICENSE copied, install.ps1 not' { (Test-Path (Join-Path $A 'LICENSE')) -and -not (Test-Path (Join-Path $A 'install.ps1')) }
Check 'Start-menu entry starts the installed exe' { (Test-Path $Menu) -and ((Target $Menu) -eq (Join-Path $A $Exe)) }
Check 'Desktop shortcut' { (Test-Path $Desk) -and ((Target $Desk) -eq (Join-Path $A $Exe)) }
Check 'the test app installed through its own installer' { (Test-Path $TestApp) -and (Get-ChildItem -LiteralPath $TestApp -Filter '*.exe') -and (Test-Path $TestMenu) -and -not (Test-Path $TestDesk) }
Check 'its release kept for the portal, complete' { (Test-Path (Join-Path $Releases "$TestTag\install.ps1")) -and (Test-Path (Join-Path $Releases "$TestTag\.complete")) }
Check 'recorded in installed.json without a byte order mark' { ((RecordOf 'test') -eq $TestTag) -and ([IO.File]::ReadAllBytes($Records)[0] -eq 0x7B) }

Write-Host '== 2. update without the Desktop shortcut'
Set-Content -LiteralPath (Join-Path $A 'stale.txt') -Value 'from an older release' -Encoding ascii
New-Item -ItemType Directory -Force -Path (Join-Path $Releases 'wp-test-v0.0.0-old') | Out-Null
$rc = Run 'log2' @('--no-desktop-shortcut')
Check 'exit 0' { $rc -eq 0 }
Check 'the old program replaced, nothing left over' { -not (Test-Path (Join-Path $A 'stale.txt')) -and -not (Test-Path "$A.new") }
Check 'Desktop shortcuts removed, Start-menu entries kept' { -not (Test-Path $Desk) -and -not (Test-Path $TestDesk) -and (Test-Path $Menu) -and (Test-Path $TestMenu) }
Check 'the record kept' { (RecordOf 'test') -eq $TestTag }

Write-Host '== 2b. update while a window has the program folder as its working directory (an older portal''s update)'
$holder = Start-Process powershell.exe -ArgumentList '-NoProfile', '-Command', 'Start-Sleep 60' -WorkingDirectory $A -WindowStyle Hidden -PassThru
Start-Sleep -Milliseconds 1500
Set-Content -LiteralPath (Join-Path $A 'stale.txt') -Value 'from an older release' -Encoding ascii
$rc = Run 'log2b' @('--no-desktop-shortcut')
Stop-Process -Id $holder.Id -Force -ErrorAction SilentlyContinue
Check 'exit 0' { $rc -eq 0 }
Check 'the new program in place, the old one and the staging folders gone' { (Test-Path (Join-Path $A $Exe)) -and (Test-Path (Join-Path $A '_internal')) -and -not (Test-Path (Join-Path $A 'stale.txt')) -and -not (Test-Path "$A.new") -and -not (Test-Path "$A.old") }

Write-Host '== 2c. a program running from the folder is not replaced'
Copy-Item -LiteralPath (Join-Path $env:WINDIR 'System32\PING.EXE') -Destination (Join-Path $A 'running.exe')
$running = Start-Process (Join-Path $A 'running.exe') -ArgumentList '-n', '60', '127.0.0.1' -WindowStyle Hidden -PassThru
Start-Sleep -Milliseconds 800
$rc = Run 'log2c' @('--no-desktop-shortcut')
Stop-Process -Id $running.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
Check 'refused: close it first' { $rc -ne 0 -and (Log 'log2c') -match 'close .* first' }
Check 'the installed program untouched' { (Test-Path (Join-Path $A $Exe)) -and (Test-Path (Join-Path $A 'running.exe')) -and -not (Test-Path "$A.new") }
Remove-Item -LiteralPath (Join-Path $A 'running.exe') -Force

Write-Host '== 3. refusals'
$env:WPS_ELEVATED = '1'
$rc = Run 'log3' @()
$env:WPS_ELEVATED = '0'
Check 'administrator refused' { $rc -ne 0 -and (Log 'log3') -match 'not as administrator' }
$rc = Run 'log3' @('--purge')
Check '--purge alone refused' { $rc -ne 0 -and (Log 'log3') -match 'only goes with --uninstall' }
$rc = Run 'log3' @('--all')
Check '--all alone refused' { $rc -ne 0 -and (Log 'log3') -match '--all only goes with --uninstall' }
$rc = Run 'log3' @('--bogus')
Check 'unknown option refused' { $rc -ne 0 -and (Log 'log3') -match 'Unknown option: --bogus' }
$rc = Run 'log3' @() (Join-Path $Suite 'portal\install.ps1')
Check 'the checkout has no program to install' { $rc -ne 0 -and (Log 'log3') -match 'No program' }
$rc = Run 'log3' @('--help')
Check '--help shows the usage' { $rc -eq 0 -and (Log 'log3') -match "(?m)^Installs the Windows Portable Suite's portal" -and (Log 'log3') -match '--uninstall --all' }
$Sums = Join-Path $R 'bundle\SHA256SUMS'
$saved = Get-Content -Raw -LiteralPath $Sums
Set-Content -LiteralPath $Sums -Value ('0' * 64 + "  $TestTag.zip") -Encoding ascii
$rc = Run 'log3' @()
Set-Content -LiteralPath $Sums -Value $saved -NoNewline -Encoding ascii
Check 'a bundle that does not match SHA256SUMS refused before anything changes' { $rc -ne 0 -and (Log 'log3') -match 'does not match bundle' }
Check 'the installed suite untouched' { (Test-Path (Join-Path $A $Exe)) -and (Test-Path $TestApp) }

Write-Host '== 4. uninstall takes the test app along, names the other app, keeps settings, log and records'
$Other = Join-Path $Releases 'wp-other-v0.1.0'
New-Item -ItemType Directory -Force -Path $Other, (Join-Path $SuiteHome 'windows-portable-other'), (Split-Path -Parent $Ini) | Out-Null
Set-Content -LiteralPath (Join-Path $Other 'install.ps1') -Encoding ascii -Value @'
if ($args -contains '--uninstall') { Remove-Item -Recurse -Force (Join-Path $env:LOCALAPPDATA 'windows-portable-suite\windows-portable-other') }
'@
[IO.File]::WriteAllText($Records, ('{"test": "' + $TestTag + '", "other": "wp-other-v0.1.0"}'))
Set-Content -LiteralPath $Ini, (Join-Path $PortalHome 'portal.log') -Value 'x' -Encoding ascii
$rc = Run 'log4' @('--uninstall')
Check 'exit 0' { $rc -eq 0 }
Check 'portal gone' { -not (Test-Path $A) -and -not (Test-Path $Menu) }
Check 'the test app gone with it, its release folder too' { -not (Test-Path $TestApp) -and -not (Test-Path $TestMenu) -and -not (Test-Path (Join-Path $Releases $TestTag)) }
Check 'the other app kept and named' { (Test-Path (Join-Path $SuiteHome 'windows-portable-other')) -and (Log 'log4') -match 'Still installed.*other \(wp-other-v0.1.0\)' }
Check 'settings, log and the records kept, the test app no longer recorded' { (Test-Path $Ini) -and (Test-Path (Join-Path $PortalHome 'portal.log')) -and ((RecordOf 'other') -eq 'wp-other-v0.1.0') -and ($null -eq (RecordOf 'test')) }

Write-Host '== 5. reinstall, then uninstall --all --purge'
$rc = Run 'log5' @()
if ($rc -eq 0) { $rc = Run 'log5b' @('--uninstall', '--all', '--purge') }
Check 'exit 0' { $rc -eq 0 }
Check 'the other app removed through its installer' { -not (Test-Path (Join-Path $SuiteHome 'windows-portable-other')) }
Check 'settings, log, records and releases removed' { -not (Test-Path $Ini) -and -not (Test-Path $PortalHome) }
Check 'the empty suite folders removed' { -not (Test-Path $SuiteHome) -and -not (Test-Path (Join-Path $env:APPDATA 'windows-portable-suite')) -and -not (Test-Path $MenuDir) }

Write-Host '== 6. installed by hand from a download: the download removed on a yes, kept on a no'
$Dl = Join-Path $T 'downloads'
$Tag = Split-Path -Leaf $R
New-Item -ItemType Directory -Force -Path $Dl | Out-Null
Copy-Item -LiteralPath $R -Destination $Dl -Recurse
Set-Content -LiteralPath (Join-Path $Dl "$Tag.zip") -Value 'the zip' -Encoding ascii
Set-Content -LiteralPath (Join-Path $Dl 'SHA256SUMS (1)') -Value "abc  $Tag.zip" -Encoding ascii     # a second download
Set-Content -LiteralPath (Join-Path $Dl 'SHA256SUMS') -Value 'def  wp-other-v1.0.0.zip' -Encoding ascii
$env:WPS_REMOVE_DOWNLOAD = 'n'
$rc = Run 'log6' @() (Join-Path $Dl "$Tag\install.ps1")
Check 'exit 0, the download kept on a no' { $rc -eq 0 -and (Test-Path (Join-Path $Dl "$Tag.zip")) -and (Test-Path (Join-Path $Dl $Tag)) }
$env:WPS_REMOVE_DOWNLOAD = 'y'
$rc = Run 'log6b' @() (Join-Path $Dl "$Tag\install.ps1")
$env:WPS_REMOVE_DOWNLOAD = ''
Check 'exit 0, installed' { $rc -eq 0 -and (Test-Path (Join-Path $A $Exe)) }
Check 'the zip, its SHA256SUMS and the unpacked folder removed' { -not (Test-Path (Join-Path $Dl "$Tag.zip")) -and -not (Test-Path (Join-Path $Dl 'SHA256SUMS (1)')) -and -not (Test-Path (Join-Path $Dl $Tag)) }
Check 'another release''s SHA256SUMS kept' { Test-Path (Join-Path $Dl 'SHA256SUMS') }

if ($script:fail -eq 0) {
    Write-Host 'ALL OK'
} else {
    Get-ChildItem -LiteralPath $T -Filter 'log*' | ForEach-Object { Write-Host "--- $($_.Name)"; Get-Content -LiteralPath $_.FullName | Write-Host }
}
exit $script:fail
