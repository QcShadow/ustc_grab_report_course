param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "SilentlyContinue"

$Root = (Resolve-Path $Root).Path
$ReportTask = "USTC-Grab-Report"
$KeepaliveTask = "USTC-Grab-Keepalive"

Stop-ScheduledTask -TaskName $ReportTask -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName $KeepaliveTask -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $ReportTask -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $KeepaliveTask -Confirm:$false -ErrorAction SilentlyContinue

Write-Output "OK: scheduled tasks removed (config and data kept in $Root)"
