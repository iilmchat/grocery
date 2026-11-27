"""Сборщик каталога и цен «Твоего дома» через внутренний API сайта.

POST https://tvoydom.ru/api/internal/catalog/<section_slug>  {"page": N}
Без авторизации. Выход: tvoydom_products.json (игнорируется Git).
"""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

BASE = "https://tvoydom.ru"
API = BASE + "/api/internal/catalog/"
CACHE = "tvoydom_cards_cache.jsonl"
OUT = "tvoydom_products.json"
WORKERS = 16

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36"),
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
}
S = requests.Session()
S.headers.update(HEADERS)


def get_sections():
    r = S.get(BASE + "/sitemap-sections.xml", timeout=60)
    return sorted(set(re.findall(r"/catalog/([^/]+)/?", r.text)))


def fetch(slug, page):
    for attempt in range(3):
        try:
            r = S.post(API + slug, json={"page": page, "pageSize": 100}, timeout=40)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None


def walk(slug):
    cards = []
    seen_sigs = set()
    page = 1
    while page <= 500:
        d = fetch(slug, page)
        if not d:
            break
        batch = d.get("cards") or []
        if not batch:
            break
        sig = (batch[0].get("id"), batch[-1].get("id"))
        if sig in seen_sigs:
            break
        seen_sigs.add(sig)
        cards.extend(batch)
        total = d.get("total") or 0
        if page * 100 >= total:
            break
        page += 1
    return slug, cards


def main():
    sections = get_sections()
    start = int(os.environ.get("START_INDEX", "0"))
    end = int(os.environ.get("END_INDEX", str(len(sections))))
    sections = sections[start:end]
    export_only = os.environ.get("EXPORT_ONLY") == "1"
    print(f"[sections] {len(sections)} (index {start}:{end})", flush=True)

    goods = {}
    cache_f = None if export_only else open(CACHE, "a", encoding="utf-8")
    if os.path.exists(CACHE):
        for line in open(CACHE, encoding="utf-8"):
            try:
                c = json.loads(line)
                goods[c["id"]] = c
            except Exception:
                pass
        print(f"[cache] {len(goods)}", flush=True)

    try:
        if not export_only:
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futs = [ex.submit(walk, slug) for slug in sections]
                done = 0
                for f in as_completed(futs):
                    slug, cards = f.result()
                    for c in cards:
                        cid = c.get("id")
                        if cid and cid not in goods:
                            goods[cid] = c
                            cache_f.write(json.dumps(c, ensure_ascii=False) + "\n")
                    done += 1
                    if done % 50 == 0:
                        print(f"[sections] {done}/{len(sections)}, товаров {len(goods)}", flush=True)
    finally:
        if cache_f:
            cache_f.close()

    now = datetime.now(timezone.utc).isoformat()
    out = []
    for cid, c in goods.items():
        photo = c.get("photo") or {}
        out.append({
            "retailer": "tvoydom",
            "product_id": str(cid),
            "code": c.get("code"),
            "name": c.get("name"),
            "category_id": c.get("sectionId"),
            "category_slug": None,
            "url": c.get("url"),
            "image_url": (BASE + photo["path"]) if photo.get("path") else None,
            "price": c.get("price"),
            "old_price": c.get("discountPrice"),
            "discount": c.get("discount"),
            "in_stock": bool(c.get("canBuy")),
            "stock_limit": c.get("ecomFilialStock"),
            "rating": c.get("rating"),
            "scraped_at": now,
        })
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nИТОГ: {len(out)} товаров -> {OUT}, с ценами: {sum(1 for x in out if x['price'] is not None)}")


if __name__ == "__main__":
    main()
