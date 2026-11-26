import asyncio
import json
import random
from datetime import datetime, timezone

from camoufox.async_api import AsyncCamoufox

BASE = "https://chizhik.club"
API = "https://app.chizhik.club/delivery/api"
OUT = "chizhik_products.json"
RAW_DIR = "overviews"
STORE = "HBBN"

CATEGORIES_URL = (
    f"{API}/catalog/v3/stores/{STORE}/categories"
    "?mode=delivery&include_subcategories=1&include_restrict=true"
)
OVERVIEW_URL = f"{API}/catalog/v2/stores/{STORE}/categories/{{cid}}/overview?mode=delivery"

FETCH_JS = """async (url) => {
    const r = await fetch(url, {credentials: "include"});
    if (!r.ok) return {__status__: r.status};
    return await r.json();
}"""


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
    """Все узлы-категории с id, рекурсивно."""
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


def collect_top_categories(tree) -> list[dict]:
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


def absorb(overview: dict, category_name: str, seen: dict) -> tuple[int, int]:
    """Возвращает (новых товаров, всего позиций в ответе)."""
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
            "retailer": "chizhik",
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
            "orange_loyalty_points": p.get("orange_loyalty_points"),
            "property_clarification": p.get("property_clarification"),
        }
        if plu in seen:
            if category_name not in seen[plu]["category_path"]:
                seen[plu]["category_path"].append(category_name)
        else:
            seen[plu] = item
            added += 1
    return added, total


async def fetch_overview(page, cid: str):
    resp = await page.evaluate(FETCH_JS, OVERVIEW_URL.format(cid=cid))
    if resp and resp.get("__status__"):
        return None
    if resp and ("categories" in resp or "products_count" in resp):
        return resp
    return None


async def main():
    import os
    os.makedirs(RAW_DIR, exist_ok=True)

    seen: dict = {}
    per_cat: dict = {}

    async with AsyncCamoufox(headless=True, geoip=False) as browser:
        page = await browser.new_page()

        await page.goto(f"{BASE}/catalog/maslo-sousy-spetsii--264C39172/",
                        wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        tree = await page.evaluate(FETCH_JS, CATEGORIES_URL)
        cats = collect_top_categories(tree)
        print(f"Категорий верхнего уровня: {len(cats)}")

        for i, cat in enumerate(cats, 1):
            cid, name = cat["id"], cat["name"]
            slug_safe = name.replace(" ", "_")[:40]

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
            print(f"[+] {name}: позиций в ответе {total} (count={want}), новых {added}, "
                  f"всего уникальных {len(seen)}")

            # Докачка: если в родителе меньше товаров, чем заявлено,
            # дёргаем overview по каждой подкатегории отдельно
            if total < want:
                subs = [s for s in iter_subcategories(overview)
                        if s["id"] != cid]
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
                        a2, t2 = absorb(sub_ov, name, seen)
                        with open(f"{RAW_DIR}/{sub['id']}.json", "w", encoding="utf-8") as f:
                            json.dump(sub_ov, f, ensure_ascii=False)
                        print(f"      + {sub['name']}: позиций {t2}, новых {a2}")
                    await asyncio.sleep(random.uniform(1.0, 2.0))

                # пересчёт по категории
                have = sum(1 for v in seen.values() if name in v["category_path"])
                per_cat[name] = have
                print(f"    итог по {name}: {have} (ожидалось ~{want})")
            else:
                per_cat[name] = sum(
                    1 for v in seen.values() if name in v["category_path"])

            await asyncio.sleep(random.uniform(1.5, 3.0))

    items = list(seen.values())
    json.dump(items, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nИТОГ: {len(items)} товаров -> {OUT}")
    for name_, n in per_cat.items():
        print(f"  {name_}: {n}")


asyncio.run(main())
