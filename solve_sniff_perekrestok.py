import asyncio
import re
from camoufox.async_api import AsyncCamoufox

async def main():
    api_calls = []
    async with AsyncCamoufox(
        headless=False,
        persistent_context=True,
        user_data_dir="profile_pk",
        i_know_what_im_doing=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        def on_req(req):
            u = req.url
            if re.search(r"perekrestok\.ru.*(api|gw)", u):
                api_calls.append((req.method, u, dict(req.headers)))
        page.on("request", on_req)

        print("[1] открываю каталог...")
        await page.goto("https://www.perekrestok.ru/cat",
                        wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)

        title = await page.title()
        content = await page.content()
        has_captcha = ("captcha" in content.lower()
                       or "подтвердите" in content.lower()
                       or "robot" in content.lower())
        print(f"    заголовок: {title!r}, похоже на капчу: {has_captcha}")

        if has_captcha:
            input(">>> Реши капчу в окне браузера, дождись загрузки каталога, затем Enter здесь... ")

        print("[2] захожу в первую категорию...")
        try:
            link = await page.wait_for_selector('a[href*="/cat/c"]', timeout=15000)
            await link.click()
            print("    клик по категории прошёл")
        except Exception as e:
            print(f"    клик не удался: {type(e).__name__} — попробую прямую ссылку")
            await page.goto("https://www.perekrestok.ru/cat/c/1565",
                            wait_until="domcontentloaded", timeout=60000)

        await page.wait_for_timeout(15000)
        await page.mouse.wheel(0, 3000)
        await page.wait_for_timeout(10000)
        await page.mouse.wheel(0, 5000)
        await page.wait_for_timeout(10000)

    print(f"\nПерехвачено API-запросов: {len(api_calls)}")
    seen = set()
    for method, u, headers in api_calls:
        key = re.sub(r"/\d+|page=\d+|limit=\d+|offset=\d+", "/{N}", u.split("?")[0])
        if key in seen:
            continue
        seen.add(key)
        print(f"\n{method} {u[:250]}")
        interesting = {k: v for k, v in headers.items()
                       if k.lower() in ("x-consumer-id", "x-app-version",
                                        "x-platform", "x-xsrf-token",
                                        "authorization", "x-ecom-client-id",
                                        "x-request-id")}
        if interesting:
            print("    заголовки:", interesting)

asyncio.run(main())
