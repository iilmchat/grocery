"""Сбор товаров сети «Ашан» через API /v3/catalog/products/.

Ашан закрыт Qrator-ом: обычный urllib получает 401, поэтому работаем
в Camoufox с persistent-профилем (куки челленджа сохраняются между прогонами).
API дёргаем fetch-ом из контекста страницы — так авторизация/куки не нужны.

Формат записей тот же, что у остальных коллекторов проекта.
"""

import asyncio
import json
import math
import os
import random
import re
import time
from datetime import datetime, timezone

from camoufox.async_api import AsyncCamoufox

BASE = "https://www.auchan.ru"
CATALOG_URL = f"{BASE}/catalog/"
API_URL = f"{BASE}/v3/catalog/products/"
OUT = "auchan_products.json"
LINKS_FILE = "auchan_links.json"
DONE_FILE = "auchan_done.json"
PROFILE = "profile_auchan"

PER_PAGE = 100           # API отдаёт максимум 100 за запрос
MAX_PAGES = 200
RETRIES = 4

FETCH_JS = """async ({url, body}) => {
    try {
        const r = await fetch(url, {
            method: 'POST',
            credentials: 'include',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
        if (!r.ok) return {__status__: r.status};
        return await r.json();
    } catch (e) { return {__error__: String(e)}; }
}"""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def checkpoint(seen):
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(list(seen.values()), f, ensure_ascii=False, indent=2)
    for attempt in range(10):
        try:
            os.replace(tmp, OUT)
            return
        except PermissionError:
            time.sleep(1 + attempt * 0.5)
    raise RuntimeError(f"не удалось перезаписать {OUT}: файл занят")


def money(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 2) if 0 < f < 1_000_000 else None


def api_url(page):
    return (f"{API_URL}?orderField=rank&orderDirection=asc&merchantId=0"
            f"&deliveryAddressSelected=0&perPage={PER_PAGE}&page={page}")


def request_body(code):
    return {"filter": {
        "cashback_only": False,
        "active_only": True,
        "promo_only": False,
        "category": [code],
    }}


def make_item(p, cat):
    pid = p.get("productId")
    if not pid:
        return None

    price = money((p.get("price") or {}).get("value"))
    old = money((p.get("oldPrice") or {}).get("value"))
    stock = p.get("stock") or {}
    codes = p.get("categoryCodes") or []
    categories = [c.get("name") for c in codes if isinstance(c, dict) and c.get("name")]
    path = categories or [cat["name"]]
    rating = p.get("rate") or {}
    values = [v for v in (price, old) if v is not None]

    return {
        "retailer": "auchan",
        "product_id": pid,
        "name": p.get("title"),
        "category_path": path,
        "category_slug": cat["code"],
        "url": f"{BASE}/product/{p['code']}/" if p.get("code") else None,
        "image_url": p.get("catalogImageUrl"),
        "price": price,
        "old_price": old,
        "discount_percent": p.get("discountPercent"),
        "price_min": min(values) if values else None,
        "price_max": max(values) if values else None,
        "brand": (p.get("brand") or {}).get("name"),
        "uom": (p.get("price") or {}).get("per"),
        "rating": rating.get("rating"),
        "reviews": rating.get("reviews_qnt"),
        "in_stock": bool(p.get("active")) and not stock.get("not_available", False),
        "badges": [b.get("text") or b.get("code") for b in (p.get("badges") or [])
                   if isinstance(b, dict)],
        "scraped_at": now_iso(),
    }


async def get_categories(page):
    """Собираем ссылки верхнего уровня со страницы каталога."""
    for attempt in range(1, 5):
        try:
            await page.goto(CATALOG_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(6000)
            html = await page.content()
        except Exception as e:
            print(f"[bootstrap] попытка {attempt}: {type(e).__name__}: {str(e)[:120]}")
            await asyncio.sleep(5 * attempt)
            continue

        links = sorted(set(re.findall(r'href="(/catalog/[^/"]+/)"', html)))
        if len(links) >= 20:
            cats = []
            for link in links:
                code = link.strip("/").split("/")[-1]
                # название возьмём из текста ссылки, если получится
                m = re.search(r'href="' + re.escape(link) + r'"[^>]*>([^<]{2,80})<', html)
                name = (m.group(1).strip() if m else code)
                cats.append({"code": code, "url": link, "name": name})
            return cats
        print(f"[bootstrap] ссылок {len(links)} — повторяю (попытка {attempt})")
        await asyncio.sleep(5 * attempt)
    raise RuntimeError("не удалось получить список категорий Ашана")


async def fetch_page(page, cat, page_num):
    for attempt in range(1, RETRIES + 1):
        resp = await page.evaluate(FETCH_JS, {
            "url": api_url(page_num), "body": request_body(cat["code"])})
        if isinstance(resp, dict) and "items" in resp:
            return resp
        print(f"    [retry] {cat['code']} стр.{page_num}: попытка {attempt} — "
              f"{str(resp)[:120]}")
        await asyncio.sleep(3 * attempt)
    return None


async def main():
    seen = {}
    if os.path.exists(OUT):
        try:
            for it in json.load(open(OUT, encoding="utf-8")):
                key = it.get("product_id")
                if key:
                    seen[key] = it
            print(f"[cache] товаров из прошлого прогона: {len(seen)}", flush=True)
        except (json.JSONDecodeError, OSError):
            pass

    done = json.load(open(DONE_FILE, encoding="utf-8")) if os.path.exists(DONE_FILE) else []
    done_set = set(done)

    async with AsyncCamoufox(
        headless=True,
        persistent_context=True,
        user_data_dir=PROFILE,
        i_know_what_im_doing=True,
        geoip=False,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        if os.path.exists(LINKS_FILE):
            cats = json.load(open(LINKS_FILE, encoding="utf-8"))
            print(f"[cache] категорий из файла: {len(cats)}", flush=True)
        else:
            cats = await get_categories(page)
            json.dump(cats, open(LINKS_FILE, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            print(f"[new] категорий собрано: {len(cats)}", flush=True)

        total_new = 0
        for i, cat in enumerate(cats, 1):
            if cat["code"] in done_set:
                continue

            first = await fetch_page(page, cat, 1)
            if not first:
                print(f"[!] {cat['code']}: API не ответил — пропускаю", flush=True)
                continue

            items = first.get("items") or []
            total = int(first.get("range") or len(items))
            total_pages = min(math.ceil(total / PER_PAGE), MAX_PAGES)

            added = 0
            for p in items:
                item = make_item(p, cat)
                if item and item["product_id"] not in seen:
                    seen[item["product_id"]] = item
                    added += 1
            checkpoint(seen)

            for page_num in range(2, total_pages + 1):
                resp = await fetch_page(page, cat, page_num)
                if not resp:
                    continue
                page_added = 0
                for p in resp.get("items") or []:
                    item = make_item(p, cat)
                    if item and item["product_id"] not in seen:
                        seen[item["product_id"]] = item
                        added += 1
                        page_added += 1
                checkpoint(seen)
                print(f"    {cat['code']}: стр.{page_num}/{total_pages} "
                      f"новых {page_added}, уникальных {len(seen)}", flush=True)
                await asyncio.sleep(random.uniform(0.3, 0.8))

            total_new += added
            print(f"[{i}/{len(cats)}] {cat['name']}: всего {total}, "
                  f"страниц {total_pages}, новых {added}, уникальных {len(seen)}",
                  flush=True)
            checkpoint(seen)
            done.append(cat["code"])
            json.dump(done, open(DONE_FILE, "w", encoding="utf-8"))
            await asyncio.sleep(random.uniform(0.5, 1.2))

    print(f"\nИТОГ: новых {total_new}, всего {len(seen)} товаров -> {OUT}", flush=True)
    if seen:
        sample = next(iter(seen.values()))
        print("образец записи:", json.dumps(sample, ensure_ascii=True)[:600], flush=True)


if __name__ == "__main__":
    asyncio.run(main())
