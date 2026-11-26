import asyncio
import json
import os
import re
from urllib.parse import urlparse

from camoufox.async_api import AsyncCamoufox

COUNTERS_JS = """() => {
    const c = {};
    const sels = ["article", "[class*=product]", "[class*=card]",
                  "[data-sku]", "[class*=item]", "[class*=catalog]",
                  "a[href*='/catalog/']", "[class*=price]"];
    sels.forEach(sel => c[sel] = document.querySelectorAll(sel).length);
    return c;
}"""

LINKS_JS = """() => {
    const out = new Set();
    document.querySelectorAll("a[href]").forEach(a => {
        const h = a.getAttribute("href") || "";
        if (h.includes("/catalog/") || h.includes("/category/")) out.add(h);
    });
    return [...out].slice(0, 50);
}"""


async def main():
    saved = 0
    api_urls = []

    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()

        async def on_resp(resp):
            nonlocal saved
            u = resp.url
            ct = (resp.headers or {}).get("content-type", "")
            if ("dixy.ru" in u or "dnsdict" in u or "dixy" in u) \
                    and ("json" in ct or u.endswith(".json")):
                try:
                    body = await resp.text()
                    if body and body.strip().startswith(("{", "[")):
                        fname = f"dixy_resp_{saved}.json"
                        with open(fname, "w", encoding="utf-8") as f:
                            f.write(body)
                        api_urls.append((resp.request.method, u, fname))
                        saved += 1
                except Exception:
                    pass

        page.on("response", on_resp)

        print("[1] открываю каталог Дикси...")
        await page.goto("https://dixy.ru/catalog/",
                        wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        print("    заголовок:", await page.title())
        counts = await page.evaluate(COUNTERS_JS)
        print("    счётчики селекторов:", counts)

        links = await page.evaluate(LINKS_JS)
        print(f"    ссылок на каталог/категории: {len(links)}")
        for l in links[:25]:
            print("   ", l)

        print("[2] захожу в первую категорию (если есть)...")
        if links:
            url = links[0] if links[0].startswith("http") else "https://dixy.ru" + links[0]
            print("    ->", url)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(8000)
                counts = await page.evaluate(COUNTERS_JS)
                print("    счётчики на категории:", counts)

                # прокрутка — чтобы сработали AJAX-подгрузки
                for _ in range(3):
                    await page.mouse.wheel(0, 4000)
                    await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"    переход упал: {type(e).__name__}: {str(e)[:120]}")

        await page.wait_for_timeout(5000)

    print(f"\nСохранено JSON-ответов: {saved}")
    for method, u, fname in api_urls:
        p = urlparse(u)
        key = re.sub(r"/\d+|page=\d+|limit=\d+|offset=\d+", "/{N}", p.path)
        print(f"\n{method} https://{p.netloc}{key}?{p.query[:120]} -> {fname}")

asyncio.run(main())
