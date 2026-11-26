import asyncio
import json
from camoufox.async_api import AsyncCamoufox

TARGETS = {
    "perekrestok": "https://www.perekrestok.ru/cat/molochnye-produkty",
    "pyaterochka": "https://5ka.ru/special_offers/",
    "dixy":        "https://dixy.ru/catalog/",
}


async def recon(site: str, url: str):
    captured = []

    async with AsyncCamoufox(headless=True, geoip=False) as browser:
        page = await browser.new_page()

        def on_response(resp):
            u = resp.url
            # отсекаем статику и картинки — интересен только API
            if any(x in u for x in (".js", ".css", ".png", ".jpg", ".webp", ".svg", ".woff")):
                return
            captured.append(resp)

        page.on("response", on_response)

        print(f"\n=== {site}: {url} ===")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[goto error] {type(e).__name__}: {str(e)[:200]}")
            return
        await page.wait_for_timeout(8000)

        for i in range(6):
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(1500)

        print(f"Перехвачено ответов: {len(captured)}")
        for i, resp in enumerate(captured):
            try:
                body = await resp.body()
                ct = resp.headers.get("content-type", "")
                is_json = "json" in ct
                print(f"[{i}] {'JSON' if is_json else 'html'} {len(body):>8}b {resp.url[:150]}")
                if is_json and len(body) > 1000:
                    with open(f"{site}_{i}.json", "wb") as f:
                        f.write(body)
            except Exception:
                pass

        # заглушка/челлендж защиты — сохраним для анализа
        html = await page.content()
        if any(k in html for k in ("Доступ ограничен", "доступ ограничен", "captcha", "Qrator", " ddos")):
            print(f"[!] {site}: похоже на страницу защиты — сохраняю {site}_challenge.html")
            with open(f"{site}_challenge.html", "w", encoding="utf-8") as f:
                f.write(html)
        print(f"{site}: длина итогового HTML {len(html)}")


async def main():
    for site, url in TARGETS.items():
        await recon(site, url)

asyncio.run(main())
