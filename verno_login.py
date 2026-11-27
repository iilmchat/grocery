"""Интерактивная авторизация в API «Верного» по SMS.

Создаёт verno_auth.json с JWT, delivery_token и store_id. Файл игнорируется Git.
"""

import json

import requests

S = requests.Session()
S.headers.update({
    "User-Agent": "okhttp/4.12.0", "Accept": "application/json",
    "Content-Type": "application/json; charset=utf-8",
    "X-App-Version": "1.5.4", "X-Platform": "android", "X-Region-City-Id": "3",
})
B = "https://apptrade.ivoin.ru/api"


def agreements():
    return {
        "agreement_user": True,
        "agreement_user_date": "2026-11-27T00:00:00Z",
        "agreement_adv": True,
        "agreement_adv_date": "2026-11-27T00:00:00Z",
    }


def main():
    phone = input("Телефон (цифры, 11 знаков): ").strip().lstrip("+")
    d = {"phone": phone, **agreements()}
    r = S.post(B + "/v2/auth/send-sms", json=d, timeout=20)
    print("send-sms:", r.status_code, r.text[:200])
    r.raise_for_status()
    code = input("Код из SMS: ").strip()
    d["code"] = code
    r = S.post(B + "/v2/auth/verify-sms", json=d, timeout=20)
    print("verify-sms:", r.status_code)
    r.raise_for_status()
    auth = r.json()
    token = auth.get("token")
    if not token:
        raise SystemExit("Токен не получен")

    if not auth.get("is_registered"):
        regions = S.get(B + "/v2/region-indices", timeout=15).json()
        print("Регионы:", regions)
        region = input("ID региона (Москва = 3): ").strip() or "3"
        rr = S.post(B + "/v2/register", json={
            "token": token, "phone": phone,
            "name": input("Имя: ").strip() or "Тест",
            "lastname": input("Фамилия: ").strip() or "Тестов",
            "region": int(region),
        }, timeout=20)
        print("register:", rr.status_code, rr.text[:200])
        rr.raise_for_status()
        auth = rr.json()
        token = auth["token"]

    out = {"token": token, "delivery_token": auth.get("delivery_token")}
    if not out["delivery_token"]:
        raise SystemExit("delivery_token не получен — проверьте register/verify")
    with open("verno_auth.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("Токены сохранены в verno_auth.json")


if __name__ == "__main__":
    main()
