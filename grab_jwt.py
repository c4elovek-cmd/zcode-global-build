# Вытаскивает свежий JWT ZCode из зашифрованных credentials.json приложения.
# Запускать отдельно: python grab_jwt.py
# Требует установленный и залогиненный ZCode Desktop и пакет cryptography.

import json
import base64
import hashlib
import os
import sys


def decrypt_value(val, key):
    if not val.startswith("enc:v1:"):
        return val
    iv_t, tag_t, ct_t = val[7:].split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)
    iv = base64.urlsafe_b64decode(pad(iv_t))
    tag = base64.urlsafe_b64decode(pad(tag_t))
    ct = base64.urlsafe_b64decode(pad(ct_t))
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    pt = AESGCM(key).decrypt(iv, ct + tag, None)
    return pt.decode("utf-8")


def find_creds_path():
    cands = [
        os.path.expandvars(r"%USERPROFILE%\.zcode\v2\credentials.json"),
        os.path.expanduser(r"~\.zcode\v2\credentials.json"),
    ]
    for p in cands:
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(
        "credentials.json ZCode не найден. Установи ZCode Desktop и войди в аккаунт."
    )


def main():
    creds_path = find_creds_path()
    home = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    user = os.environ.get("USERNAME", os.path.basename(home))
    secret = f"zcode-credential-fallback:win32:{home}:{user}"
    key = hashlib.sha256(secret.encode()).digest()

    creds = json.load(open(creds_path, encoding="utf-8"))
    jwt = decrypt_value(creds.get("zcodejwttoken", ""), key)
    # api-key лежит под ключом с user_id внутри — ищем по префиксу/суффиксу
    api_key = ""
    for k, v in creds.items():
        if k.startswith("account-provider:coding-plan:") and k.endswith(":api-key"):
            api_key = decrypt_value(v, key)
            break

    device_mid = ""
    onb = os.path.join(os.path.dirname(creds_path), "onboarding-record.json")
    if os.path.isfile(onb):
        try:
            device_mid = json.load(open(onb, encoding="utf-8")).get("deviceMid", "")
        except Exception:
            pass

    out_dir = os.path.dirname(os.path.abspath(__file__))
    cfg = {
        "jwt": jwt,
        "api_key": api_key,
        "device_mid": device_mid,
        "creds_path": creds_path,
    }
    out_path = os.path.join(out_dir, "config.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    print(f"OK: config.json обновлён ({out_path})")
    print(f"jwt: {jwt[:28]}...{jwt[-12:]}")
    if api_key:
        print(f"api_key: {api_key[:14]}...")

    if not jwt:
        print("JWT пустой — войди в аккаунт в ZCode Desktop и запусти снова.")
        sys.exit(1)

    try:
        import cryptography  # noqa
    except ImportError:
        print("Нет пакета cryptography — установи: pip install cryptography")


if __name__ == "__main__":
    main()
