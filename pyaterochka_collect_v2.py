import asyncio
import json
import os
import random
import re
from datetime import datetime, timezone

from camoufox.async_api import AsyncCamoufox

OUT = "pyaterochka_products.json"
LINKS_FILE = "pyaterochka_links.json"
DONE_FILE = "pyaterochka_done.json"
BASE = "https://5ka.ru"

SCROLL_WAIT_SEC = 12     # сколько ждём новые карточки после прокрута
POLL_INTERVAL = 1.0      # с каким шагом опрашиваем DOM
MAX_ROUNDS = 200         # страховка от бесконечного цикла

PARSE_CARDS = """() => {
    const cards = [];
    document.querySelectorAll('[data-qa^="product-card-"]').forEach(card => {
        const m = (card.getAttribute("data-qa") || "").match(/product-card-(\\d+)/);
        const pid = m ? m[1] : null;
        const a = card.querySelector("a[href*='/product/']");
        const img = card.querySelector("img");
        const nameEl = card.querySelector("h2, h3, img[alt]");
        const metaAll = [...card.querySelectorAll('meta[itemprop="price"]')]
            .map(x => x.getAttribute("content"));
        const rublesAll = [...card.querySelectorAll('[data-qa="price-tag-rubles"]')]
            .map(x => x.textContent.trim());
        const penniesAll = [...card.querySelectorAll('[data-qa="price-tag-pennies"]')]
            .map(x => x.textContent.trim());
        const badge = card.querySelector("[class*='badge'], [class*='label']");
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
    """Фолбэк: цены только рядом со знаком рубля — рейтинги не трогаем."""
    vals = []
    for t in texts:
        if not t:
            continue
        for m in re.finditer(r"([\d\s\u00a0.,]{1,15}?)\s*₽", t):
            v = _chunk_to_price(m.group(1))
            if v is not None and _ok(v):
                vals.append(v)
    return (min(vals), max(vals)) if vals else (None, None)


async def page_state(page):
    """(заглушка, капча, жёсткий блок) по реальным признакам, а не по слову в HTML.

    Жёсткий блок — страница X5 «Проблемы со связью. Проверьте настройки
    интернета и VPN»: банер целиком на IP, ожиданием за 15 минут не снимается.
    """
    content = await page.content()
    low = content.lower()
    stub = "не смогли загрузить категории" in low
    blocked = "проблемы со связью" in low
    title = (await page.title()).lower()
    widget = await page.locator(
        "iframe[src*='challenge'], [class*='captcha'], [id*='captcha']"
    ).count()
    captcha = widget > 0 or "captcha" in title or "доступ ограничен" in title
    return stub, captcha, blocked


async def scroll_collect(page):
    """Скроллит до упора: конец списка = нет новых карточек И высота не растёт."""
    collected: dict = {}
    stable_rounds = 0
    last_height = 0
    for _ in range(MAX_ROUNDS):
        cards = await page.evaluate(PARSE_CARDS)
        for c in cards:
            if c["id"] and c["id"] not in collected:
                collected[c["id"]] = c

        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        got_new = False
        waited = 0.0
        while waited < SCROLL_WAIT_SEC:
            # джиттер: шаг опроса не идеально ровный
            await page.wait_for_timeout(int(POLL_INTERVAL * 1000) + random.randint(0, 200))
            waited += POLL_INTERVAL
            cards = await page.evaluate(PARSE_CARDS)
            for c in cards:
                if c["id"] and c["id"] not in collected:
                    collected[c["id"]] = c
                    got_new = True
            if got_new:
                break

        # конец списка: не было новых карточек и высота страницы не изменилась
        height = await page.evaluate("document.body.scrollHeight")
        if not got_new and height == last_height:
            stable_rounds += 1
            if stable_rounds >= 2:
                break
        else:
            stable_rounds = 0
        last_height = height

        if not got_new:
            # толчок: вверх на экран и обратно вниз — перезапускает триггер подгрузки
            await page.evaluate(
                "window.scrollTo(0, document.body.scrollHeight - window.innerHeight)")
            await page.wait_for_timeout(400 + random.randint(0, 400))
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

    return list(collected.values())
# === КОНЕЦ scroll_collect: если видишь эту строку, блок скопировался целиком ===


async def main():
    seen: dict = {}
    if os.path.exists(OUT):
        for it in json.load(open(OUT, encoding="utf-8")):
            key = it.get("product_id") or it.get("url")
            if key:
                seen[key] = it
        print(f"[cache] товаров из прошлого прогона: {len(seen)}")

    async with AsyncCamoufox(
        headless=False,
        persistent_context=True,
        user_data_dir="profile_5ka",
        i_know_what_im_doing=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        links = []
        if os.path.exists(LINKS_FILE):
            links = json.load(open(LINKS_FILE, encoding="utf-8"))
            print(f"[cache] ссылок из файла: {len(links)}")
        if not links:
            await page.goto(f"{BASE}/catalog/", wait_until="domcontentloaded", timeout=60000)
            for attempt in range(3):
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

        # стартовая проверка: если главная отдаёт блок-страницу — даже не начинаем
        _stub, _cap, start_blocked = await page_state(page)
        if start_blocked:
            print("[!!] IP заблокирован X5 («Проблемы со связью») — прогон не начинаю. "
                  "Отдых 2–3 часа, потом перезапуск")
            links = []   # цикл пройдёт нулевой длины, хвост запишет кэш как есть

        sample_printed = False
        hard_stop = False

        for i, link in enumerate(links, 1):
            if link in done:
                continue
            url = link if link.startswith("http") else BASE + link
            slug = re.sub(r"--\w+", "", link.replace("/catalog/", "").strip("/")) or link

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(random.randint(4000, 8000))

                stub, captcha, blocked = await page_state(page)
                if blocked:
                    print(f"[!!] {slug}: жёсткий блок IP («Проблемы со связью») — "
                          "останавливаю прогон. Отдых 2–3 часа, потом перезапуск")
                    hard_stop = True
                    break
                if stub:
                    print(f"[!] {slug}: мягкий блок 5ka (заглушка каталога) — останавливаю прогон")
                    break
                if captcha:
                    print(f"[!] {slug}: капча — реши в окне, жду до 15 минут")
                    resumed = False
                    for _ in range(90):
                        await page.wait_for_timeout(10000)
                        stub, captcha, blocked = await page_state(page)
                        if blocked:
                            print("[!!] во время ожидания пришёл жёсткий блок IP — стоп")
                            hard_stop = True
                            break
                        if not captcha:
                            resumed = True
                            break
                    if hard_stop:
                        break
                    if not resumed:
                        print("[!] капча не решена за 15 минут — стоп, "
                              "даю сайту остыть, резюм подхватит")
                        break
                    # мягкое касание после решения: пауза, чтобы не словить снова
                    print("[captcha] решена — пауза 3 мин, потом продолжаю")
                    await asyncio.sleep(180)

                content = await page.content()
                if "такой страницы больше нет" in content:
                    print(f"[404] {slug}: категория мертва — помечаю как пройденную")
                    done.append(link)
                    json.dump(done, open(DONE_FILE, "w", encoding="utf-8"))
                    continue

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
                key = c["id"] or c["href"]
                if not key:
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
                    "retailer": "pyaterochka",
                    "product_id": key,
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
                    # свежая цена всегда перезаписывает старую
                    if pmin is not None:
                        seen[key]["price_min"], seen[key]["price_max"] = pmin, pmax
                        priced += 1
                    continue
                seen[key] = item
                added += 1

            print(f"[+] {i}/{len(links)} {slug}: карточек {len(cards)}, "
                  f"новых {added}, обновлено цен {priced}, всего {len(seen)}")

            json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            done.append(link)
            json.dump(done, open(DONE_FILE, "w", encoding="utf-8"))

            # человеческая пауза между категориями: 15–35 секунд
            # (после жёсткого блока IP — щадящий темп обязателен)
            await asyncio.sleep(random.uniform(15, 35))

    json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nИТОГ: {len(seen)} товаров -> {OUT}"
          + (" (остановлен по жёсткому блоку IP — данные целы, резюм с последней категории)"
             if hard_stop else ""))
    if seen:
        with_price = sum(1 for v in seen.values() if "price_min" in v)
        print(f"с ценами: {with_price} из {len(seen)}")

# === КОНЕЦ ФАЙЛА: если видишь эту строку, хвост скопировался целиком ===

asyncio.run(main())
