# Проверка окна Global Build раз в 5 минут (окно 14:00–01:00 МСК).
# Запускается задачей планировщика ZCode-GlobalBuild-Claim (см. install.ps1).

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python).Source
$intervalSec = 300          # каждые 5 минут
$windowStartHour = 14       # 14:00 МСК (11:00 UTC)
$windowEndHour   = 25       # до 01:00 МСК следующего дня

while ($true) {
    $now = Get-Date
    $h = $now.Hour
    # Claim — если текущее время внутри окна 14:00–01:00
    if (($h -ge $windowStartHour) -or ($h -lt ($windowEndHour - 24))) {
        & $py -X utf8 (Join-Path $root 'claim.py') | Out-Null
    }
    Start-Sleep -Seconds $intervalSec
}
