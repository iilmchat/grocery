import asyncio
from camoufox.async_api import AsyncCamoufox

API_CATS = ("https://5d.5ka.ru/catalog/v2/stores/35XY/categories"
            "?mode=delivery&include_subcategories=1&include_restrict=true")

async def main():
    async with AsyncCamoufox(
        headless=False,
        persistent_context=True,
        user_data_dir="profile_5ka",
        i_know_what_im_doing=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://5ka.ru/", wait_until="domcontentloaded", timeout=60000)
        input(">>> В окне браузера реши капчу, дожди загрузки каталога и нажми Enter здесь... ")
        print("[2] проверяю API прямой навигацией...")
        resp = await page.goto(API_CATS, wait_until="domcontentloaded", timeout=60000)
        body = await page.content()
        print(f"HTTP-статус: {resp.status if resp else '?'}")
        print("начало тела:", body[:200].replace("\n", " "))

asyncio.run(main())
