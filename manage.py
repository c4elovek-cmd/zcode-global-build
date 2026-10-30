# Простое терминальное управление ZCode Global Build.
# Запуск: python -X utf8 manage.py

import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:
    pass

from claim import (  # noqa: E402
    read_balance, task_state, reschedule_watchdog,
    THRESHOLD_UNITS, TASK_NAME,
)
import claim  # noqa: E402  (для claim.main())

CLAIM_TASK = "ZCode-GlobalBuild-Claim"
CLAIM_LOG = os.path.join(HERE, "claim.log")
WD_LOG = os.path.join(HERE, "watchdog.log")
WD_STATE = os.path.join(HERE, "watchdog_state.json")


def hr():
    print("-" * 60)


def fmt_ts(unix):
    if not unix:
        return "—"
    return datetime.datetime.fromtimestamp(unix).strftime("%d.%m.%Y %H:%M")


def read_watchdog_state():
    try:
        with open(WD_STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def show_status():
    hr()
    print("БАЛАНС")
    bal = read_balance()
    if bal is None:
        print("  Неизвестно (API/сеть недоступны)")
    elif bal["remaining"] < 0:
        print(f"  Активный план есть, но баланс недоступен (истекает: {fmt_ts(bal['expires_at'])})")
    elif bal["total"] == 0:
        print("  Нет активного плана — лимиты недоступны")
        print("  Забери новый план через пункт 2 (в окне 14:00–01:00 МСК)")
    else:
        pct = (bal["remaining"] / bal["total"] * 100) if bal["total"] else 0
        print(f"  Остаток:  {bal['remaining']:,} из {bal['total']:,} токенов ({pct:.1f}%)".replace(",", " "))
        print(f"  План истекает: {fmt_ts(bal['expires_at'])}")
        if bal["remaining"] <= THRESHOLD_UNITS:
            print("  ⚠ Лимиты исчерпаны")

    print("\nЗАДАЧИ ПЛАНИРОВЩИКА")
    for name in (CLAIM_TASK, TASK_NAME):
        st = task_state(name) or "нет задачи"
        print(f"  {name}: {st}")

    print("\nWATCHDOG (автовыключение)")
    st = read_watchdog_state()
    if st.get("done"):
        print(f"  Выключение УЖЕ БЫЛО: {st.get('shutdown_at', '?')}")
        print("  Задача отключена до нового claim")
    else:
        print(f"  Счётчик нулевых проверок: {st.get('streak', 0)}/2")
    hr()


def run_claim_now():
    hr()
    print("Запускаю claim...")
    claim.main()


def run_grab_jwt():
    hr()
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "grab_jwt.py")])
    if r.returncode == 0:
        print("JWT обновлён.")


def wd_enable():
    hr()
    bal = read_balance()
    if bal and bal["remaining"] > THRESHOLD_UNITS:
        subprocess.run(["schtasks", "/change", "/tn", TASK_NAME, "/enable"], check=False)
        with open(WD_STATE, "w", encoding="utf-8") as f:
            json.dump({"streak": 0, "done": False}, f)
        print(f"Watchdog включён (токенов: {bal['remaining']:,}).".replace(",", " "))
    else:
        rem = bal["remaining"] if bal else "неизвестно"
        print(f"Токенов нет (remaining={rem}) — включать бессмысленно.")
        print("Забери новый план (пункт 3), потом включай.")


def wd_disable():
    hr()
    subprocess.run(["schtasks", "/change", "/tn", TASK_NAME, "/disable"], check=False)
    print(f"Watchdog отключён — ПК больше не выключится автоматически.")


def wd_reschedule():
    hr()
    reschedule_watchdog()
    print("Задача Watchdog пересоздана (проверка каждые 5 минут).")


def cancel_shutdown():
    hr()
    r = subprocess.run(["shutdown", "/a"], capture_output=True)
    if r.returncode == 0:
        print("Запланированное выключение отменено.")
    else:
        print("Активного запланированного выключения нет.")


def tail(path, n=15):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except FileNotFoundError:
        return "(лог пуст)"


def show_logs():
    hr()
    print("1) Лог claim  2) Лог watchdog  3) Состояние watchdog")
    what = input("Выбор [1]: ").strip() or "1"
    n = input("Сколько строк [15]: ").strip()
    n = int(n) if n.isdigit() else 15
    hr()
    if what == "2":
        print(tail(WD_LOG, n))
    elif what == "3":
        print(json.dumps(read_watchdog_state(), ensure_ascii=False, indent=2))
    else:
        print(tail(CLAIM_LOG, n))


MENU = """
================ ZCode Global Build — управление ================
 1) Статус (баланс, задачи, автовыключение)
 2) Claim сейчас (забрать план вручную)
 3) Обновить JWT из ZCode Desktop
 4) Watchdog: включить автовыключение
 5) Watchdog: отключить автовыключение
 6) Watchdog: пересоздать задачу (после перечитки конфига)
 7) Отменить запланированное выключение (shutdown /a)
 8) Логи
 0) Выход
================================================================="""


def main():
    actions = {
        "1": show_status,
        "2": run_claim_now,
        "3": run_grab_jwt,
        "4": wd_enable,
        "5": wd_disable,
        "6": wd_reschedule,
        "7": cancel_shutdown,
        "8": show_logs,
    }
    while True:
        print(MENU)
        choice = input("Выбор: ").strip()
        if choice == "0":
            print("Пока!")
            return
        action = actions.get(choice)
        if action:
            try:
                action()
            except KeyboardInterrupt:
                print("\nПрервано.")
        else:
            print("Не понял, повтори.")
        input("\n[Enter — в меню]")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nПока!")
