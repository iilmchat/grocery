import asyncio
from camoufox.async_api import AsyncCamoufox

async def main():
    async with AsyncCamoufox(
        headless=False,                    # видимое окно — решаем капчу руками
        persistent_context=True,
        user_data_dir="profile_pk",
        i_know_what_im_doing=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.perekrestok.ru/catalog/novinki",
                        wait_until="domcontentloaded", timeout=60000)
        print("Заголовок страницы:", repr(await page.title()))
        print("Если открылась капча — реши её. Затем погуляй по каталогу 1-2 минуты.")
        print("Через 5 минут окно закроется само, профиль сохранит сессию.")
        await asyncio.sleep(300)

asyncio.run(main())
