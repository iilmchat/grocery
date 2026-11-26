import asyncio
import json
import os
import random
from datetime import datetime, timezone

from camoufox.async_api import AsyncCamoufox

BASE = "https://www.perekrestok.ru"
API = "https://x5m.x5.ru/tcx/api"
OUT = "perekrestok_products.json"
RAW_DIR = "overviews_pr"
STORE = "XSEO"

CATEGORIES_URL = (
    f"{API}/catalog/v4/stores/{STORE}/categories"
    "?mode=store&include_subcategories=1&include_restrict=true&available_status=all"
)
OVERVIEW_URL = (
    f"{API}/catalog/v4/stores/{STORE}/categories/{{cid}}/overview?mode=store"
)


def is_product(node) -> bool:
    """Универсальный детектор карточки: имя + что-то ценовое + идентификатор."""
    if not isinstance(node, dict):
        return False
    keys = set(node)
    has_name = "name" in node
    has_price = bool(keys & {"prices", "price", "current_price", "price_info", "old_price"})
    has_id = bool(keys & {"plu", "id", "code", "sku"})
    return has_name and has_price and has_id


def iter_products(node):
    if isinstance(node, dict):
        if is_product(node):
            yield node
        else:
            for v in node.values():
                yield from iter_products(v)
    elif isinstance(node, list):
        for v in node:
            yield from iter_products(v)


def iter_subcategories(node):
    if isinstance(node, dict):
        if node.get("id") and node.get("name") and not is_product(node):
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


def get_price(prices: dict):
    for k in ("regular", "current", "current_price", "value", "price"):
        if isinstance(prices, dict) and prices.get(k) is not None:
            return prices[k]
    return None


def absorb(overview: dict, category_name: str, seen: dict) -> tuple[int, int]:
    added, total = 0, 0
    for p in iter_products(overview):
        total += 1
        pid = p.get("plu") or p.get("id") or p.get("code")
        if pid is None:
            continue
        prices = p.get("prices") or p.get("price_info") or {}
        promo = (prices.get("discount") or prices.get("old_price")
                 or prices.get("previous_price"))
        price = get_price(prices)
        item = {
            "retailer": "perekrestok",
            "product_id": pid,
            "name": p.get("name"),
            "category_path": [category_name],
            "price": price,
            "promo_price": promo,
            "store_id": STORE,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "raw_keys": sorted(prices.keys()) if isinstance(prices, dict) else None,
        }
        if pid in seen:
            if category_name not in seen[pid]["category_path"]:
                seen[pid]["category_path"].append(category_name)
        else:
            seen[pid] = item
            added += 1
    return added, total


async def fetch_json(page, url):
    return await page.evaluate(
        """async (url) => {
             const r = await fetch(url, {credentials: "include"});
             if (!r.ok) return {__status__: r.status};
             return await r.json();
           }""",
        url,
    )


async def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    seen: dict = {}

    async with AsyncCamoufox(headless=True, geoip=False) as browser:
        page = await browser.new_page()

        await page.goto(f"{BASE}/cat/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        tree = await fetch_json(page, CATEGORIES_URL)
        if isinstance(tree, dict) and tree.get("__status__"):
            raise SystemExit(f"Категории не получены: HTTP {tree['__status__']}")
        cats = collect_top_categories(tree)
        print(f"Категорий верхнего уровня: {len(cats)}")
        json.dump(tree, open(f"{RAW_DIR}/tree.json", "w", encoding="utf-8"),
                  ensure_ascii=False)
        if not cats:
            print("Дерево неожиданной структуры, фрагмент:",
                  json.dumps(tree, ensure_ascii=False)[:600])
            return

        # --- проба: первая категория, смотрим структуру товара ---
        first = cats[0]
        ov = await fetch_json(page, OVERVIEW_URL.format(cid=first["id"]))
        if isinstance(ov, dict) and ov.get("__status__"):
            print(f"Проба overview: HTTP {ov['__status__']} — видимо, другой эндпоинт")
            return
        json.dump(ov, open(f"{RAW_DIR}/{first['id']}.json", "w", encoding="utf-8"),
                  ensure_ascii=False)
        products = list(iter_products(ov))
        print(f"Проба {first['name']}: найдено товаров {len(products)}")
        if products:
            sample = json.dumps(products[0], ensure_ascii=False)
            print("Образец товара:", sample[:1500])
            added, total = absorb(ov, first["name"], seen)
            print(f"[+] {first['name']}: позиций {total}, новых {added}")
        else:
            print("Товары не найдены детектором — структура другая.")
            print("Фрагмент overview:", json.dumps(ov, ensure_ascii=False)[:800])
            print(">>> пришли этот вывод, поправлю парсер за один ход")
            return

        # --- основной обход ---
        for cat in cats[1:]:
            cid, name = cat["id"], cat["name"]
            ov = None
            for attempt in (1, 2, 3):
                try:
                    ov = await fetch_json(page, OVERVIEW_URL.format(cid=cid))
                except Exception as e:
                    print(f"{name}: ошибка fetch — {e}")
                if ov and not ov.get("__status__"):
                    break
                if ov and ov.get("__status__"):
                    print(f"  {name}: HTTP {ov['__status__']}, попытка {attempt}")
                ov = None
                await asyncio.sleep(5)
            if not ov:
                print(f"[!] {name} ({cid}): не получен — пропускаю")
                continue

            json.dump(ov, open(f"{RAW_DIR}/{cid}.json", "w", encoding="utf-8"),
                      ensure_ascii=False)
            added, total = absorb(ov, name, seen)
            want = ov.get("products_count") or total
            print(f"[+] {name}: позиций {total} (count={want}), новых {added}, всего {len(seen)}")

            if total < want:
                subs = [s for s in iter_subcategories(ov) if s["id"] != cid]
                print(f"    [~] недобор {want - total}: докачиваю {len(subs)} подкатегорий")
                for sub in subs:
                    sub_ov = None
                    for attempt in (1, 2):
                        try:
                            sub_ov = await fetch_json(page, OVERVIEW_URL.format(cid=sub["id"]))
                        except Exception:
                            pass
                        if sub_ov and not sub_ov.get("__status__"):
                            break
                        sub_ov = None
                        await asyncio.sleep(3)
                    if sub_ov:
                        json.dump(sub_ov, open(f"{RAW_DIR}/{sub['id']}.json", "w",
                                               encoding="utf-8"), ensure_ascii=False)
                        a2, t2 = absorb(sub_ov, name, seen)
                        print(f"      + {sub['name']}: позиций {t2}, новых {a2}")
                    await asyncio.sleep(random.uniform(1.0, 2.0))

            await asyncio.sleep(random.uniform(1.5, 3.0))

    json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nИТОГ: {len(seen)} товаров -> {OUT}")


asyncio.run(main())
