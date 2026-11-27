"""Сборщик каталога и цен «Магнита» через webgate API сайта magnit.ru.

АUTHORIZATION не требуется. Выход: magnit_products.json (игнорируется Git).
"""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

BASE = "https://magnit.ru"
API = BASE + "/webgate/v2/goods/search"
OUT = "magnit_products.json"
LIMIT = 50
WORKERS = 8

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36"),
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-Client-Name": "magnit",
    "X-Device-Platform": "Web",
    "X-App-Version": "2026.11.27-12.47",
    "X-Platform-Version": "Chrome/131",
    "X-Device-ID": "recon-device-001",
    "X-Device-Tag": "disabled",
}
S = requests.Session()
S.headers.update(HEADERS)


def get_store_code():
    env = os.environ.get("MAGNIT_STORE_CODE")
    if env:
        return env
    try:
        r = S.get(BASE + "/", timeout=25)
        m = re.search(r'storeCode":"(\d+)"', r.text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "992301"  # Краснодар, ул. Дзержинского, 42


def get_categories():
    r = S.get(BASE + "/__sitemap__/catalog.xml", timeout=30)
    ids = sorted(set(re.findall(r"/catalog/(\d+)-", r.text)), key=int)
    return ids


def search(store, cid, offset):
    body = {
        "pagination": {"limit": LIMIT, "offset": offset},
        "sort": {"order": "desc", "type": "popularity"},
        "storeCode": store,
        "storeType": "dostavka",
        "catalogType": "2",
        "term": "",
    }
    if cid:
        body["categories"] = [int(cid)]
    for attempt in range(4):
        try:
            r = S.post(API, json=body, timeout=40)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (400, 422, 500, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None


def main():
    store = get_store_code()
    cats = get_categories()
    print(f"[auth] store={store}, категорий={len(cats)}", flush=True)

    goods = {}
    errors = 0
    lock = None

    def walk_cat(cid):
        local = []
        offset = 0
        seen_offsets = set()
        while offset not in seen_offsets:
            seen_offsets.add(offset)
            d = search(store, cid, offset)
            if not d:
                return cid, local, 1
            items = d.get("items") or []
            local.extend(items)
            p = d.get("pagination") or {}
            if not p.get("hasMore"):
                break
            nxt = p.get("nextOffset")
            if not nxt or nxt <= offset:
                break
            offset = nxt
        return cid, local, 0

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(walk_cat, cid) for cid in cats]
        done = 0
        for f in as_completed(futs):
            cid, items, err = f.result()
            errors += err
            for it in items:
                pid = it.get("productId") or it.get("id")
                if pid and pid not in goods:
                    goods[pid] = (it, cid)
            done += 1
            if done % 50 == 0:
                print(f"[cats] {done}/{len(cats)}, товаров {len(goods)}, ошибок {errors}", flush=True)

    now = datetime.now(timezone.utc).isoformat()
    out = []
    for pid, (it, cid) in goods.items():
        promo = it.get("promotion") or {}
        price = it.get("price")
        gallery = it.get("gallery") or []
        out.append({
            "retailer": "magnit",
            "product_id": str(pid),
            "name": it.get("name"),
            "category_id": cid,
            "category_slug": str(cid),
            "url": f"{BASE}/product/{pid}-{it.get('seoCode', '')}" if it.get("seoCode") else f"{BASE}/product/{pid}",
            "image_url": gallery[0].get("url") if gallery else None,
            "price": price / 100 if isinstance(price, (int, float)) else None,
            "old_price": promo.get("oldPrice") / 100 if promo.get("oldPrice") else None,
            "in_stock": bool(it.get("quantity")),
            "stock_limit": it.get("quantity"),
            "rating": (it.get("ratings") or {}).get("rating"),
            "store_code": store,
            "scraped_at": now,
        })

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    with_price = sum(1 for x in out if x["price"] is not None)
    print(f"\nИТОГ: {len(out)} товаров -> {OUT}, с ценами: {with_price}, ошибок: {errors}")


if __name__ == "__main__":
    main()
