import asyncio
import json
import os
import random
import sys
from datetime import datetime, timezone

from camoufox.async_api import AsyncCamoufox

BASE = "https://5ka.ru"
API = "https://5d.5ka.ru"
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
    delays = [0, 10, 30, 60]
    last_exc = None
    for attempt, d in enumerate(delays):
        if d:
            print(f"    [net] пауза {d}с перед попыткой {attempt + 1}")
            await asyncio.sleep(d)
        try:
            return await page.evaluate(
                """async (url) => {
                     const r = await fetch(url, {credentials: "include"});
                     if (!r.ok) return {__status__: r.status};
                     return await r.json();
                   }""",
                url,
            )
        except Exception as e:
            last_exc = e
            print(f"    [net] попытка {attempt + 1} упала: "
                  f"{type(e).__name__}: {str(e)[:120]}")
            try:
                await page.goto(f"{BASE}/catalog/",
                                wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(5000)
            except Exception as ge:
                print(f"    [net] перезагрузка тоже упала: {type(ge).__name__}")
    return {"__status__": "netfail",
            "__exc__": f"{type(last_exc).__name__}: {str(last_exc)[:150]}"}



def save_out(seen: dict):
    json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


async def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    seen: dict = {}
    consec_netfail = 0

    async with AsyncCamoufox(
        headless=True,
        persistent_context=True,
        user_data_dir="profile_5ka",
        i_know_what_im_doing=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()


        await page.goto(f"{BASE}/catalog/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        tree = await fetch_json(page, CATEGORIES_URL)
        if isinstance(tree, dict) and tree.get("__status__"):
            raise SystemExit(f"Категории не получены: HTTP {tree['__status__']}")
        cats = collect_top_categories(tree)
        print(f"Категорий верхнего уровня: {len(cats)}")
        if not cats:
            print("Дерево неожиданной структуры:",
                  json.dumps(tree, ensure_ascii=False)[:500])
            return

        for i, cat in enumerate(cats, 1):
            cid, name = cat["id"], cat["name"]
            cache_path = os.path.join(RAW_DIR, f"{cid}.json")

            # --- resume: категория уже скачана в прошлый прогон ---
            if os.path.exists(cache_path):
                overview = json.load(open(cache_path, encoding="utf-8"))
                added, total = absorb(overview, name, seen)
                print(f"[cached] {i}/{len(cats)} {name}: позиций {total}, всего {len(seen)}")
                continue

            overview = None
            for ver in ("v2", "v4"):
                resp = await fetch_json(
                    page, f"{API}/catalog/{ver}/stores/{STORE}/categories/{cid}/overview?mode=delivery")
                if resp and resp.get("__status__"):
                    if resp["__status__"] == "netfail":
                        break  # сеть мертва — смысла пробовать v4 нет
                    print(f"    (overview {ver}: HTTP {resp['__status__']})")
                    continue
                if resp:
                    overview = resp
                    break

            if not overview:
                consec_netfail += 1
                print(f"[!] {name} ({cid}): не получен")
                print(f"[!] {name} ({cid}): не получен — {overview.get('__exc__', 'HTTP-ответы')}")
                if consec_netfail >= 3:
                    save_out(seen)
                    print(f"\n[STOP] Три категории подряд без ответа — сервер режет соединения.")
                    print(f"[STOP] Подожди 10-15 минут и запусти снова: прогресс сохранён ({len(seen)} товаров),")
                    print(f"[STOP] собранные категории будут взяты из кеша.")
                    return
                await asyncio.sleep(60)
                continue
            consec_netfail = 0

            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(overview, f, ensure_ascii=False)

            added, total = absorb(overview, name, seen)
            want = overview.get("products_count") or total
            print(f"[+] {i}/{len(cats)} {name}: позиций {total} (count={want}), "
                  f"новых {added}, всего {len(seen)}")

            if total < want:
                subs = [s for s in iter_subcategories(overview) if s["id"] != cid]
                print(f"    [~] недобор {want - total}: докачиваю {len(subs)} подкатегорий")
                for sub in subs:
                    sub_cache = os.path.join(RAW_DIR, f"{sub['id']}.json")
                    if os.path.exists(sub_cache):
                        sub_ov = json.load(open(sub_cache, encoding="utf-8"))
                    else:
                        sub_ov = None
                        for attempt in (1, 2):
                            try:
                                sub_ov = await fetch_json(
                                    page, f"{API}/catalog/v2/stores/{STORE}/categories/{sub['id']}/overview?mode=delivery")
                            except Exception:
                                pass
                            if sub_ov and not sub_ov.get("__status__"):
                                break
                            sub_ov = None
                            await asyncio.sleep(15)
                        if sub_ov:
                            with open(sub_cache, "w", encoding="utf-8") as f:
                                json.dump(sub_ov, f, ensure_ascii=False)
                    if sub_ov:
                        a2, t2 = absorb(sub_ov, name, seen)
                        print(f"      + {sub['name']}: позиций {t2}, новых {a2}")
                    await asyncio.sleep(random.uniform(2.0, 4.0))

            if i % 10 == 0:
                save_out(seen)
                print(f"    [checkpoint] {len(seen)} товаров -> {OUT}")

            await asyncio.sleep(random.uniform(2.0, 4.0))

    save_out(seen)
    print(f"\nИТОГ: {len(seen)} товаров -> {OUT}")


asyncio.run(main())
