import sys

print("Интерпретатор:", sys.executable)

try:
    import asyncio
    from camoufox.async_api import AsyncCamoufox

    async def run():
        async with AsyncCamoufox(headless=True) as browser:
            page = await browser.new_page()
            await page.goto("https://chizhik.club/", timeout=60000,
                            wait_until="domcontentloaded")
            title = await page.title()
            await page.wait_for_timeout(2000)
            print("SMOKE OK, заголовок страницы:", title[:80])

    asyncio.run(run())
except Exception as e:
    print(f"SMOKE FAIL: {type(e).__name__}: {str(e)[:300]}")
    raise
