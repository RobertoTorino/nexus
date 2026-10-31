# SPDX-License-Identifier: GPL-3.0-or-later
# The Operating Mode helper of the Windows Portable Suite on the ROG Xbox Ally X (owner, 31-10-2026). The scheduled
# task \Windows Portable Suite\Operating Mode runs it as SYSTEM from C:\Program Files\windows-portable-suite\, where
# the user cannot change it, when the portal asks (A on a mode of its Operating Mode page) and a few seconds after
# every change of the power source (Kernel-Power 105), after Armoury Crate has applied its own mode for it, and 20 s
# and 2 minutes after a sign-in, after Armoury Crate's services have applied theirs at Windows' start (owner,
# 31-10-2026: the portal's mode after a restart too).
#
# It applies the whole mode the portal recorded: the power plan, Windows' power mode, and the three watt limits only
# an administrator may write (ASUS WMI, AsusAtkWmi_WMNB's DEVS), for the power source the device is on now. The
# portal only names the mode, one letter (S, P, T or W) in C:\ProgramData\windows-portable-suite\operating-mode;
# the values are this script's own table, the owner's measurements (MIGRATION.md, 31-10-2026; the portal's
# operating_mode.py holds the same, a test keeps them equal). What it did goes in operating-mode-result (one line,
# for the portal) and operating-mode.log beside it, which only an administrator may write.
$ErrorActionPreference = 'Stop'

$Data = Join-Path $env:ProgramData 'windows-portable-suite'
$Request = Join-Path $Data 'operating-mode'
$Result = Join-Path $Data 'operating-mode-result'
$Log = Join-Path $Data 'operating-mode.log'

$Balanced = '00000000-0000-0000-0000-000000000000'
$Efficiency = '961cc777-2547-4f9d-8174-7d86181b8a7a'
$Performance = 'ded574b5-45a0-4f42-8737-46345c09c238'
# Sustained, slow and fast watts on the charger and on battery
$Modes = @{
    S = @{ Name = 'Silent'; Plan = '64a64f24-65b9-4b56-befd-5ec1eaced9b3'; Overlay = $Efficiency
           Charger = @(13, 16, 20); Battery = @(13, 16, 20) }
    P = @{ Name = 'Performance'; Plan = '27fa6203-3987-4dcc-918d-748559d549ec'; Overlay = $Balanced
           Charger = @(17, 21, 26); Battery = @(17, 21, 26) }
    T = @{ Name = 'Turbo'; Plan = '6fecc5ae-f350-48a5-b669-b472cb895ccf'; Overlay = $Performance
           Charger = @(35, 44, 55); Battery = @(25, 30, 36) }
    W = @{ Name = 'Windows'; Plan = '381b4222-f694-41f0-9685-ff5bb260df2e'; Overlay = $null
           Charger = @(17, 21, 26); Battery = @(17, 21, 26) }
}
$Devices = @(0x001200A3, 0x001200A0, 0x001200C1)           # DEVS: sustained, slow and fast limit; result 1 = taken

function Write-Log($text) {
    $line = '{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $text
    $old = @()
    if (Test-Path -LiteralPath $Log) { $old = @(Get-Content -LiteralPath $Log -Tail 199) }
    Set-Content -LiteralPath $Log -Value ($old + $line) -Encoding UTF8
}

function Write-Result($text) {
    Set-Content -LiteralPath $Result -Value $text -Encoding UTF8 -NoNewline
    Write-Log $text
}

Add-Type -Namespace WindowsPortableSuite -Name Power -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern bool GetSystemPowerStatus([In, Out] byte[] status);
[DllImport("powrprof.dll")] public static extern uint PowerSetActiveScheme(IntPtr root, ref Guid scheme);
[DllImport("powrprof.dll")] public static extern uint PowerSetActiveOverlayScheme(ref Guid overlay);
'@

try {
    $letter = ''
    if (Test-Path -LiteralPath $Request) { $letter = ([string](Get-Content -LiteralPath $Request -Raw)).Trim() }
    if (-not $letter) { exit 0 }                         # no mode picked in the portal yet: Armoury Crate's stays
    if ($letter -cnotin @($Modes.Keys)) { Write-Result "? not a mode: $($letter.Substring(0, [Math]::Min(8, $letter.Length)))"; exit 1 }
    $mode = $Modes[$letter]

    $status = New-Object byte[] 12                         # SYSTEM_POWER_STATUS; ACLineStatus first, 1 = on the charger
    $charger = -not [WindowsPortableSuite.Power]::GetSystemPowerStatus($status) -or $status[0] -ne 0
    if ($charger) { $watts = $mode.Charger; $source = 'charger' } else { $watts = $mode.Battery; $source = 'battery' }

    $plan = [Guid]$mode.Plan
    if ([WindowsPortableSuite.Power]::PowerSetActiveScheme([IntPtr]::Zero, [ref]$plan)) { throw "the power plan was not taken" }
    if ($mode.Overlay) {
        $overlay = [Guid]$mode.Overlay
        if ([WindowsPortableSuite.Power]::PowerSetActiveOverlayScheme([ref]$overlay)) { throw "the power mode was not taken" }
    }

    $wmi = Get-CimInstance -Namespace root/wmi -ClassName AsusAtkWmi_WMNB | Select-Object -First 1
    if (-not $wmi) { throw 'no ASUS WMI (AsusAtkWmi_WMNB)' }
    # Written twice when a limit is not taken the first time: the firmware may refuse a limit above the next one
    # until that one is raised too
    foreach ($pass in 1, 2) {
        $refused = @()
        for ($i = 0; $i -lt 3; $i++) {
            $out = Invoke-CimMethod -InputObject $wmi -MethodName DEVS -Arguments @{
                Device_ID = [uint32]$Devices[$i]; Control_status = [uint32]$watts[$i] }
            if ($out.result -ne 1) { $refused += ('0x{0:X8}' -f $Devices[$i]) }
        }
        if (-not $refused) { break }
    }
    $shown = $watts -join ' / '
    if ($refused) { throw "the firmware did not take $($refused -join ', ') ($shown W)" }
    Write-Result "$letter ok $source $shown W"
    exit 0
} catch {
    Write-Result "$letter failed $($_.Exception.Message)"
    exit 1
}
