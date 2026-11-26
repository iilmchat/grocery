import asyncio

from camoufox.async_api import AsyncCamoufox

BASE = "https://5ka.ru"

SHOW_ALL_LINKS = """() => {
    const out = [];
    document.querySelectorAll("a[href*='/catalog/']").forEach(a => {
        out.push((a.getAttribute("href") || "") + " | " + (a.textContent.trim().slice(0, 40)));
    });
    return out.slice(0, 60);
}"""


async def main():
    async with AsyncCamoufox(
        headless=True,
        persistent_context=True,
        user_data_dir="profile_5ka",
        i_know_what_im_doing=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        print("[1] открываю /catalog/ ...")
        await page.goto(f"{BASE}/catalog/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        print("    заголовок:", await page.title())
        links = await page.evaluate(SHOW_ALL_LINKS)
        print(f"    catalog-ссылок в DOM: {len(links)}")
        for l in links[:40]:
            print("   ", l)

        print("[2] кликаю по текстовой категории 'Рыба и морепродукты' ...")
        try:
            cat = page.locator("text=Рыба и морепродукты").first
            await cat.click(timeout=10000)
            await page.wait_for_timeout(6000)
            print("    URL после клика:", page.url)
            links2 = await page.evaluate(SHOW_ALL_LINKS)
            print(f"    catalog-ссылок теперь: {len(links2)}")
            new = [l for l in links2 if l not in links]
            print(f"    новых ссылок: {len(new)}")
            for l in new[:40]:
                print("   ", l)
        except Exception as e:
            print(f"    клик не удался: {type(e).__name__}: {str(e)[:120]}")

        print("[3] проверяю сайдбар: раскрываю элементы с чебоксами ...")
        try:
            toggles = page.locator("button, [role='button'], [class*='expand'], [class*='toggle']")
            n = await toggles.count()
            print(f"    кандидат-кнопок: {n}")
            before = set(await page.evaluate(SHOW_ALL_LINKS))
            for i in range(min(n, 15)):
                try:
                    await toggles.nth(i).click(timeout=3000)
                    await page.wait_for_timeout(1200)
                except Exception:
                    continue
            after = await page.evaluate(SHOW_ALL_LINKS)
            new = [l for l in after if l not in before]
            print(f"    ссылок до: {len(before)}, после: {len(after)}, новых: {len(new)}")
            for l in new[:40]:
                print("   ", l)
        except Exception as e:
            print(f"    сайдбар не поддался: {type(e).__name__}: {str(e)[:120]}")

asyncio.run(main())
