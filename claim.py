# Автоматический claim бесплатного промо-плана Global Build (GLM-5.3-Flash,
# 300M токенов) в ZCode. Работает так: в окно (с 11:00 UTC / 14:00 МСК) делает
# GET billing/preview, берёт первый доступный план и сразу POST billing/claim.
# Лог пишет рядом с собой.

import json
import urllib.request
import urllib.error
import uuid
import base64
import datetime
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(HERE, "config.json")
LOG_PATH = os.path.join(HERE, "claim.log")
STATE_PATH = os.path.join(HERE, "state.json")

BALANCE_URL = "https://zcode.z.ai/api/v1/zcode-plan/billing/balance?app_version=3.16.3&platform=win32-x64"
CURRENT_URL = "https://zcode.z.ai/api/v1/zcode-plan/billing/current"
# Порог остатка токенов: ниже него план считается исчерпанным.
THRESHOLD_UNITS = 0
TASK_NAME = "ZCode-Limit-Watchdog"


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def load_config():
    cfg = load_json(CONFIG_PATH, {})
    if not cfg.get("jwt"):
        print("Нет config.json с JWT. Запусти: python grab_jwt.py")
        sys.exit(1)
    return cfg


def build_headers(jwt, api_key, device_mid):
    # Для GET (preview/balance/current) лишний Content-Type ломает запрос → parameter error
    return {
        "Accept": "application/json",
        "User-Agent": "ZCode/3.16.3",
        "X-ZCode-App-Version": "3.16.3",
        "X-Device-Mid": device_mid,
        "X-Client-Language": "ru-RU",
        "X-Platform": "win32-x64",
        "Authorization": f"Bearer {jwt}",
        "X-Os-Category": "windows",
        "X-Os-Version": "10.0.19045",
        "X-Release-Channel": "production",
        "X-Client-Timezone": "Europe/Moscow",
        "X-Title": "Z Code@electron",
        "http-referer": "https://zcode.z.ai",
    }


def with_json_content_type(headers):
    h = dict(headers)
    h["Content-Type"] = "application/json"
    return h


def request(url, headers, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, {"raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}


def preview_plans(headers):
    url = (
        "https://zcode.z.ai/api/v1/zcode-plan/billing/preview"
        "?app_version=3.16.3&platform=win32-x64"
    )
    st, data = request(url, headers)
    if st != 200 or data.get("code") not in (0, None):
        log(f"preview: HTTP {st} code={data.get('code')} msg={data.get('msg')}")
        return []
    plans = (data.get("data") or {}).get("plans") or []
    out = []
    for p in plans:
        pid = (p.get("plan_id") or "").strip()
        if pid:
            ents = ", ".join(
                f"{e.get('meter','?')}:{e.get('grant_units','?')}"
                for e in (p.get("entitlements") or [])[:6]
            )
            out.append({"plan_id": pid, "name": p.get("name", pid), "entitlements": ents})
    return out


def claim_plan(headers, plan_id):
    url = "https://zcode.z.ai/api/v1/zcode-plan/billing/claim"
    st, data = request(url, with_json_content_type(headers), method="POST", body={"plan_id": plan_id})
    ok = st == 200 and data.get("code") in (0, None) and (data.get("data") or {}).get("plan")
    msg = data.get("msg") or (data.get("data") or {}).get("message") or ""
    return ok, st, msg, data


def read_balance(headers=None):
    """Остаток токенов ZCode.
    Возвращает dict {remaining, total, expires_at} или None (сеть/API сломаны —
    состояние неизвестно). Когда активных планов нет, /billing/balance отвечает
    400 parameter error, поэтому в этом случае смотрим /billing/current:
      - планов нет  → remaining=0 (лимиты исчерпаны — план истёк);
      - план есть, но balance недоступен → remaining=-1 (неизвестно, не выключать).
    """
    if headers is None:
        cfg = load_config()
        headers = build_headers(cfg["jwt"], cfg.get("api_key", ""), cfg.get("device_mid", ""))
    st, data = request(BALANCE_URL, headers)
    if st == 200 and data.get("code") in (0, None):
        balances = (data.get("data") or {}).get("balances") or []
        return {
            "remaining": sum(int(b.get("remaining_units") or 0) for b in balances),
            "total": sum(int(b.get("total_units") or 0) for b in balances),
            "expires_at": max((int(b.get("expires_at") or 0) for b in balances), default=0),
        }

    # balance недоступен — смотрим, есть ли вообще активный план
    st2, data2 = request(CURRENT_URL, headers)
    ok2 = st2 == 200 and data2.get("code") in (0, None)
    if not ok2:
        return None
    cur = (data2.get("data") or {}).get("plans") or []
    if not cur:
        return {"remaining": 0, "total": 0, "expires_at": 0}
    return {
        "remaining": -1,
        "total": 0,
        "expires_at": max((int(p.get("ends_at") or 0) for p in cur), default=0),
    }


def task_state(name=TASK_NAME):
    """Состояние задачи планировщика: 'Ready'/'Running'/'Disabled' или None, если её нет."""
    r = subprocess.run(
        ["pwsh", "-NoProfile", "-Command",
         f"(Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue).State"],
        capture_output=True, text=True,
    )
    s = (r.stdout or "").strip()
    return s or None


def reset_watchdog_state():
    try:
        with open(os.path.join(HERE, "watchdog_state.json"), "w", encoding="utf-8") as f:
            json.dump({"streak": 0, "done": False}, f)
    except Exception:
        pass


def ensure_watchdog():
    # Мониторинг активен ТОЛЬКО когда токены реально есть. При нулевом балансе
    # задача остаётся отключённой — выключение НЕ повторяется (единоразово).
    bal = read_balance()
    if not (bal and bal["remaining"] > THRESHOLD_UNITS):
        rem = bal["remaining"] if bal else "неизвестно"
        log(f"Лимитов нет (remaining={rem}) — мониторинг/выключение не включаю.")
        return

    st = task_state()
    if st == "Disabled":
        subprocess.run(["schtasks", "/change", "/tn", TASK_NAME, "/enable"], check=False)
        reset_watchdog_state()
        log(f"Токены есть (remaining={bal['remaining']}) — включаю задачу {TASK_NAME}.")
    elif st is None:
        reschedule_watchdog()
        log(f"Токены есть (remaining={bal['remaining']}) — задача отсутствовала, создаю.")
    # st в ('Ready', 'Running') — уже следит, ничего не трогаем


def reschedule_watchdog(ends_at=None):
    # Пересоздаёт задачу ZCode-Limit-Watchdog (проверка каждые 5 минут) и
    # сбрасывает флаг done. Вызывается при активном плане / после успешного claim,
    # чтобы мониторинг снова ловил момент исчерпания токенов.
    run_at = datetime.datetime.now()
    python_exe = sys.executable.replace("'", "''")
    script = os.path.join(HERE, "limit_watchdog.py").replace("'", "''")
    pw = (
        "$act = New-ScheduledTaskAction -Execute '" + python_exe + "' "
        "-Argument '-X utf8 \"" + script + "\"'; "
        "$t = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5); "
        "$t.Repetition.Duration = 'P365D'; "
        "$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable "
        "-ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew; "
        "Register-ScheduledTask -TaskName '" + TASK_NAME + "' -Action $act -Trigger $t -Settings $set "
        "-Description 'Мониторинг лимитов ZCode; при исчерпании 2 проверки подряд выключает ПК (единоразово)' -Force | Out-Null"
    )
    r = subprocess.run(["pwsh", "-NoProfile", "-Command", pw], capture_output=True, text=True)
    ok = r.returncode == 0
    # Сброс флага done — новый план активен, мониторинг снова нужен
    reset_watchdog_state()
    log(f"Watchdog-задача пересоздана (цикл 5 мин) в {run_at:%Y-%m-%d %H:%M}: {'OK' if ok else 'FAIL ' + (r.stderr or '')[:200]}")


def main():
    cfg = load_config()
    jwt = cfg["jwt"]
    api_key = cfg.get("api_key", "")
    dm = cfg.get("device_mid", "")
    headers = build_headers(jwt, api_key, dm)

    st, data = request("https://zcode.z.ai/api/v1/zcode-plan/billing/current", headers)
    cur = (data.get("data") or {}).get("plans") or []
    already = []
    for p in cur:
        pid = (p.get("plan_id") or "").strip()
        status = (p.get("status") or "").strip()
        ends = p.get("ends_at")
        if pid:
            already.append({"plan_id": pid, "status": status, "ends_at": ends})
    if already:
        log(f"Уже есть активный план: {already}")
        ensure_watchdog()
        save_json(STATE_PATH, {"last_run": time.time(), "already_active": already})
        return

    plans = preview_plans(headers)
    if not plans:
        log("preview вернул пусто — окно claim не открыто или план не доступен.")
        save_json(STATE_PATH, {"last_run": time.time(), "plans": []})
        return

    log(f"Доступны планы: {[p['plan_id'] + ' (' + p['name'] + ')' for p in plans]}")

    # По умолчанию берём первый (сервер сам отдаёт в порядке приоритета)
    chosen = plans[0]
    ok, st, msg, full = claim_plan(headers, chosen["plan_id"])
    if ok:
        plan = (full.get("data") or {}).get("plan") or {}
        log(f"CLAIM OK: {chosen['plan_id']} ({chosen['name']}) ent={chosen['entitlements']} ends_at={plan.get('ends_at')}")
        ensure_watchdog()
        save_json(STATE_PATH, {"last_run": time.time(), "claimed": chosen, "plan": plan})
    else:
        log(f"CLAIM FAIL: plan={chosen['plan_id']} HTTP={st} msg={msg}")
        save_json(STATE_PATH, {"last_run": time.time(), "failed": chosen, "msg": msg})


if __name__ == "__main__":
    main()
