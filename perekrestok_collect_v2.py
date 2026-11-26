import asyncio
import json
import os
import re
from datetime import datetime, timezone

from camoufox.async_api import AsyncCamoufox

OUT = "perekrestok_products.json"
LINKS_FILE = "perekrestok_links.json"
DONE_FILE = "perekrestok_done.json"
BASE = "https://www.perekrestok.ru"

PARSE_CARDS = """() => {
    const cards = [];
    document.querySelectorAll('[data-qa^="product-card-"]').forEach(card => {
        const m = (card.getAttribute("data-qa") || "").match(/product-card-(\\d+)/);
        const pid = m ? m[1] : null;
        const a = card.querySelector('a[href*="/product/"]');
        const img = card.querySelector("img");
        const nameEl = card.querySelector('img[alt], h2, h3');
        const offer = card.querySelector('[itemtype*="schema.org/Offer"]');
        const priceEl = offer ? offer.querySelector('[itemprop="price"]') : null;
        const badge = card.querySelector("h2[type], .chakra-badge");
        const rating = card.querySelector('[itemtype*="AggregateRating"]');
        cards.push({
            id: pid,
            href: a ? a.getAttribute("href") : null,
            name: nameEl ? (nameEl.getAttribute("alt") || nameEl.textContent) : null,
            image: img ? img.src : null,
            offer_text: offer ? offer.textContent.trim().slice(0, 300) : null,
            price_attr: priceEl ? priceEl.getAttribute("content")
                        || priceEl.getAttribute("data-price") : null,
            badge: badge ? badge.textContent.trim() : null,
            rating_html: rating ? rating.textContent.trim().slice(0, 100) : null,
        });
    });
    return cards;
}"""


def parse_price(text):
    """Достаёт цены из текста, допускает целые рубли без копеек."""
    if not text:
        return None
    nums = re.findall(r"\d[\d\s\u00a0]*(?:[.,]\d{1,2})?", text)
    vals = []
    for n in nums:
        v = re.sub(r"[^\d.,]", "", n).replace("\u00a0", "").replace(" ", "").replace(",", ".")
        try:
            f = float(v)
            if 5 <= f <= 1_000_000:  # отсечь проценты, рейтинги и мусор
                vals.append(f)
        except ValueError:
            pass
    return (min(vals), max(vals)) if vals else None


async def scroll_collect(page):
    """Крутит страницу до насыщения, парсит карточки."""
    prev, stale = 0, 0
    for _ in range(40):
        cards = await page.evaluate(PARSE_CARDS)
        if len(cards) == prev:
            stale += 1
            if stale >= 3:
                break
        else:
            stale = 0
        prev = len(cards)
        await page.mouse.wheel(0, 4000)
        await page.wait_for_timeout(3500)
    await page.wait_for_timeout(5000)
    return await page.evaluate(PARSE_CARDS)


async def main():
    seen: dict = {}
    if os.path.exists(OUT):
        for it in json.load(open(OUT, encoding="utf-8")):
            seen[it["product_id"]] = it
        print(f"[cache] товаров из прошлого прогона: {len(seen)}")

    async with AsyncCamoufox(
        headless=True,
        persistent_context=True,
        user_data_dir="profile_pk",
        i_know_what_im_doing=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        if os.path.exists(LINKS_FILE):
            links = json.load(open(LINKS_FILE, encoding="utf-8"))
            print(f"[cache] ссылок из файла: {len(links)}")
        else:
            await page.goto(f"{BASE}/cat", wait_until="domcontentloaded", timeout=60000)
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

        for i, link in enumerate(links, 1):
            if link in done:
                continue
            url = link if link.startswith("http") else BASE + link
            slug = re.sub(r"--\w+", "", link.replace("/catalog/", "")) or link

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(6000)

                content = await page.content()
                if "captcha" in content.lower() or "robot" in content.lower():
                    print(f"[!] {slug}: капча на странице — останавливаю прогон")
                    break

                cards = await scroll_collect(page)
            except Exception as e:
                print(f"[!] {slug}: {type(e).__name__}: {str(e)[:100]} — пропускаю")
                await asyncio.sleep(30)
                continue

            if not cards:
                print(f"[0] {slug}: пусто — похоже на кулинг, пауза 60 сек (категория останется в очереди)")
                await asyncio.sleep(60)
                continue

            added = 0
            priced = 0
            for c in cards:
                pid = c["id"] or c["href"]
                if not pid:
                    continue
                prices = parse_price(c["offer_text"])
                item = {
                    "retailer": "perekrestok",
                    "product_id": pid,
                    "name": (c["name"] or "").strip(),
                    "url": BASE + c["href"] if c["href"] and not c["href"].startswith("http") else c["href"],
                    "image_url": c["image"],
                    "category_slug": slug,
                    "badge": c["badge"],
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                }
                if prices:
                    item["price_min"], item["price_max"] = prices
                if pid in seen:
                    if prices and "price_min" not in seen[pid]:
                        seen[pid]["price_min"], seen[pid]["price_max"] = prices
                        priced += 1
                    continue
                seen[pid] = item
                added += 1

            print(f"[+] {i}/{len(links)} {slug}: карточек {len(cards)}, "
                  f"новых {added}, добито цен {priced}, всего {len(seen)}")

            done.append(link)
            json.dump(done, open(DONE_FILE, "w", encoding="utf-8"))
            if i % 5 == 0:
                json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
                print(f"    [checkpoint] {len(seen)} товаров -> {OUT}")

            await asyncio.sleep(8)

    json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nИТОГ: {len(seen)} товаров -> {OUT}")
    if seen:
        with_price = sum(1 for v in seen.values() if "price_min" in v)
        print(f"с ценами: {with_price} из {len(seen)}")
        sample = list(seen.values())[0]
        print("образец записи:", json.dumps(sample, ensure_ascii=False)[:600])

asyncio.run(main())
