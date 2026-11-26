import asyncio
import json
from camoufox.async_api import AsyncCamoufox

SKIP = (".js", ".css", ".png", ".jpg", ".webp", ".svg", ".woff", ".gif", ".ttf")

CARD_SELECTORS = [
    "[data-product-id]",
    "[data-plu]",
    ".product-card", ".product-item", ".product-item-small-card",
    "[class*='product-card']", "[class*='product__card']",
    "[class*='ProductCard']", "[class*='productItem']",
    "xf-product", "[class*='xf-product']",
    "article", "[class*='catalog__item']",
]


async def probe_selectors(page, site: str):
    """Пробует селекторы, печатает счётчики, сохраняет образец карточки."""
    results = await page.evaluate(
        """(sels) => {
             const out = [];
             for (const s of sels) {
               try { out.push([s, document.querySelectorAll(s).length]); }
               catch { out.push([s, -1]); }
             }
             return out;
           }""",
        CARD_SELECTORS,
    )
    print(f"[{site}] счётчики селекторов:")
    for s, n in results:
        if n:
            print(f"    {n:>6}  {s}")
    for s, n in results:
        if n and n > 0:
            html = await page.evaluate(
                "(s) => { const e = document.querySelector(s); return e ? e.outerHTML : null; }",
                s,
            )
            if html:
                with open(f"{site}_card_sample.html", "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"[{site}] образец карточки ({s}, {len(html)} байт) -> {site}_card_sample.html")
            break


async def save_json_responses(page, site: str, seen_urls: set):
    pass  # заглушка — обработчик ниже сам сохраняет


async def probe_dixy():
    tree = json.load(open("dixy_resp_3.json", encoding="utf-8"))
    urls = []
    def walk(node):
        if isinstance(node, dict):
            href = node.get("href")
            if href and href.startswith("/catalog/") and href not in urls:
                urls.append("https://dixy.ru" + href)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(tree)
    # только разделы верхнего уровня (по одному на категорию) — быстрая проба
    top = [u for u in urls if u.count("/") == 3]  # https://dixy.ru/catalog/xxx/
    print(f"Дикси: всего URL {len(urls)}, верхнего уровня {len(top)}")
    for u in top[:5]:
        print("   ", u)

    async with AsyncCamoufox(headless=True, geoip=False) as browser:
        page = await browser.new_page()

        async def on_response(resp):
            u = resp.url
            if any(x in u for x in SKIP) or "dixy.ru" not in u:
                return
            try:
                body = await resp.body()
            except Exception:
                return
            if body and len(body) > 300 and body[:1] in (b"{", b"["):
                print(f"[dixy-capture] {len(body):>8}b {u[:140]}")
                with open(f"dixy_ajax_{abs(hash(u)) % 10000}.json", "wb") as f:
                    f.write(body)

        page.on("response", on_response)

        if top:
            await page.goto(top[0], wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(6000)
            for _ in range(6):
                await page.mouse.wheel(0, 4000)
                await page.wait_for_timeout(1200)
            await probe_selectors(page, "dixy")
            with open("dixy_category_full.html", "w", encoding="utf-8") as f:
                f.write(await page.content())
            print(f"[dixy] полный HTML категории -> dixy_category_full.html")


async def probe_perekrestok():
    async with AsyncCamoufox(headless=True, geoip=False) as browser:
        page = await browser.new_page()

        async def on_response(resp):
            u = resp.url
            if any(x in u for x in SKIP):
                return
            try:
                body = await resp.body()
            except Exception:
                return
            if body and len(body) > 300 and body[:1] in (b"{", b"["):
                print(f"[pr-capture] {len(body):>8}b {u[:140]}")
                with open(f"pr_ajax_{abs(hash(u)) % 10000}.json", "wb") as f:
                    f.write(body)

        page.on("response", on_response)

        await page.goto("https://www.perekrestok.ru/cat/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)
        hrefs = await page.eval_on_selector_all(
            "a[href*='/cat/']",
            "els => [...new Set(els.map(e => e.getAttribute('href')))]",
        )
        cats = [h for h in hrefs if h and "/cat/" in h and h.rstrip("/") != "/cat"]
        print(f"Перекрёсток: найдено ссылок /cat/: {len(cats)}")
        for h in cats[:15]:
            print("   ", h)

        milk = next((h for h in cats if "molo" in h.lower()), cats[0] if cats else None)
        if milk:
            url = "https://www.perekrestok.ru" + milk if milk.startswith("/") else milk
            print(f"[pr] пробная категория: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(8000)
            for _ in range(6):
                await page.mouse.wheel(0, 4000)
                await page.wait_for_timeout(1200)
            await probe_selectors(page, "perekrestok")
            with open("perekrestok_category_full.html", "w", encoding="utf-8") as f:
                f.write(await page.content())
            print(f"[pr] полный HTML категории -> perekrestok_category_full.html")


async def main():
    await probe_dixy()
    await probe_perekrestok()

asyncio.run(main())
