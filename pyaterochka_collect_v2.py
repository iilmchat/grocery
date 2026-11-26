import asyncio
import json
import os
import re
from datetime import datetime, timezone

from camoufox.async_api import AsyncCamoufox

OUT = "pyaterochka_products.json"
LINKS_FILE = "pyaterochka_links.json"
DONE_FILE = "pyaterochka_done.json"
BASE = "https://5ka.ru"

SCROLL_WAIT_SEC = 20     # сколько ждём новые карточки после прокрута
POLL_INTERVAL = 1.5      # с каким шагом опрашиваем DOM
EMPTY_STOP = 3           # пустых попыток подряд — конец списка
MAX_ROUNDS = 200         # страховка от бесконечного цикла

PARSE_CARDS = """() => {
    const cards = [];
    document.querySelectorAll('[data-qa^="product-card-"]').forEach(card => {
        const m = (card.getAttribute("data-qa") || "").match(/product-card-(\\d+)/);
        const pid = m ? m[1] : null;
        const a = card.querySelector("a[href*='/product/']");
        const img = card.querySelector("img");
        const nameEl = card.querySelector("h2, h3, img[alt]");
        const offer = card.querySelector('[itemtype*="schema.org/Offer"]');
        const priceEl = offer ? offer.querySelector('[itemprop="price"]') : null;
        const badge = card.querySelector("[class*='badge'], [class*='label']");
        cards.push({
            id: pid,
            href: a ? a.getAttribute("href") : null,
            name: nameEl ? (nameEl.getAttribute("alt") || nameEl.textContent.trim()) : null,
            image: img ? img.src : null,
            offer_text: offer ? offer.textContent.trim().slice(0, 300) : null,
            price_attr: priceEl ? (priceEl.getAttribute("content")
                        || priceEl.getAttribute("data-price")) : null,
            prices_fallback: [...card.querySelectorAll("[class*='price']")]
                .map(p => p.textContent.trim()).filter(t => t).slice(0, 4),
            badge: badge ? badge.textContent.trim().slice(0, 60) : null,
            html_head: card.outerHTML.slice(0, 500),
        });
    });
    return cards;
}"""


def parse_price(texts):
    vals = []
    for t in texts:
        if not t:
            continue
        for n in re.findall(r"\d[\d\s\u00a0]*(?:[.,]\d{1,2})?", t):
            v = re.sub(r"[^\d.,]", "", n).replace("\u00a0", "").replace(" ", "").replace(",", ".")
            try:
                f = float(v)
                if 5 <= f <= 1_000_000:
                    vals.append(f)
            except ValueError:
                pass
    return (min(vals), max(vals)) if vals else (None, None)


def parse_kopecks(raw):
    """Цена из атрибута content у 5ka приходит в копейках."""
    v = re.sub(r"[^\d.,]", "", raw).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        f = float(v)
    except ValueError:
        return None, None
    f /= 100.0
    if 5 <= f <= 1_000_000:
        return f, f
    return None, None


async def scroll_collect(page):
    """Скроллит до упора и терпеливо ждёт догрузку страниц."""
    collected: dict = {}
    empty_streak = 0
    for _ in range(MAX_ROUNDS):
        cards = await page.evaluate(PARSE_CARDS)
        new_count = sum(1 for c in cards if c["id"] and c["id"] not in collected)
        for c in cards:
            if c["id"] and c["id"] not in collected:
                collected[c["id"]] = c

        if new_count:
            empty_streak = 0
        else:
            empty_streak += 1
            if empty_streak >= EMPTY_STOP:
                break

        # прокрут в самый низ — чтобы скелетоны вошли в вьюпорт и триггер сработал
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        # терпеливо ждём появления новых карточек
        got_new = False
        waited = 0.0
        while waited < SCROLL_WAIT_SEC:
            await page.wait_for_timeout(int(POLL_INTERVAL * 1000))
            waited += POLL_INTERVAL
            cards = await page.evaluate(PARSE_CARDS)
            for c in cards:
                if c["id"] and c["id"] not in collected:
                    collected[c["id"]] = c
                    got_new = True
            if got_new:
                break

    return list(collected.values())



async def main():
    seen: dict = {}
    if os.path.exists(OUT):
        for it in json.load(open(OUT, encoding="utf-8")):
            key = it.get("product_id") or it.get("url")
            if key:
                seen[key] = it
        print(f"[cache] товаров из прошлого прогона: {len(seen)}")

    async with AsyncCamoufox(
        headless=True,
        persistent_context=True,
        user_data_dir="profile_5ka",
        i_know_what_im_doing=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        links = []
        if os.path.exists(LINKS_FILE):
            links = json.load(open(LINKS_FILE, encoding="utf-8"))
            print(f"[cache] ссылок из файла: {len(links)}")
        if not links:  # пустой кеш — пересобираем
            await page.goto(f"{BASE}/catalog/", wait_until="domcontentloaded", timeout=60000)
            for attempt in range(3):
                # ждём до 40 сек, пока дерево категорий отрендерится
                for _ in range(10):
                    await page.wait_for_timeout(4000)
                    links = await page.evaluate("""() => {
                        const out = new Set();
                        document.querySelectorAll("a[href*='/catalog/']").forEach(a => {
                            const h = a.getAttribute("href");
                            if (h && h.includes("--")) out.add(h);
                        });
                        return [...out];
                    }""")
                    if len(links) >= 20:
                        break
                if len(links) >= 20:
                    break
                print(f"    [retry] ссылок {len(links)} — перезагружаю страницу (попытка {attempt + 1})")
                await page.goto(f"{BASE}/catalog/", wait_until="networkidle",
                                timeout=60000)
            json.dump(links, open(LINKS_FILE, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            print(f"[new] ссылок собрано: {len(links)}")

        done = (json.load(open(DONE_FILE, encoding="utf-8"))
                if os.path.exists(DONE_FILE) else [])

        sample_printed = False

        for i, link in enumerate(links, 1):
            if link in done:
                continue
            url = link if link.startswith("http") else BASE + link
            slug = re.sub(r"--\w+", "", link.replace("/catalog/", "").strip("/")) or link

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(6000)

                content = await page.content()
                if "такой страницы больше нет" in content:
                    print(f"[404] {slug}: категория мертва — помечаю как пройденную")
                    done.append(link)
                    json.dump(done, open(DONE_FILE, "w", encoding="utf-8"))
                    continue
                if "captcha" in content.lower():
                    print(f"[!] {slug}: капча на странице — останавливаю прогон")
                    break

                cards = await scroll_collect(page)
            except Exception as e:
                print(f"[!] {slug}: {type(e).__name__}: {str(e)[:100]} — пропускаю")
                await asyncio.sleep(30)
                continue

            if not cards:
                print(f"[0] {slug}: пусто — пауза 60 сек")
                await asyncio.sleep(60)
                continue

            if not sample_printed:
                print("    образец HTML карточки:", cards[0]["html_head"][:500])
                sample_printed = True

            added = 0
            priced = 0
            for c in cards:
                key = c["id"] or c["href"]
                if not key:
                    continue
                pmin, pmax = None, None
                if c["price_attr"]:
                    pmin, pmax = parse_kopecks(c["price_attr"])
                if pmin is None:
                    pmin, pmax = parse_price(
                        ([c["offer_text"]] if c["offer_text"] else [])
                        + c["prices_fallback"])
                item = {
                    "retailer": "pyaterochka",
                    "product_id": c["id"],
                    "url": BASE + c["href"] if c["href"] and not c["href"].startswith("http") else c["href"],
                    "name": (c["name"] or "").strip(),
                    "image_url": c["image"],
                    "category_slug": slug,
                    "badge": c["badge"],
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                }
                if pmin is not None:
                    item["price_min"], item["price_max"] = pmin, pmax
                if key in seen:
                    if pmin is not None and "price_min" not in seen[key]:
                        seen[key]["price_min"], seen[key]["price_max"] = pmin, pmax
                        priced += 1
                    continue
                seen[key] = item
                added += 1

            print(f"[+] {i}/{len(links)} {slug}: карточек {len(cards)}, "
                  f"новых {added}, добито цен {priced}, всего {len(seen)}")

            # сначала товары, потом done — прерывание всегда консистентно
            json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            done.append(link)
            json.dump(done, open(DONE_FILE, "w", encoding="utf-8"))

            await asyncio.sleep(8)

    json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nИТОГ: {len(seen)} товаров -> {OUT}")
    if seen:
        with_price = sum(1 for v in seen.values() if "price_min" in v)
        print(f"с ценами: {with_price} из {len(seen)}")
        sample = list(seen.values())[0]
        print("образец записи:", json.dumps(sample, ensure_ascii=False)[:500])

asyncio.run(main())
