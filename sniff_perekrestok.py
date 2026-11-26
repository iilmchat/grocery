import asyncio
import re
from camoufox.async_api import AsyncCamoufox

async def main():
    api_calls = []
    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()

        def on_req(req):
            u = req.url
            if "perekrestok.ru" in u and re.search(r"/api/|ecom\.gw", u):
                api_calls.append((req.method, u, dict(req.headers)))

        page.on("request", on_req)

        print("[1] открываю каталог...")
        await page.goto("https://www.perekrestok.ru/cat",
                        wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        print("[2] кликаю первую категорию...")
        try:
            await page.click('a[href*="/cat/c"]', timeout=10000)
        except Exception as e:
            print(f"    клик не удался: {type(e).__name__}, открою подкатегорию вручную")
        await page.wait_for_timeout(15000)

        # ещё раз прокрутить вниз, чтобы сработали запросы пагинации
        await page.mouse.wheel(0, 3000)
        await page.wait_for_timeout(10000)

    print(f"\nПерехвачено API-запросов: {len(api_calls)}")
    seen = set()
    for method, u, headers in api_calls:
        key = re.sub(r"/\d+|page=\d+|limit=\d+", "/{N}", u.split("?")[0])
        if key in seen:
            continue
        seen.add(key)
        print(f"\n{method} {u[:220]}")
        interesting = {k: v for k, v in headers.items()
                       if k.lower() in ("x-consumer-id", "x-app-version",
                                        "x-platform", "x-xsrf-token",
                                        "authorization", "x-ecom-client-id")}
        if interesting:
            print("    заголовки:", interesting)

asyncio.run(main())
