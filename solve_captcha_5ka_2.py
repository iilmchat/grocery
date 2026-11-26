import asyncio

from camoufox.async_api import AsyncCamoufox


async def main():
    async with AsyncCamoufox(
        headless=False,
        persistent_context=True,
        user_data_dir="profile_5ka",
        i_know_what_im_doing=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://5ka.ru/catalog/gotovaya-eda/",
                        wait_until="domcontentloaded", timeout=60000)
        print()
        print("=" * 60)
        print("Браузер открыт. Реши капчу, дожди до товаров в каталоге,")
        print("потом вернись сюда и нажми Enter.")
        print("=" * 60)
        await asyncio.get_event_loop().run_in_executor(None, input)
        title = await page.title()
        print("Заголовок страницы на выходе:", title)
        print("Профиль сохранён. Теперь запускай pyaterochka_collect_v2.py.")

asyncio.run(main())
