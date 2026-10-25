# Install on Windows (x86_64): Soloist, the display server, the daily updater
# and the display itself as scheduled tasks of the current user. Needs Python 3
# (python.org or `winget install Python.Python.3.13`) and Chrome or Edge.
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#   powershell -ExecutionPolicy Bypass -File install.ps1 -NoAutostart
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall
param([switch]$NoAutostart, [switch]$Uninstall)
$ErrorActionPreference = "Stop"

$Repo = $PSScriptRoot
$App = Join-Path $env:LOCALAPPDATA "soloist-display"
$Bin = Join-Path $App "bin\soloist.exe"
$Config = Join-Path $env:APPDATA "soloist-display\soloist.env"
$TaskPath = "\soloist-display\"

if ($Uninstall) {
    Get-ScheduledTask -TaskPath $TaskPath -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-ScheduledTask -TaskName $_.TaskName -TaskPath $TaskPath
        Unregister-ScheduledTask -TaskName $_.TaskName -TaskPath $TaskPath -Confirm:$false
    }
    Write-Host "Removed the scheduled tasks. Settings and Soloist stay in $App and $Config."
    exit 0
}

# The real interpreter, not the Microsoft Store alias; pythonw runs without a console window.
$python = $null
if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    $python = (& py.exe -3 -c "import sys; print(sys.executable)").Trim()
} elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
    $python = (& python.exe -c "import sys; print(sys.executable)").Trim()
}
if (-not $python) { throw "Python 3 is required: winget install Python.Python.3.13" }
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"

if (-not (Test-Path $Config)) {
    New-Item -ItemType Directory -Force (Split-Path $Config) | Out-Null
    (Get-Content (Join-Path $Repo "soloist\soloist.env.example")) `
        -replace "^SOLOIST_DEVICE_NAME=.*", "SOLOIST_DEVICE_NAME=$env:COMPUTERNAME" |
        Set-Content -Encoding utf8 $Config
    Write-Host "!! Put the Soloist API key in $Config, then run this again"
    exit 1
}

& $python (Join-Path $Repo "soloist\update.py") --bin $Bin --restart pid --force
if ($LASTEXITCODE -ne 0) { throw "could not install Soloist" }

function Add-Task($Name, $Script, $Arguments, $Triggers, [switch]$KeepRunning, [switch]$Start) {
    $action = New-ScheduledTaskAction -Execute $pythonw -WorkingDirectory $Repo `
        -Argument ("`"{0}`" {1}" -f (Join-Path $Repo $Script), $Arguments)
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
    if ($KeepRunning) {
        $settings.RestartCount = 999
        $settings.RestartInterval = "PT1M"
    }
    Register-ScheduledTask -TaskName $Name -TaskPath $TaskPath -Action $action -Trigger $Triggers `
        -Settings $settings -Force | Out-Null
    if ($Start) { Start-ScheduledTask -TaskName $Name -TaskPath $TaskPath }
}

$logon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$daily = New-ScheduledTaskTrigger -Daily -At "05:30"

Add-Task "Soloist" "soloist\run.py" "--bin `"$Bin`" --config `"$Config`"" $logon -KeepRunning -Start
Add-Task "Display server" "display\server.py" "--port 8787" $logon -KeepRunning -Start
Add-Task "Soloist update" "soloist\update.py" "--bin `"$Bin`" --restart pid" @($daily, $logon)
if (-not $NoAutostart) { Add-Task "Display" "display\open.py" "" $logon -Start }

Write-Host "Installed. Open the display any time: $python `"$Repo\display\open.py`""
