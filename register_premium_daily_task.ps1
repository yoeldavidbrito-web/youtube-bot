param(
    [string]$TaskName = "YouTubeBotDailyPremiumPrivate",
    [string]$Time = "10:00"
)

$runner = "C:\Users\yoeld\Desktop\youtube bot.cmd"

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
