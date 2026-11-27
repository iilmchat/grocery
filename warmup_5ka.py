import asyncio
from camoufox.async_api import AsyncCamoufox

URLS = ["https://5ka.ru/", "https://5ka.ru/catalog/"]


async def safe_goto(page, url, tries=3):
    for attempt in range(1, tries + 1):
        try:
            await page.goto(url, wait_until="commit", timeout=60000)
            await page.wait_for_timeout(8000)
            print(f"[ok] {url} -> финальный URL: {page.url[:80]}")
            return True
        except Exception as e:
            print(f"[retry {attempt}] {url}: {type(e).__name__}: {str(e)[:80]}")
            await asyncio.sleep(5 * attempt)
    return False


async def main():
    async with AsyncCamoufox(
        headless=False,
        persistent_context=True,
        user_data_dir="profile_5ka",
        i_know_what_im_doing=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        opened = False
        for url in URLS:
            if await safe_goto(page, url):
                opened = True
                break

        if not opened:
            print("[!] ни одна страница не открылась — прогон отменяю")
            return

        await page.wait_for_timeout(5000)
        print("Заголовок страницы:", repr(await page.title()))
        print("Если заглушка 'Не смогли загрузить категории' — жми 'Повторить'")
        print("с паузой ~30 сек, 2-3 раза. Если каталог открылся — погуляй")
        print("по 2-3 категориям руками. Через 5 минут окно закроется само.")
        await asyncio.sleep(300)

asyncio.run(main())
