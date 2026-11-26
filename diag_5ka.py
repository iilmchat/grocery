import asyncio
from camoufox.async_api import AsyncCamoufox

API_CATS = ("https://5d.5ka.ru/catalog/v2/stores/35XY/categories"
            "?mode=delivery&include_subcategories=1&include_restrict=true")

async def main():
    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()
        print("[1] обычная страница 5ka.ru...")
        await page.goto("https://5ka.ru/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        print("    заголовок:", await page.title())

        print("[2] прямая навигация на API категорий...")
        try:
            resp = await page.goto(API_CATS, wait_until="domcontentloaded", timeout=60000)
            body = (await page.content())[:300]
            print(f"    HTTP-статус: {resp.status if resp else '?'}")
            print(f"    тело: {body}")
        except Exception as e:
            print(f"    навигация упала: {type(e).__name__}: {str(e)[:150]}")

asyncio.run(main())
