# SPDX-License-Identifier: GPL-3.0-or-later
# The portal checks of a release of the Windows Portable Suite, as Nexus Releases' buttons run them on the handheld
# (Windows), as the BC250 suite's check-release.sh does on the board:
#
#   check-release.ps1 local              # before the push: start the portal from this checkout; it installs the
#                                        # apps apps.toml pins from their GitHub releases (Test app updates, and
#                                        # Test withdrawal: a withdrawn app it finds installed it removes)
#   check-release.ps1 release [TAG]      # after the release workflow built the portal: download the published
#                                        # portal release (default wp-portal-v<portal\VERSION>), check it against its
#                                        # SHA256SUMS, install it and start it, so the handheld runs the release again
#   check-release.ps1 installer          # every installer test of the suite (tools\installer-tests\*.ps1), in turn
#   ... --no-start                       # install only, do not start the portal
#
# The release is downloaded into %TEMP%\wps-release-check\, emptied first. WPS_RELEASE_URL overrides the download
# address (tests).
$ErrorActionPreference = 'Stop'
$Suite = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path        # the suite's folder: portal\VERSION, portal\run.ps1
$Url = if ($env:WPS_RELEASE_URL) { $env:WPS_RELEASE_URL } else { 'https://github.com/RobertoTorino/nexus/releases/download' }
$Cache = Join-Path $env:TEMP 'wps-release-check'
$Program = Join-Path $env:LOCALAPPDATA 'windows-portable-suite\portal\app\Windows-Portable-Suite.exe'

function Info([string]$Text) { Write-Host "==> $Text" -ForegroundColor Magenta }
function Die([string]$Text) { Write-Host "ERROR: $Text" -ForegroundColor Red; exit 1 }

$Mode = if ($args.Count -gt 0) { [string]$args[0] } else { '' }
$Tag = ''
$Start = $true
foreach ($arg in ($args | Select-Object -Skip 1)) {
    switch -Wildcard ([string]$arg) {
        '--no-start' { $Start = $false }
        'wp-portal-v*' { $Tag = [string]$arg }
        default { Die "Unknown argument: $arg (see the top of $PSCommandPath)" }
    }
}

switch ($Mode) {
    'local' {
        Info "Starting the portal from this checkout ($Suite)"
        if (-not $Start) { exit 0 }
        & (Join-Path $Suite 'portal\run.ps1')
        exit $LASTEXITCODE
    }
    'release' {
        if (-not $Tag) {
            $version = (Get-Content -LiteralPath (Join-Path $Suite 'portal\VERSION') -Raw).Trim()
            $Tag = "wp-portal-v$version"
        }
        if (Test-Path -LiteralPath $Cache) { Remove-Item -LiteralPath $Cache -Recurse -Force }
        New-Item -ItemType Directory -Path $Cache | Out-Null
        Info "Downloading $Tag"
        $ProgressPreference = 'SilentlyContinue'                    # the progress bar slows the download down
        foreach ($name in "$Tag.zip", 'SHA256SUMS') {
            Invoke-WebRequest -Uri "$Url/$Tag/$name" -OutFile (Join-Path $Cache $name) -UseBasicParsing
        }
        $zip = Join-Path $Cache "$Tag.zip"
        $line = Get-Content -LiteralPath (Join-Path $Cache 'SHA256SUMS') | Where-Object { $_ -match "\s\*?$([regex]::Escape("$Tag.zip"))$" } |
            Select-Object -First 1
        if (-not $line) { Die "SHA256SUMS has no line for $Tag.zip" }
        $expected = (-split $line)[0].ToLower()
        $actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower()
        if ($actual -ne $expected) { Die "$Tag.zip does not match its SHA256SUMS ($actual)" }
        Info "Checked against SHA256SUMS: $actual"
        Expand-Archive -LiteralPath $zip -DestinationPath $Cache -Force
        Info "Installing $Tag"
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Cache "$Tag\install.ps1")
        if ($LASTEXITCODE -ne 0) { Die "Its install.ps1 ended with $LASTEXITCODE" }
        if (-not $Start) { exit 0 }
        Info "Starting the installed portal"
        Start-Process -FilePath $Program
        exit 0
    }
    'installer' {
        $failed = @()
        foreach ($test in Get-ChildItem -Path (Join-Path $Suite 'tools\installer-tests') -Filter '*.ps1' | Sort-Object Name) {
            Info "Installer test: $($test.Name)"
            & powershell -NoProfile -ExecutionPolicy Bypass -File $test.FullName
            if ($LASTEXITCODE -ne 0) { $failed += $test.Name }
        }
        if ($failed) { Die "Failed: $($failed -join ', ')" }
        Info 'Every installer test passed.'
        exit 0
    }
    default { Die "Usage: check-release.ps1 local | release [wp-portal-vX.Y.Z] | installer [--no-start]" }
}
