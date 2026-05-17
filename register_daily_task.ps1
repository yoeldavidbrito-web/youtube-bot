param(
    [string]$TaskName = "YouTubeBotDaily3",
    [string]$Time = "09:00"
)

$baseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $baseDir "run_daily_3_videos.cmd"

if (-not (Test-Path $runner)) {
    throw "No existe el runner esperado: $runner"
}

schtasks /Create `
    /F `
    /SC DAILY `
    /ST $Time `
    /TN $TaskName `
    /TR "`"$runner`""

Write-Host "Tarea creada: $TaskName"
Write-Host "Hora diaria: $Time"
Write-Host "Runner: $runner"
