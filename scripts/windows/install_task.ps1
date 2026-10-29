param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [int]$IntervalMinutes = 2,
  [switch]$EnableKeepalive
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path $Root).Path
$ReportTask = "USTC-Grab-Report"
$KeepaliveTask = "USTC-Grab-Keepalive"

$python = Join-Path $Root "venv\Scripts\pythonw.exe"
if (-not (Test-Path $python)) {
  $python = Join-Path $Root "venv\Scripts\python.exe"
}
if (-not (Test-Path $python)) {
  throw "找不到 venv Python，请先运行 setup_windows.bat。"
}

$runner = Join-Path $Root "scripts\run_job.py"
if (-not (Test-Path $runner)) {
  throw "找不到 scripts\run_job.py。"
}

if ($IntervalMinutes -lt 1) { $IntervalMinutes = 1 }

function Register-ReportTask {
  param(
    [string]$Name,
    [string]$Script,
    [int]$Minutes,
    [string]$Description
  )

  $action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument ('"{0}" {1}' -f $runner, $Script) `
    -WorkingDirectory $Root

  $trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $Minutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

  $settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

  $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
  $principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited

  Register-ScheduledTask `
    -TaskName $Name `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description $Description `
    -Force | Out-Null
}

Register-ReportTask `
  -Name $ReportTask `
  -Script "main" `
  -Minutes $IntervalMinutes `
  -Description "USTC report grabber: detect every $IntervalMinutes minute(s)"

if ($EnableKeepalive) {
  Register-ReportTask `
    -Name $KeepaliveTask `
    -Script "keepalive" `
    -Minutes 30 `
    -Description "USTC report grabber: optional keepalive (withdraw and re-grab)"
} else {
  Unregister-ScheduledTask -TaskName $KeepaliveTask -Confirm:$false -ErrorAction SilentlyContinue
}

Write-Output "OK: $ReportTask every $IntervalMinutes minute(s)"
if ($EnableKeepalive) {
  Write-Output "OK: $KeepaliveTask every 30 minute(s)"
}
