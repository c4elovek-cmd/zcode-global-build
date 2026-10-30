# Мониторинг лимитов ZCode Start Plan (GLM-5.3-Flash).
# Задача планировщика ZCode-Limit-Watchdog запускает скрипт каждые 5 минут.
#
# Логика:
#   - проверка billing/balance; при сбое сети/API счётчик сбрасывается (выключения нет);
#   - 2 проверки подряд с остатком <= THRESHOLD_UNITS → ВЫКЛЮЧЕНИЕ ПК;
#   - выключение ЕДИНОРАЗОВОЕ: задача отключает сама себя (schtasks /disable) и
#     ставит флаг done — до нового claim (claim.py пересоздаёт и включает задачу).
#
# Ручной запуск: python -X utf8 limit_watchdog.py
# Отмена запланированного выключения: shutdown /a

import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from claim import read_balance, THRESHOLD_UNITS, TASK_NAME  # noqa: E402

LOG_PATH = os.path.join(HERE, "watchdog.log")
STATE_PATH = os.path.join(HERE, "watchdog_state.json")

# Подтверждений подряд до выключения (запуски задачи раз в 5 минут → ~10 мин задержки).
CONFIRMATIONS = 2
SHUTDOWN_DELAY_SEC = 60


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"streak": 0, "done": False}


def save_state(st):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def main():
    state = load_state()
    if state.get("done"):
        return  # выключение уже было, задача отключена

    bal = read_balance()
    if bal is None:
        # 401/сеть/сбой — реальный баланс неизвестен, выключение отменяем по счётчику
        log("API недоступен — пропуск (счётчик сброшен).")
        state["streak"] = 0
        save_state(state)
        return

    log(f"Проверка: remaining={bal['remaining']}/{bal['total']}, streak={state.get('streak', 0)}")

    if bal["remaining"] <= THRESHOLD_UNITS:
        state["streak"] = int(state.get("streak") or 0) + 1
        save_state(state)
        if state["streak"] >= CONFIRMATIONS:
            log(f"Лимиты исчерпаны ({state['streak']} подтверждения подряд) — выключаю ПК и отключаю задачу.")
            state["done"] = True
            state["shutdown_at"] = datetime.datetime.now().isoformat()
            save_state(state)
            subprocess.run(["schtasks", "/change", "/tn", TASK_NAME, "/disable"], check=False)
            subprocess.run(
                ["shutdown", "/s", "/t", str(SHUTDOWN_DELAY_SEC),
                 "/c", f"ZCode: лимиты исчерпаны ({bal['remaining']} токенов). Отмена: shutdown /a"],
                check=False,
            )
    else:
        state["streak"] = 0
        state.pop("shutdown_at", None)
        save_state(state)


if __name__ == "__main__":
    main()
