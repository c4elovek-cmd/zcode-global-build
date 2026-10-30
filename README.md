# ZCode Global Build — авто-claim + мониторинг лимитов

Набор скриптов для автоматического получения бесплатного промо-плана **Global Build**
(GLM-5.3-Flash, 300M токенов) в [ZCode](https://zcode.z.ai) и опционального
автовыключения ПК, когда лимиты исчерпаны.

> Работает на Windows 10/11. Требуется установленный и залогиненный **ZCode Desktop**.

## Что делает

| Скрипт | Назначение |
|---|---|
| `grab_jwt.py` | Извлекает JWT/api-key/device_mid из зашифрованного `credentials.json` ZCode Desktop → `config.json` |
| `claim.py` | Забирает доступный промо-план через `POST /billing/claim` (окно 14:00–01:00 МСК) |
| `run_scheduler.ps1` | Бесконечный цикл: вызывает `claim.py` каждые 5 минут внутри окна |
| `limit_watchdog.py` | Каждые 5 минут проверяет остаток токенов; при исчерпании — выключает ПК |
| `install.ps1` | Ставит зависимости, создаёт задачи Планировщика, запускает всё |
| `manage.py` | **Интерактивное меню управления в терминале** |

### Управление в терминале

```powershell
python -X utf8 manage.py
```

```
 1) Статус (баланс, задачи, автовыключение)
 2) Claim сейчас (забрать план вручную)
 3) Обновить JWT из ZCode Desktop
 4) Watchdog: включить автовыключение
 5) Watchdog: отключить автовыключение
 6) Watchdog: пересоздать задачу
 7) Отменить запланированное выключение (shutdown /a)
 8) Логи
```

### Логика монитора лимитов (watchdog)

- Проверяет остаток токенов через `GET /billing/balance` каждые 5 минут.
- **2 проверки подряд** с нулевым остатком → `shutdown /s /t 60` (60 секунд на отмену: `shutdown /a`).
- Сбой сети/API **не** триггерит выключение (иначе обрыв интернета гасит машину).
- Выключение **единоразовое**: после него задача отключает сама себя и не сработает
  снова, пока не появится новый план (новый claim автоматически включит её обратно).

## Установка

```powershell
# 1. Склонируй репозиторий и перейди в папку
git clone https://github.com/c4elovek-cmd/zcode-global-build.git
cd zcode-global-build

# 2. Запусти установку (Python 3.10+ и ZCode Desktop должны быть установлены)
pwsh -NoProfile -ExecutionPolicy Bypass -File install.ps1
```

`install.ps1` сделает всё сам:

1. Установит Python-зависимость `cryptography`
2. Вытащит JWT из ZCode Desktop → `config.json`
3. Сделает тестовый запрос баланса
4. Создаст задачи Планировщика:
   - `ZCode-GlobalBuild-Claim` — запуск claim-цикла при логоне
   - `ZCode-Limit-Watchdog` — проверка лимитов каждые 5 минут

## Ручная установка (без install.ps1)

```powershell
pip install cryptography
python grab_jwt.py          # вытащить токен из ZCode Desktop
python claim.py             # проверить, что claim работает

# Claim-цикл в фоне:
pwsh -NoProfile -WindowStyle Hidden -File run_scheduler.ps1
```

## Файлы

- `config.json` — **создаётся автоматически** (`grab_jwt.py`), содержит твой JWT. **Не публикуй его!**
- `claim.log`, `claim.state.json` (`state.json`), `watchdog.log`, `watchdog_state.json` — логи и состояние, создаются автоматически.

## Полезное

| Действие | Команда |
|---|---|
| Отменить запланированное выключение | `shutdown /a` |
| Отключить автовыключение | `schtasks /change /tn ZCode-Limit-Watchdog /disable` |
| Включить обратно | `schtasks /change /tn ZCode-Limit-Watchdog /enable` |
| Обновить JWT (если истёк) | `python grab_jwt.py` |
| Проверить баланс вручную | `python -c "import claim; print(claim.read_balance())"` |

## Окно claim

Промо-планы Global Build появляются в окне **11:00–22:00 UTC** (14:00–01:00 МСК).
Цикл `run_scheduler.ps1` опрашивает сервер каждые 5 минут и забирает план, как
только он станет доступен. Если план уже активен — просто проверяет баланс.

## Дисклеймер

Проект не аффилирован с Z.ai / ZCode. Используй на свой риск: форматы API
неофициальные и могут измениться. Токены (`config.json`) — это доступ к твоему
аккаунту, никому их не передавай.
