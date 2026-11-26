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
            if re.search(r"perekrestok\.ru.*(api|gw)", req.url):
                api_calls.append((req.method, req.url, dict(req.headers)))
        page.on("request", on_req)

        print("[1] открываю /cat и собираю ссылки на категории...")
        await page.goto("https://www.perekrestok.ru/cat",
                        wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        links = await page.evaluate("""() => {
            const out = new Set();
            document.querySelectorAll("a[href]").forEach(a => {
                const h = a.getAttribute("href") || "";
                if (h.includes("/cat/")) out.add(h);
            });
            return [...out].slice(0, 40);
        }""")
        print(f"    найдено ссылок с /cat/: {len(links)}")
        for l in links[:25]:
            print("   ", l)

        if not links:
            print("[!] ссылок не найдено — присылай этот вывод, копну разметку")
            return

        full = links[0] if links[0].startswith("http") else "https://www.perekrestok.ru" + links[0]
        print(f"[2] захожу в категорию: {full}")
        await page.goto(full, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(15000)

        # считаем карточки товара в DOM
        counts = await page.evaluate("""() => {
            const c = {};
            ["article", "[class*=product]", "[class*=card]", "[data-sku]", "[class*=item]"].forEach(sel => {
                c[sel] = document.querySelectorAll(sel).length;
            });
            return c;
        }""")
        print("    счётчики селекторов:", counts)

        await page.mouse.wheel(0, 3000); await page.wait_for_timeout(8000)
        await page.mouse.wheel(0, 5000); await page.wait_for_timeout(8000)

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
                                        "x-platform", "authorization",
                                        "x-ecom-client-id", "x-request-id")}
        if interesting:
            print("    заголовки:", interesting)

asyncio.run(main())
