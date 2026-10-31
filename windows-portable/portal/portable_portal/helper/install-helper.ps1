# SPDX-License-Identifier: GPL-3.0-or-later
# Installs the portal's Operating Mode helper on the ROG Xbox Ally X (owner, 31-10-2026), as administrator: the
# portal starts it with one administrator prompt (the Operating Mode page's Watt limits row), and the portal's
# install.ps1 --uninstall starts the copy in Program Files to remove it.
#
#   powershell -ExecutionPolicy Bypass -File install-helper.ps1               # install or update
#   powershell -ExecutionPolicy Bypass -File install-helper.ps1 --uninstall   # remove it
#
# The suite's one part that runs as administrator (windows-portable/CLAUDE.md):
#  * C:\Program Files\windows-portable-suite\: operating-mode.ps1 (the helper) and this script, where only an
#    administrator may change them.
#  * C:\ProgramData\windows-portable-suite\: operating-mode, the mode the portal asks for (one letter, which users
#    may write and nothing else), and the helper's operating-mode-result and operating-mode.log (users may read).
#  * The scheduled task \Windows Portable Suite\Operating Mode: the helper as SYSTEM, when the portal starts it
#    (users may start it, nothing more), 5 s after every change of the power source (Kernel-Power 105), and 20 s
#    and 2 minutes after a sign-in, after Armoury Crate's services have applied its own mode at Windows' start.
$ErrorActionPreference = 'Stop'

$Suite = 'windows-portable-suite'
$Programs = Join-Path $env:ProgramFiles $Suite
$Data = Join-Path $env:ProgramData $Suite
$Request = Join-Path $Data 'operating-mode'
$TaskFolder = '\Windows Portable Suite\'
$TaskName = 'Operating Mode'
$Model = 'RC73XA'                                           # the ROG Xbox Ally X, as operating_mode.MODEL
# The task: SYSTEM and the administrators may do anything with it, every signed-in user may read and start it
$TaskSddl = 'D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;GRGX;;;AU)'

function Info($text) { Write-Host '==> ' -ForegroundColor Magenta -NoNewline; Write-Host $text }
function Die($text) { Write-Host "ERROR: $text" -ForegroundColor Red; Start-Sleep -Seconds 5; exit 1 }

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Die 'Run this as administrator: the helper writes the watt limits, which only an administrator may.'
}

if ($args -contains '--uninstall') {
    Info 'Removing the Operating Mode helper'
    Unregister-ScheduledTask -TaskPath $TaskFolder -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    try {
        $service = New-Object -ComObject Schedule.Service
        $service.Connect()
        $service.GetFolder('\').DeleteFolder($TaskFolder.Trim('\'), 0)
    } catch { }                                             # not there, or another task still in it
    foreach ($folder in $Data, $Programs) {
        if (Test-Path -LiteralPath $folder) { Remove-Item -LiteralPath $folder -Recurse -Force }
    }
    Info 'The Operating Mode helper is removed; Armoury Crate sets the watts again.'
    exit 0
}

$product = (Get-ItemProperty 'HKLM:\HARDWARE\DESCRIPTION\System\BIOS').SystemProductName
if ($product -notmatch $Model) { Die "This is not a ROG Xbox Ally X ($product): the helper's watt limits are the Ally X's." }

Info "Copying the helper to $Programs"
New-Item -ItemType Directory -Force -Path $Programs | Out-Null
foreach ($file in 'operating-mode.ps1', 'install-helper.ps1') {
    $from = Join-Path $PSScriptRoot $file
    $to = Join-Path $Programs $file
    if ($from -ne $to) { Copy-Item -LiteralPath $from -Destination $to -Force }
}

Info "Making $Data"
New-Item -ItemType Directory -Force -Path $Data | Out-Null
# Only SYSTEM and the administrators write in the folder; users read it, and write the request's letter, never
# make, delete or replace a file in it (the helper runs as SYSTEM and writes its result there)
& icacls.exe $Data /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null
if ($LASTEXITCODE) { Die "The rights of $Data were not set (icacls: $LASTEXITCODE)." }
if (-not (Test-Path -LiteralPath $Request)) { New-Item -ItemType File -Path $Request | Out-Null }
& icacls.exe $Request /grant '*S-1-5-32-545:(R,W)' | Out-Null
if ($LASTEXITCODE) { Die "The rights of $Request were not set (icacls: $LASTEXITCODE)." }

Info "Registering the task $TaskFolder$TaskName"
$script = Join-Path $Programs 'operating-mode.ps1'
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>The Windows Portable Suite's Operating Mode: the mode picked in the portal, its power plan, power mode and watt limits, again after every change of the power source and after a sign-in.</Description>
  </RegistrationInfo>
  <Triggers>
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>&lt;QueryList&gt;&lt;Query Id="0" Path="System"&gt;&lt;Select Path="System"&gt;*[System[Provider[@Name='Microsoft-Windows-Kernel-Power'] and EventID=105]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>
      <Delay>PT5S</Delay>
    </EventTrigger>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT20S</Delay>
    </LogonTrigger>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT2M</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>Queue</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT1M</ExecutionTimeLimit>
    <Priority>5</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$script"</Arguments>
    </Exec>
  </Actions>
</Task>
"@
Register-ScheduledTask -TaskPath $TaskFolder -TaskName $TaskName -Xml $xml -Force | Out-Null
$service = New-Object -ComObject Schedule.Service
$service.Connect()
$service.GetFolder($TaskFolder.TrimEnd('\')).GetTask($TaskName).SetSecurityDescriptor($TaskSddl, 0)
Info 'The Operating Mode helper is installed: a mode picked in the portal now sets its watts too.'
