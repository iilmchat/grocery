import asyncio
from camoufox.async_api import AsyncCamoufox

URL = "https://chizhik.club/catalog/ovoshchi-i-frukty--264C39196/"

captured = []

async def main():
    async with AsyncCamoufox(headless=True, geoip=False) as browser:
        page = await browser.new_page()

        def on_response(response):
            url = response.url
            if "app.chizhik.club" in url and ("/categories/" in url or "/products" in url):
                captured.append(url)
                print(f"[CAP] {url}")

        page.on("response", on_response)

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        # скроллим до упора, чтобы выцепить запросы следующих страниц
        for i in range(20):
            await page.mouse.wheel(0, 5000)
            await page.wait_for_timeout(1500)
            if i % 5 == 4:
                print(f"--- скролл {i + 1}/20 ---")

        print("\n=== Все перехваченные URL ===")
        for u in dict.fromkeys(captured):  # без повторов, с сохранением порядка
            print(u)

asyncio.run(main())
