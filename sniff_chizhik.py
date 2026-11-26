import asyncio
import json
from camoufox.async_api import AsyncCamoufox

URL = "https://chizhik.club/catalog/maslo-sousy-spetsii--264C39172/"

captured = []

def guess_json(url: str) -> bool:
    u = url.lower()
    return any(k in u for k in ("api", "product", "catalog", "search", "item"))

async def main():
    async with AsyncCamoufox(headless=True, geoip=False) as browser:
        page = await browser.new_page()

        async def on_response(response):
            url = response.url
            if not guess_json(url):
                return
            try:
                body = await response.text()
            except Exception:
                return
            if not body or len(body) < 200:
                return
            captured.append({"url": url, "body": body})
            print(f"[{len(body):>8} байт] {url[:120]}")

        page.on("response", on_response)

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        # прокрутим страницу — если подгрузка по скроллу, поймаем и её
        for _ in range(5):
            await page.mouse.wheel(0, 2000)
            await page.wait_for_timeout(1500)

        await page.wait_for_timeout(3000)

        for i, c in enumerate(captured):
            with open(f"resp_{i}.json", "w", encoding="utf-8") as f:
                f.write(c["body"])
            print(i, c["url"])

asyncio.run(main())
