
import asyncio
import json
import os
import random
from datetime import datetime, timezone

from camoufox.async_api import AsyncCamoufox

BASE = "https://5ka.ru"
API = "https://5d.5ka.ru/api"
OUT = "pyaterochka_products.json"
RAW_DIR = "overviews_5ka"
STORE = "35XY"

CATEGORIES_URL = (
    f"{API}/catalog/v4/stores/{STORE}/categories"
    "?mode=delivery&include_subcategories=1&include_restrict=true"
)


def iter_products(node):
    if isinstance(node, dict):
        if "plu" in node and "name" in node and "prices" in node:
            yield node
        else:
            for v in node.values():
                yield from iter_products(v)
    elif isinstance(node, list):
        for v in node:
            yield from iter_products(v)


def iter_subcategories(node):
    if isinstance(node, dict):
        if node.get("id") and node.get("name") and "plu" not in node:
            yield node
            for v in node.values():
                yield from iter_subcategories(v)
        else:
            for v in node.values():
                yield from iter_subcategories(v)
    elif isinstance(node, list):
        for v in node:
            yield from iter_subcategories(v)


def collect_top_categories(tree) -> list:
    cats = []
    if not isinstance(tree, list):
        return cats
    for group in tree:
        if not isinstance(group, dict):
            continue
        for cat in group.get("categories") or []:
            if isinstance(cat, dict) and cat.get("id") and cat.get("name"):
                cats.append({"id": cat["id"], "name": cat["name"]})
    return cats


def absorb(overview, category_name, seen):
    added, total = 0, 0
    for p in iter_products(overview):
        total += 1
        plu = p.get("plu")
        if plu is None:
            continue
        prices = p.get("prices") or {}
        promo = (prices.get("discount") or prices.get("cpd_promo_price")
                 or prices.get("markdown"))
        images = (p.get("image_links") or {}).get("normal") or []
        rating = p.get("rating") or {}

        item = {
            "retailer": "pyaterochka",
            "product_id": plu,
            "name": p.get("name"),
            "category_path": [category_name],
            "price": prices.get("regular"),
            "promo_price": promo,
            "url": f"{BASE}/product/{plu}/",
            "image_url": images[0] if images else None,
            "store_id": STORE,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "in_stock": p.get("is_available"),
            "stock_limit": p.get("stock_limit"),
            "uom": p.get("uom"),
            "rating": rating.get("rating_average"),
            "rates_count": rating.get("rates_count"),
            "max_qty_per_order": p.get("max_qty_per_order"),
            "property_clarification": p.get("property_clarification"),
        }
        if plu in seen:
            if category_name not in seen[plu]["category_path"]:
                seen[plu]["category_path"].append(category_name)
        else:
            seen[plu] = item
            added += 1
    return added, total


async def fetch_json(page, url):
    for attempt in range(4):
        try:
            return await page.evaluate(
                """async (url) => {
                     const r = await fetch(url, {credentials: "include"});
                     if (!r.ok) return {__status__: r.status};
                     return await r.json();
                   }""",
                url,
            )
        except Exception:
            # контекст страницы, похоже, умер — перезагружаем и перепрогреваем
            print(f"    [net] попытка {attempt + 1} упала, перезагружаю страницу")
            try:
                await page.goto(f"{BASE}/catalog/",
                                wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(5000)
            except Exception as e:
                print(f"    [net] перезагрузка тоже упала: {type(e).__name__}")
                await asyncio.sleep(10)
    return {"__status__": "netfail"}



async def fetch_overview(page, cid):
    for ver in ("v2", "v4"):
        resp = await fetch_json(
            page, f"{API}/catalog/{ver}/stores/{STORE}/categories/{cid}/overview?mode=delivery")
        if resp and resp.get("__status__"):
            print(f"    (overview {ver}: HTTP {resp['__status__']})")
            continue
        if resp and ("categories" in resp or "products_count" in resp):
            return resp
    return None


async def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    seen = {}
    per_cat = {}

    async with AsyncCamoufox(headless=True, geoip=False) as browser:
        page = await browser.new_page()

        await page.goto(f"{BASE}/catalog/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        tree = await fetch_json(page, CATEGORIES_URL)
        if isinstance(tree, dict) and tree.get("__status__"):
            raise SystemExit(f"Категории не получены: HTTP {tree['__status__']}")
        cats = collect_top_categories(tree)
        print(f"Категорий верхнего уровня: {len(cats)}")
        if not cats:
            print("Дерево неожиданной структуры, первые ключи:",
                  json.dumps(tree, ensure_ascii=False)[:500])
            return

        for i, cat in enumerate(cats, 1):
            cid, name = cat["id"], cat["name"]
            overview = None
            for attempt in (1, 2, 3):
                try:
                    overview = await fetch_overview(page, cid)
                except Exception as e:
                    print(f"[{i}/{len(cats)}] {name}: ошибка fetch — {e}")
                if overview:
                    break
                await asyncio.sleep(5)

            if not overview:
                print(f"[!] {name} ({cid}): overview не получен — пропускаю")
                continue

            with open(f"{RAW_DIR}/{cid}.json", "w", encoding="utf-8") as f:
                json.dump(overview, f, ensure_ascii=False)

            added, total = absorb(overview, name, seen)
            want = overview.get("products_count") or total
            print(f"[+] {name}: позиций {total} (count={want}), новых {added}, "
                  f"всего {len(seen)}")

            if total < want:
                subs = [s for s in iter_subcategories(overview) if s["id"] != cid]
                print(f"    [~] недобор {want - total}: докачиваю {len(subs)} подкатегорий")
                for sub in subs:
                    sub_ov = None
                    for attempt in (1, 2):
                        try:
                            sub_ov = await fetch_overview(page, sub["id"])
                        except Exception:
                            pass
                        if sub_ov:
                            break
                        await asyncio.sleep(3)
                    if sub_ov:
                        with open(f"{RAW_DIR}/{sub['id']}.json", "w", encoding="utf-8") as f:
                            json.dump(sub_ov, f, ensure_ascii=False)
                        a2, t2 = absorb(sub_ov, name, seen)
                        print(f"      + {sub['name']}: позиций {t2}, новых {a2}")
                    await asyncio.sleep(random.uniform(1.0, 2.0))
                per_cat[name] = sum(
                    1 for v in seen.values() if name in v["category_path"])
            else:
                per_cat[name] = sum(
                    1 for v in seen.values() if name in v["category_path"])

            await asyncio.sleep(random.uniform(1.5, 3.0))

    json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nИТОГ: {len(seen)} товаров -> {OUT}")
    for n, c in per_cat.items():
        print(f"  {n}: {c}")


asyncio.run(main())
