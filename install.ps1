# Установка ZCode Global Build auto-claim + watchdog.
# Запуск: pwsh -NoProfile -ExecutionPolicy Bypass -File install.ps1
# Требования: Windows 10/11, Python 3.10+, ZCode Desktop с залогиненным аккаунтом.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python).Source
$pwsh = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if (-not $pwsh) { throw "pwsh (PowerShell 7) не найден — установи с https://aka.ms/powershell" }

Write-Host "=== ZCode Global Build: установка ===" -ForegroundColor Cyan

# 1. Зависимости Python
Write-Host "[1/4] Проверяю зависимости Python..." -ForegroundColor Yellow
& $py -m pip install --quiet cryptography
if ($LASTEXITCODE -ne 0) { throw "pip install cryptography не удался" }

# 2. JWT из ZCode Desktop
Write-Host "[2/4] Извлекаю JWT из ZCode Desktop..." -ForegroundColor Yellow
& $py -X utf8 (Join-Path $root 'grab_jwt.py')
if ($LASTEXITCODE -ne 0) { throw "grab_jwt.py не удался — залогиньтесь в ZCode Desktop" }

# 3. Тестовый запуск claim
Write-Host "[3/4] Тестовый запуск claim.py..." -ForegroundColor Yellow
& $py -X utf8 (Join-Path $root 'claim.py')

# 4. Задачи планировщика
Write-Host "[4/4] Создаю задачи планировщика..." -ForegroundColor Yellow

$schedScript = (Join-Path $root 'run_scheduler.ps1').Replace("'", "''")
$wdScript = (Join-Path $root 'limit_watchdog.py').Replace("'", "''")

# 4a. Claim: бесконечный цикл run_scheduler.ps1, запускается при логоне
$actClaim = New-ScheduledTaskAction -Execute $pwsh `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File '$schedScript'"
$tClaim = New-ScheduledTaskTrigger -AtLogOn -User "$env:COMPUTERNAME\$env:USERNAME"
$setClaim = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)
Register-ScheduledTask -TaskName "ZCode-GlobalBuild-Claim" -Action $actClaim -Trigger $tClaim -Settings $setClaim `
    -Description "Автоматический claim Global Build в ZCode (окно 14:00-01:00 МСК)" -Force | Out-Null

# Запустить цикл сразу (не дожидаясь перелогина)
Start-Process $pwsh -WindowStyle Hidden -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $root 'run_scheduler.ps1')

# 4b. Watchdog: проверка баланса каждые 5 минут
$actWd = New-ScheduledTaskAction -Execute $py -Argument "-X utf8 `"$wdScript`""
$tWd = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
$tWd.Repetition.Duration = 'P365D'
$setWd = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "ZCode-Limit-Watchdog" -Action $actWd -Trigger $tWd -Settings $setWd `
    -Description "Мониторинг лимитов ZCode; при исчерпании 2 проверки подряд выключает ПК (единоразово)" -Force | Out-Null

Write-Host ""
Write-Host "=== Готово! ===" -ForegroundColor Green
Write-Host "Claim-цикл:  фоновый процесс + задача ZCode-GlobalBuild-Claim (при логоне)."
Write-Host "Watchdog:    задача ZCode-Limit-Watchdog (каждые 5 минут)."
Write-Host "Логи:        claim.log, watchdog.log в папке $root"
Write-Host "Отмена выключения: shutdown /a"
Write-Host ""
Write-Host "Внимание: автовыключение ПК при исчерпании лимитов ВКЛЮЧЕНО." -ForegroundColor Magenta
Write-Host "Если не нужно — удали задачу: schtasks /change /tn ZCode-Limit-Watchdog /disable"
