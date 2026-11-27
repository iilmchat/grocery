import asyncio
import json
import os
import random
import re
from datetime import datetime, timezone

from camoufox.async_api import AsyncCamoufox

OUT = "dixy_products.json"
LINKS_FILE = "dixy_links.json"
DONE_FILE = "dixy_done.json"
EMPTY_FILE = "dixy_empty.json"
BASE = "https://dixy.ru"

PARSE_CARDS = """() => {
    const cards = [];
    document.querySelectorAll("article.card").forEach(card => {
        const pid = card.getAttribute("product-id") || card.getAttribute("data-id");
        const a = card.querySelector("a.card__link, a[href*='/product']");
        const titleEl = card.querySelector(".card__title");
        const img = card.querySelector("img.card-image, img");
        const ratingEl = card.querySelector(".card__rating span");
        const badgeEl = card.querySelector(".badge");
        const oldEl = card.querySelector(".card__price-crossed");
        const newEl = card.querySelector(".card__price-num");
        cards.push({
            id: pid,
            href: a ? a.getAttribute("href") : null,
            name: titleEl ? titleEl.textContent.trim() : null,
            image: img ? (img.src || img.getAttribute("data-src")) : null,
            rating: ratingEl ? ratingEl.textContent.trim() : null,
            badge: badgeEl ? badgeEl.textContent.trim() : null,
            section: card.getAttribute("data-section"),
            old_price: oldEl ? oldEl.textContent.trim() : null,
            new_price: newEl ? newEl.textContent.trim() : null,
        });
    });
    return cards;
}"""


def _price_from_str(s):
    """'69.99руб.' -> 69.99; '1 049.00руб.' -> 1049.0"""
    if not s:
        return None
    m = re.search(r"(\d[\d\s\u00a0]*)[.,](\d{2})", s)
    if not m:
        return None
    v = float(m.group(1).replace("\u00a0", "").replace(" ", "") + "." + m.group(2))
    return v if 5 <= v <= 1_000_000 else None


async def goto_retry(page, url, tries=3):
    """goto с повторами: DNS-сбои и обрывы навигации не роняют категорию."""
    for attempt in range(1, tries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return
        except Exception as e:
            if attempt == tries:
                raise
            print(f"    [retry {attempt}] goto: {type(e).__name__}: {str(e)[:60]}")
            await asyncio.sleep(10 * attempt)


async def load_all(page):
    """Догружает ленту: кнопка 'ещё' или скролл-насыщение."""
    for _ in range(60):
        before = await page.evaluate("document.querySelectorAll('article.card').length")
        clicked = False
        for sel in ["button:has-text('Показать ещё')",
                    "button:has-text('показать ещё')",
                    "[class*=more] button", "[class*=show-more]"]:
            try:
                btn = page.locator(sel).first
                if await btn.count():
                    await btn.click(timeout=5000)
                    await page.wait_for_timeout(3000)
                    clicked = True
                    break
            except Exception:
                continue
        after = await page.evaluate("document.querySelectorAll('article.card').length")
        if not clicked and after == before:
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(2500)
            if await page.evaluate("document.querySelectorAll('article.card').length") == before:
                break
    return await page.evaluate(PARSE_CARDS)


async def main():
    seen: dict = {}
    if os.path.exists(OUT):
        for it in json.load(open(OUT, encoding="utf-8")):
            key = it.get("product_key") or it.get("url") or ""
            if key.startswith(BASE):
                key = key[len(BASE):]
            seen[key] = it
        print(f"[cache] товаров из прошлого прогона: {len(seen)}")

    try:
        async with AsyncCamoufox(headless=True, i_know_what_im_doing=True) as browser:
            page = await browser.new_page()

            if os.path.exists(LINKS_FILE):
                links = json.load(open(LINKS_FILE, encoding="utf-8"))
                print(f"[cache] ссылок из файла: {len(links)}")
            else:
                await goto_retry(page, f"{BASE}/catalog/")
                await page.wait_for_timeout(8000)
                links = await page.evaluate("""() => {
                    const out = new Set();
                    document.querySelectorAll("a[href*='/catalog/']").forEach(a =>
                        out.add(a.getAttribute("href")));
                    return [...out];
                }""")
                json.dump(links, open(LINKS_FILE, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
                print(f"[new] ссылок собрано: {len(links)}")

            done = (json.load(open(DONE_FILE, encoding="utf-8"))
                    if os.path.exists(DONE_FILE) else [])
            empty_counts = (json.load(open(EMPTY_FILE, encoding="utf-8"))
                            if os.path.exists(EMPTY_FILE) else {})

            sample_printed = False

            for i, link in enumerate(links, 1):
                if link in done:
                    continue
                url = link if link.startswith("http") else BASE + link
                slug = link.replace("/catalog/", "").strip("/").replace("/", "_") or "root"

                try:
                    await goto_retry(page, url)
                    await page.wait_for_timeout(6000)
                    cards = await load_all(page)
                except Exception as e:
                    print(f"[!] {i}/{len(links)} {slug}: {type(e).__name__}: {str(e)[:100]} — пропускаю")
                    await asyncio.sleep(random.uniform(25, 45))
                    continue

                if not cards:
                    empty_counts[link] = empty_counts.get(link, 0) + 1
                    if empty_counts[link] >= 2:
                        print(f"[0] {i}/{len(links)} {slug}: пусто второй раз — помечаю done")
                        done.append(link)
                        json.dump(done, open(DONE_FILE, "w", encoding="utf-8"))
                        json.dump(empty_counts, open(EMPTY_FILE, "w", encoding="utf-8"))
                        continue
                    print(f"[0] {i}/{len(links)} {slug}: пусто — пауза 60 сек, проверю ещё раз")
                    await asyncio.sleep(60)
                    continue

                if not sample_printed:
                    print("    образец карточки:", json.dumps(cards[0], ensure_ascii=False)[:400])
                    sample_printed = True

                added = 0
                updated = 0
                for c in cards:
                    key = c["href"]
                    if not key:
                        continue
                    new_p = _price_from_str(c["new_price"]) or _price_from_str(c["old_price"])
                    old_p = _price_from_str(c["old_price"]) if _price_from_str(c["new_price"]) else None

                    if key in seen:
                        it = seen[key]
                        if new_p is not None:
                            it["price_min"] = it["price_max"] = new_p
                        it["price_old"] = old_p
                        it["rating"] = c["rating"]
                        it["badge"] = c["badge"]
                        it["category_name"] = c["section"]
                        it["scraped_at"] = datetime.now(timezone.utc).isoformat()
                        updated += 1
                        continue

                    seen[key] = {
                        "retailer": "dixy",
                        "product_id": c["id"],
                        "product_key": key,
                        "url": BASE + key if not key.startswith("http") else key,
                        "name": (c["name"] or "").strip(),
                        "image_url": c["image"],
                        "category_slug": slug,
                        "category_name": c["section"],
                        "rating": c["rating"],
                        "badge": c["badge"],
                        "price_min": new_p,
                        "price_max": new_p,
                        "price_old": old_p,
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                    }
                    added += 1

                print(f"[+] {i}/{len(links)} {slug}: карточек {len(cards)}, "
                      f"новых {added}, обновлено {updated}, всего {len(seen)}")

                done.append(link)
                json.dump(done, open(DONE_FILE, "w", encoding="utf-8"))
                if i % 5 == 0:
                    json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
                              ensure_ascii=False, indent=2)
                    print(f"    [checkpoint] {len(seen)} товаров -> {OUT}")

                await asyncio.sleep(random.uniform(3, 6))

    except Exception as e:
        print(f"[teardown] прогон прерван ({type(e).__name__}) — "
              f"чекпоинты целы, резюм подхватит с места остановки")

    json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nИТОГ: {len(seen)} товаров -> {OUT}")
    with_price = sum(1 for v in seen.values() if v.get("price_min") is not None)
    with_old = sum(1 for v in seen.values() if v.get("price_old") is not None)
    print(f"с ценами: {with_price}, со старой ценой: {with_old}")
    if seen:
        print("образец записи:", json.dumps(list(seen.values())[0], ensure_ascii=False)[:600])

# === КОНЕЦ ФАЙЛА: если видишь эту строку, хвост скопировался целиком ===

asyncio.run(main())
