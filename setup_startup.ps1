# setup_startup.ps1 – Register Eden as a silent Windows logon task
# Run this script once from an elevated PowerShell prompt.
# It schedules Eden to start 15 seconds after logon using pythonw.exe
# (no console window).

$ErrorActionPreference = "Stop"

# Resolve paths relative to this script's location
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Pythonw    = Join-Path $ScriptDir ".venv\Scripts\pythonw.exe"
$MainPy     = Join-Path $ScriptDir "main.py"
$TaskName   = "EdenVoiceAssistant"
$LogFile    = Join-Path $ScriptDir "eden_startup.log"

if (-not (Test-Path $Pythonw)) {
    Write-Error "pythonw.exe not found at: $Pythonw`nRun 'python -m venv .venv' and install requirements first."
    exit 1
}

# Remove any previous registration
schtasks /delete /tn $TaskName /f 2>$null | Out-Null

# Build the action: 15-second delay then launch silently
$Action = New-ScheduledTaskAction `
    -Execute $Pythonw `
    -Argument "`"$MainPy`"" `
    -WorkingDirectory $ScriptDir

# Trigger: at logon of current user, with a 15-second delay
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Trigger.Delay = "PT15S"   # ISO 8601 duration – 15 seconds

# Settings: run only when user is logged in, no time limit, hidden
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -MultipleInstances IgnoreNew `
    -Hidden

# Principal: run as current user, only when logged in
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName   $TaskName `
    -Action     $Action `
    -Trigger    $Trigger `
    -Settings   $Settings `
    -Principal  $Principal `
    -Description "Eden Voice Assistant – starts silently 15 s after logon." `
    -Force

Write-Host ""
Write-Host "✅ Task '$TaskName' registered successfully." -ForegroundColor Green
Write-Host "   Eden will start silently 15 seconds after each Windows logon."
Write-Host "   To remove: schtasks /delete /tn $TaskName /f"
