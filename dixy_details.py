import asyncio
import json
import os
import re
from datetime import datetime, timezone

from camoufox.async_api import AsyncCamoufox

DETAILS = "dixy_details.json"
DONE_FILE = "dixy_details_done.json"
SOURCE = "dixy_products.json"

PAUSE_SEC = 1.5          # пауза между товарами
CHECKPOINT_EVERY = 25    # раз в N товаров пишем чекпоинт
ERR_STREAK_STOP = 8      # подряд ошибок — остановка (сайт не в духе)


def parse_ld_product(entry):
    """Вытаскивает поля Product из одного ld+json блока."""
    if not isinstance(entry, dict):
        return None
    if entry.get("@type") == "Product":
        return entry
    if isinstance(entry.get("@graph"), list):
        for g in entry["@graph"]:
            if g.get("@type") == "Product":
                return g
    return None


def parse_price_val(raw):
    if raw is None:
        return None
    try:
        v = float(str(raw).replace(",", ".").strip())
    except ValueError:
        return None
    return v if 5 <= v <= 1_000_000 else None


async def extract(page):
    data = await page.evaluate("""() => {
        const ld = [];
        document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
            try { ld.push(JSON.parse(s.textContent)); } catch(e) {}
        });
        const body = document.body.innerText || "";
        const crumbs = (body.match(/Главная\\s*\\n?\\s*Каталог([\\s\\S]{0,400}?)\\n(?=[А-ЯA-Z][а-яa-z]{2,})/) || [])[1] || null;
        const avail = (body.match(/В наличии в (\\d+) магаз/) || [])[1] || null;
        const rating = (body.match(/\\n(\\d(?:[.,]\\d)?)\\n\\d+ отзывов/) || [])[1] || null;
        const reviews = (body.match(/\\d(?:[.,]\\d)?\\n(\\d+) отзывов/) || [])[1] || null;
        const h1 = document.querySelector("h1")?.textContent.trim() || null;
        return {ld, crumbs, avail, rating, reviews, h1};
    }""")
    return data


async def main():
    products = json.load(open(SOURCE, encoding="utf-8"))
    print(f"[source] товаров в базе: {len(products)}")

    details = {}
    if os.path.exists(DETAILS):
        for it in json.load(open(DETAILS, encoding="utf-8")):
            details[it["product_id"]] = it
        print(f"[cache] деталей из прошлого прогона: {len(details)}")

    done = set(json.load(open(DONE_FILE, encoding="utf-8"))
               if os.path.exists(DONE_FILE) else [])

    try:
        async with AsyncCamoufox(headless=True, i_know_what_im_doing=True) as browser:
            page = await browser.new_page()
            err_streak = 0

            for i, prod in enumerate(products, 1):
                pid = str(prod.get("product_id") or "")
                url = prod.get("url") or ""
                if not pid or not url or pid in done:
                    continue

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_timeout(3000)
                    raw = await extract(page)
                    err_streak = 0
                except Exception as e:
                    print(f"[!] {pid}: {type(e).__name__}: {str(e)[:80]} — пауза 30 сек")
                    err_streak += 1
                    if err_streak >= ERR_STREAK_STOP:
                        print("[!] много ошибок подряд — останавливаю прогон, резюм сохранён")
                        break
                    await asyncio.sleep(30)
                    continue

                item = {
                    "retailer": "dixy",
                    "product_id": pid,
                    "url": url,
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                }

                # ld+json: описание, бренд, цена, sku
                for entry in raw["ld"]:
                    prod_ld = parse_ld_product(entry)
                    if not prod_ld:
                        continue
                    item["name"] = prod_ld.get("name")
                    item["description"] = (prod_ld.get("description") or "").strip() or None
                    brand = prod_ld.get("brand")
                    if isinstance(brand, dict):
                        brand = brand.get("name")
                    item["brand"] = brand
                    item["sku"] = prod_ld.get("sku")
                    offers = prod_ld.get("offers") or {}
                    item["price"] = parse_price_val(offers.get("price"))
                    item["price_currency"] = offers.get("priceCurrency")
                    break

                # крошки: "Каталог < Категория > Подкатегория"
                if raw["crumbs"]:
                    cr = re.sub(r"\s+", " ", raw["crumbs"]).strip(" \n")
                    cr = re.split(r"\s*[>»]\s*|\n", cr)
                    cr = [x.strip() for x in cr if x.strip()]
                    item["breadcrumbs"] = cr

                if raw["avail"]:
                    item["stores_count"] = int(raw["avail"])
                if raw["rating"]:
                    item["rating"] = raw["rating"].replace(",", ".")
                if raw["reviews"]:
                    item["reviews_count"] = int(raw["reviews"])

                details[pid] = item
                done.add(pid)

                if i % CHECKPOINT_EVERY == 0:
                    json.dump(list(details.values()), open(DETAILS, "w", encoding="utf-8"),
                              ensure_ascii=False, indent=2)
                    json.dump(sorted(done), open(DONE_FILE, "w", encoding="utf-8"))
                    print(f"[+] {i}/{len(products)} всего деталей {len(details)} "
                          f"[checkpoint]")

                await asyncio.sleep(PAUSE_SEC)

    finally:
        # пишем хвост при любом исходе: и после break по ошибкам,
        # и при падении Browser.close (известный Camoufox-teardown)
        json.dump(list(details.values()), open(DETAILS, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        json.dump(sorted(done), open(DONE_FILE, "w", encoding="utf-8"))
        print(f"\nИТОГ: {len(details)} деталей -> {DETAILS}")
        if details:
            sample = list(details.values())[0]
            print("образец:", json.dumps(sample, ensure_ascii=False)[:600])

# === КОНЕЦ ФАЙЛА: если видишь эту строку, хвост скопировался целиком ===

asyncio.run(main())
