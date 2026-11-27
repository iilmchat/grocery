"""Сборщик каталога и цен сети «Верный» через API мобильного приложения.

Токены берутся из verno_auth.json (создаётся verno_login.py) или из
переменных окружения VERNO_TOKEN / VERNO_DELIVERY_TOKEN / VERNO_STORE_ID.
Выход: verno_products.json (игнорируется Git).
"""

import json
import os
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from datetime import datetime, timezone

import requests

BASE_TRADE = "https://apptrade.ivoin.ru/api"
BASE_DELIVERY = "https://app.verno-dostavka.ru"
AUTH_FILE = "verno_auth.json"
OUT = "verno_products.json"
CACHE = "verno_goods_cache.jsonl"
BATCH = 100  # лимит API: validation.max.array на 200+
WORKERS = 16


def load_auth():
    a = {}
    if os.path.exists(AUTH_FILE):
        a = json.load(open(AUTH_FILE, encoding="utf-8"))
    token = os.environ.get("VERNO_TOKEN") or a.get("token")
    delivery = os.environ.get("VERNO_DELIVERY_TOKEN") or a.get("delivery_token")
    store = os.environ.get("VERNO_STORE_ID") or a.get("store_id")
    if not token or not delivery:
        raise SystemExit("Нет токенов: запустите verno_login.py или задайте VERNO_TOKEN/VERNO_DELIVERY_TOKEN")
    if not store:
        s = requests.Session()
        s.headers.update({"User-Agent": "okhttp/4.12.0", "Accept": "application/json"})
        r = s.get(BASE_DELIVERY + "/api3/address/get-addresses",
                  params={"delivery_token": delivery}, timeout=20)
        r.raise_for_status()
        addresses = r.json().get("addresses") or []
        if not addresses:
            raise SystemExit("Нет адреса/магазина: выберите магазин в приложении Верный")
        store = addresses[0]["store_id"]
        a["store_id"] = store
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(a, f, ensure_ascii=False, indent=2)
    return token, delivery, store


def get(url, headers=None, params=None, retries=4):
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=45)
            r.raise_for_status()
            return r
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def post(url, body, headers=None, retries=4):
    for i in range(retries):
        try:
            r = requests.post(url, json=body, headers=headers, timeout=45)
            r.raise_for_status()
            return r
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def signed(token, path, body=None):
    """Дёргает API apptrade и возвращает JSON по подписанной S3-ссылке."""
    h = {
        "User-Agent": "okhttp/4.12.0", "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": "Bearer " + token,
        "X-App-Version": "1.5.4", "X-Platform": "android", "X-Region-City-Id": "3",
    }
    if body is None:
        r = get(BASE_TRADE + path, headers=h)
    else:
        r = post(BASE_TRADE + path, body, headers=h)
    return r.json()["data"]


def category_path(cid, cats):
    parts = []
    seen = set()
    while cid and cid in cats and cid not in seen:
        seen.add(cid)
        c = cats[cid]
        parts.append(c.get("short_name") or c.get("full_name") or cid)
        cid = c.get("parent_id")
    return list(reversed(parts))


def main():
    token, delivery, store = load_auth()
    print(f"[auth] store={store}")

    cats_raw = get(signed(token, "/v2/catalog/categories")["url"]).json()
    cats = {c["id"]: c for c in cats_raw}
    print(f"[+] категорий: {len(cats)}")

    filters = get(signed(token, "/v2/catalog/filters")["url"]).json()
    products_index = filters["products"]
    print(f"[+] товаров в индексе: {len(products_index)}")

    prices_raw = get(signed(token, f"/v2/catalog/prices/{store}")["url"]).json()
    prices = {p["goods_id"]: p for p in prices_raw["prices"]}
    print(f"[+] цен: {len(prices)}")

    s = requests.Session()
    s.headers.update({"User-Agent": "okhttp/4.12.0", "Accept": "application/json"})
    stocks_raw = get(BASE_DELIVERY + "/api4/sync/stocks",
                     params={"delivery_token": delivery}).json()
    stocks = {x["goods_id"]: x.get("max_count", 0) for x in stocks_raw.get("stocks", [])}
    print(f"[+] остатков: {len(stocks)}")

    # Карточки без цены в выбранном магазине в сбор не попадают
    ids = [p["id"] for p in products_index if p["id"] in prices]
    print(f"[+] товаров с ценой в магазине: {len(ids)}")

    goods = {}
    if os.path.exists(CACHE):
        for line in open(CACHE, encoding="utf-8"):
            try:
                g = json.loads(line)
                goods[g["id"]] = g
            except Exception:
                pass
        print(f"[cache] карточек из прошлого прогона: {len(goods)}")

    def fetch(item):
        pid, url = item
        try:
            r = requests.get(url, timeout=20)
            if r.status_code != 200:
                return pid, None
            return pid, r.json()
        except Exception:
            return pid, None

    def consume(fut):
        pid, g = fut.result()
        if g:
            goods[pid] = g
            cache_f.write(json.dumps(g, ensure_ascii=False) + "\n")

    cache_f = open(CACHE, "a", encoding="utf-8")
    failed = 0
    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            pending = set()
            done = 0
            todo = [pid for pid in ids if pid not in goods]
            for i in range(0, len(todo), BATCH):
                chunk = todo[i:i + BATCH]
                data = signed(token, "/v2/catalog/products/urls", {"uuids": chunk})
                for pid, url in data["urls"].items():
                    pending.add(ex.submit(fetch, (pid, url)))
                    if len(pending) >= WORKERS * 4:
                        finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                        for f in finished:
                            before = len(goods)
                            consume(f)
                            done += 1
                            if len(goods) == before:
                                failed += 1
                if (i // BATCH) % 10 == 0:
                    print(f"[urls] {min(i + BATCH, len(todo))}/{len(todo)}, "
                          f"карточек {len(goods)}, ошибок {failed}", flush=True)
            for f in as_completed(pending):
                before = len(goods)
                consume(f)
                done += 1
                if len(goods) == before:
                    failed += 1
            print(f"[goods] загружено карточек: {done}, ошибок: {failed}", flush=True)
    finally:
        cache_f.close()
        cache_f = None

    out = []
    now = datetime.now(timezone.utc).isoformat()
    for pid, g in goods.items():
        cids = g.get("category_ids") or []
        path = category_path(cids[0], cats) if cids else []
        p = prices.get(pid) or {}
        price = p.get("with_sale")
        old = p.get("price_for_unit")
        out.append({
            "retailer": "verny",
            "product_id": pid,
            "item_code": g.get("item_code"),
            "name": g.get("display_name") or g.get("full_name"),
            "category_path": path,
            "category_slug": cids[0] if cids else None,
            "url": f"https://verno-dostavka.ru/product/{pid}",
            "image_url": g.get("main_image"),
            "price": price,
            "old_price": old if old and price and old > price else None,
            "in_stock": bool(stocks.get(pid)),
            "stock_limit": stocks.get(pid),
            "scraped_at": now,
        })

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    with_price = sum(1 for x in out if x["price"] is not None)
    print(f"\nИТОГ: {len(out)} товаров -> {OUT}, с ценами: {with_price}")


if __name__ == "__main__":
    main()
