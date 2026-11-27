import asyncio
import json
import os
import random
import re
from datetime import datetime, timezone

from camoufox.async_api import AsyncCamoufox

OUT = "perekrestok_products.json"
LINKS_FILE = "perekrestok_links.json"
DONE_FILE = "perekrestok_done.json"
BASE = "https://www.perekrestok.ru"

SCROLL_WAIT_SEC = 12     # сколько ждём новые карточки после прокрута
POLL_INTERVAL = 1.0      # с каким шагом опрашиваем DOM
MAX_ROUNDS = 200         # страховка от бесконечного цикла

PARSE_CARDS = """() => {
    const cards = [];
    document.querySelectorAll('[data-qa^="product-card-"]').forEach(card => {
        const m = (card.getAttribute("data-qa") || "").match(/product-card-(\\d+)/);
        const pid = m ? m[1] : null;
        const a = card.querySelector('a[href*="/product/"]');
        const img = card.querySelector("img");
        const nameEl = card.querySelector('img[alt], h2, h3');
        const metaAll = [...card.querySelectorAll('meta[itemprop="price"]')]
            .map(x => x.getAttribute("content"));
        const rublesAll = [...card.querySelectorAll('[data-qa="price-tag-rubles"]')]
            .map(x => x.textContent.trim());
        const penniesAll = [...card.querySelectorAll('[data-qa="price-tag-pennies"]')]
            .map(x => x.textContent.trim());
        const badge = card.querySelector("h2[type], .chakra-badge");
        cards.push({
            id: pid,
            href: a ? a.getAttribute("href") : null,
            name: nameEl ? (nameEl.getAttribute("alt") || nameEl.textContent.trim()) : null,
            image: img ? img.src : null,
            meta_prices: metaAll,
            rubles_list: rublesAll,
            pennies_list: penniesAll,
            prices_fallback: [...card.querySelectorAll("[class*='price']")]
                .map(p => p.textContent.trim()).filter(t => t).slice(0, 4),
            badge: badge ? badge.textContent.trim().slice(0, 60) : null,
            html_head: card.outerHTML.slice(0, 500),
        });
    });
    return cards;
}"""


def _ok(v):
    return v is not None and 5 <= v <= 1_000_000


def price_from_meta(raw):
    """content у meta[itemprop=price] — рубли с копейками: '379.99'."""
    if not raw:
        return None
    m = re.search(r"\d[\d\s\u00a0.,]*", raw)
    if not m:
        return None
    v = m.group(0).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        f = float(v)
    except ValueError:
        return None
    return f if _ok(f) else None


def price_from_spans(rubles, pennies):
    """'379' + '99' -> 379.99."""
    if not rubles:
        return None
    if not re.fullmatch(r"[\d\s\u00a0]+", rubles.strip()):
        return None
    rub = int(re.sub(r"[^\d]", "", rubles))
    pen = 0
    if pennies:
        pm = re.fullmatch(r"\d{1,2}", pennies.strip())
        if pm:
            pen = int(pm.group(0))
    v = rub + pen / 100.0
    return v if _ok(v) else None


def _chunk_to_price(chunk):
    """'95 99' -> 95.99; '1 349 99' -> 1349.99; '129,99' -> 129.99; '129' -> 129.0"""
    chunk = chunk.replace("\u00a0", " ").strip()
    m = re.fullmatch(r"(\d{1,3}(?: \d{3})*|\d+) (\d{2})", chunk)
    if m:
        return float(f"{m.group(1).replace(' ', '')}.{m.group(2)}")
    m = re.fullmatch(r"\d{1,9}(?:[.,]\d{1,2})?", chunk)
    if m:
        return float(chunk.replace(",", "."))
    return None


def parse_price(texts):
    """Фолбэк: цены только рядом со знаком ₽ — рейтинги не трогаем."""
    vals = []
    for t in texts:
        if not t:
            continue
        for m in re.finditer(r"([\d\s\u00a0.,]{1,15}?)\s*₽", t):
            v = _chunk_to_price(m.group(1))
            if v is not None and _ok(v):
                vals.append(v)
    return (min(vals), max(vals)) if vals else (None, None)


async def is_captcha(page):
    """Капча по заголовку страницы или реальному виджету, а не по слову в HTML."""
    title = (await page.title()).lower()
    widget = await page.locator(
        "iframe[src*='challenge'], [class*='captcha'], [id*='captcha']"
    ).count()
    return (widget > 0 or "captcha" in title
            or "доступ ограничен" in title), await page.title()


async def scroll_collect(page):
    """Перекрёсток: скролл через контейнеры + колёсико над карточками."""
    collected: dict = {}
    stable_rounds = 0
    last_count = 0

    SCROLL_JS = """() => {
        const els = [...document.querySelectorAll('*')].filter(e => {
            const s = getComputedStyle(e);
            return (s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                   e.scrollHeight > e.clientHeight + 100 && e.clientHeight > 200;
        });
        for (const el of els) el.scrollTop = el.scrollHeight;
        window.scrollTo(0, document.body.scrollHeight);
        return els.length;
    }"""

    for _ in range(MAX_ROUNDS):
        cards = await page.evaluate(PARSE_CARDS)
        for c in cards:
            if c["id"] and c["id"] not in collected:
                collected[c["id"]] = c

        n = len(collected)
        if n == last_count:
            stable_rounds += 1
            if stable_rounds >= 3:      # три круга без новых — конец списка
                break
        else:
            stable_rounds = 0
        last_count = n

        # 1) программный дожим всех контейнеров
        await page.evaluate(SCROLL_JS)
        await page.wait_for_timeout(400 + random.randint(0, 400))

        # 2) колёсико над зоной карточек — самый «человеческий» сигнал
        await page.mouse.move(960, 600)
        await page.mouse.wheel(0, 1200)
        await page.wait_for_timeout(int(POLL_INTERVAL * 1000) + random.randint(0, 300))

        if stable_rounds >= 1:
            # дёрганье: чуть вверх и снова вниз внутри активного скролла
            await page.mouse.wheel(0, -2000)
            await page.wait_for_timeout(300 + random.randint(0, 300))
            await page.mouse.wheel(0, 2600)

    return list(collected.values())
# === КОНЕЦ scroll_collect: если видишь эту строку, блок скопировался целиком ===


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

        # человеческий вход: главная, пауза, лёгкий скролл — прежде чем лезть в категории
        try:
            await page.goto(BASE, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(random.randint(5000, 9000))
            await page.evaluate(
                "window.scrollTo(0, document.body.scrollHeight * 0.3)")
            await page.wait_for_timeout(random.randint(1500, 3500))
            await page.evaluate("window.scrollTo(0, 0)")
            print("[warmup] главная открыта, пауза выдержана")
        except Exception as e:
            print(f"[warmup] не получилось ({type(e).__name__}) — идём дальше")

        links = []
        if os.path.exists(LINKS_FILE):
            links = json.load(open(LINKS_FILE, encoding="utf-8"))
            print(f"[cache] ссылок из файла: {len(links)}")
        if not links:
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

        sample_printed = False

        for i, link in enumerate(links, 1):
            if link in done:
                continue
            url = link if link.startswith("http") else BASE + link
            slug = re.sub(r"--\w+", "", link.replace("/catalog/", "").strip("/")) or link

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(random.randint(4000, 8000))

                captcha, title = await is_captcha(page)
                if captcha:
                    print(f"[!] {slug}: капча (title={title!r}) — пауза 10 мин, повторю категорию")
                    resumed = False
                    for attempt in range(3):
                        await asyncio.sleep(600)
                        await page.goto(url, wait_until="domcontentloaded",
                                        timeout=60000)
                        await page.wait_for_timeout(random.randint(4000, 8000))
                        captcha, title = await is_captcha(page)
                        if not captcha:
                            resumed = True
                            break
                        print(f"    [captcha] попытка {attempt + 1}: ещё держится")
                    if not resumed:
                        print("[!] капча не ушла за 3 попытки — останавливаю прогон")
                        break

                cards = await scroll_collect(page)
            except Exception as e:
                print(f"[!] {slug}: {type(e).__name__}: {str(e)[:100]} — пропускаю")
                await asyncio.sleep(random.uniform(25, 45))
                continue

            if not cards:
                print(f"[0] {slug}: пусто — пауза {int(random.uniform(60, 90))} сек")
                await asyncio.sleep(random.uniform(60, 90))
                continue

            if not sample_printed:
                print("    образец HTML карточки:", cards[0]["html_head"][:500])
                sample_printed = True

            added = 0
            priced = 0
            for c in cards:
                pid = c["id"] or c["href"]
                if not pid:
                    continue

                # собираем все цены в карточке: обычная + акционная
                candidates = []
                for raw in (c.get("meta_prices") or []):
                    v = price_from_meta(raw)
                    if v is not None:
                        candidates.append(v)
                for rub, pen in zip(c.get("rubles_list") or [],
                                    c.get("pennies_list") or []):
                    v = price_from_spans(rub, pen)
                    if v is not None:
                        candidates.append(v)
                if not candidates:
                    pmin, pmax = parse_price(c.get("prices_fallback") or [])
                    if pmin is not None:
                        candidates.append(pmin)
                        if pmax is not None:
                            candidates.append(pmax)
                if candidates:
                    pmin, pmax = min(candidates), max(candidates)
                else:
                    pmin, pmax = None, None

                item = {
                    "retailer": "perekrestok",
                    "product_id": pid,
                    "url": BASE + c["href"] if c["href"] and not c["href"].startswith("http") else c["href"],
                    "name": (c["name"] or "").strip(),
                    "image_url": c["image"],
                    "category_slug": slug,
                    "badge": c["badge"],
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                }
                if pmin is not None:
                    item["price_min"], item["price_max"] = pmin, pmax
                if pid in seen:
                    # свежая цена всегда перезаписывает старую
                    if pmin is not None:
                        seen[pid]["price_min"], seen[pid]["price_max"] = pmin, pmax
                        priced += 1
                    continue
                seen[pid] = item
                added += 1

            print(f"[+] {i}/{len(links)} {slug}: карточек {len(cards)}, "
                  f"новых {added}, обновлено цен {priced}, всего {len(seen)}")

            # сначала товары, потом done — прерывание всегда консистентно
            json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            done.append(link)
            json.dump(done, open(DONE_FILE, "w", encoding="utf-8"))

            # человеческая пауза между категориями: 8–20 секунд, каждый раз разная
            await asyncio.sleep(random.uniform(8, 20))

    json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nИТОГ: {len(seen)} товаров -> {OUT}")
    if seen:
        with_price = sum(1 for v in seen.values() if "price_min" in v)
        print(f"с ценами: {with_price} из {len(seen)}")
        sample = list(seen.values())[0]
        print("образец записи:", json.dumps(sample, ensure_ascii=False)[:500])

# === КОНЕЦ ФАЙЛА: если видишь эту строку, хвост скопировался целиком ===

asyncio.run(main())
