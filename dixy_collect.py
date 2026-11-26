import asyncio
import json
import os
import re
from datetime import datetime, timezone

from camoufox.async_api import AsyncCamoufox

OUT = "dixy_products.json"
LINKS_FILE = "dixy_links.json"
DONE_FILE = "dixy_done.json"
BASE = "https://dixy.ru"

PARSE_CARDS = """() => {
    const cards = [];
    document.querySelectorAll("article").forEach(card => {
        const a = card.querySelector("a[href*='/product'], a[href*='/catalog/']");
        const img = card.querySelector("img");
        const nameEl = card.querySelector("h2, h3, img[alt]");
        const priceEls = [...card.querySelectorAll("[class*=price]")];
        const prices = priceEls.map(p => p.textContent.trim()).filter(t => t);
        cards.push({
            href: a ? a.getAttribute("href") : null,
            name: nameEl ? (nameEl.getAttribute("alt") || nameEl.textContent.trim()) : null,
            image: img ? img.src : null,
            prices: prices,
        });
    });
    return cards;
}"""


def parse_price(texts):
    vals = []
    for t in texts:
        for n in re.findall(r"\d[\d\s\u00a0]*[.,]\d{2}|\d[\d\s\u00a0]{2,}", t):
            v = re.sub(r"[^\d.,]", "", n).replace("\u00a0", "").replace(" ", "").replace(",", ".")
            try:
                vals.append(float(v))
            except ValueError:
                pass
    return (min(vals), max(vals)) if vals else (None, None)


async def load_all(page):
    """Догружает ленту: кнопка 'ещё' или скролл-насыщение."""
    for _ in range(60):
        before = await page.evaluate("document.querySelectorAll('article').length")
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
        after = await page.evaluate("document.querySelectorAll('article').length")
        if not clicked and after == before:
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(2500)
            if await page.evaluate("document.querySelectorAll('article').length") == before:
                break
    return await page.evaluate(PARSE_CARDS)


async def main():
    seen: dict = {}

    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()

        if os.path.exists(LINKS_FILE):
            links = json.load(open(LINKS_FILE, encoding="utf-8"))
            print(f"[cache] ссылок из файла: {len(links)}")
        else:
            await page.goto(f"{BASE}/catalog/", wait_until="domcontentloaded", timeout=60000)
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
            slug = link.replace("/catalog/", "").strip("/").replace("/", "_") or "root"

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(6000)
                cards = await load_all(page)
            except Exception as e:
                print(f"[!] {slug}: {type(e).__name__}: {str(e)[:100]} — пропускаю")
                continue

            added = 0
            for c in cards:
                pid = c["href"]
                if not pid:
                    continue
                if pid in seen:
                    continue
                pmin, pmax = parse_price(c["prices"])
                seen[pid] = {
                    "retailer": "dixy",
                    "url": BASE + pid if not pid.startswith("http") else pid,
                    "name": (c["name"] or "").strip(),
                    "image_url": c["image"],
                    "category_slug": slug,
                    "price_min": pmin,
                    "price_max": pmax,
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                }
                added += 1

            print(f"[+] {i}/{len(links)} {slug}: карточек {len(cards)}, новых {added}, всего {len(seen)}")

            done.append(link)
            json.dump(done, open(DONE_FILE, "w", encoding="utf-8"))
            if i % 5 == 0:
                json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
                print(f"    [checkpoint] {len(seen)} товаров -> {OUT}")

            await asyncio.sleep(3)

    json.dump(list(seen.values()), open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nИТОГ: {len(seen)} товаров -> {OUT}")
    if seen:
        print("образец записи:", json.dumps(list(seen.values())[0], ensure_ascii=False)[:500])

asyncio.run(main())
