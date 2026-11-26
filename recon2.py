import asyncio
import json
from camoufox.async_api import AsyncCamoufox

TARGETS = {
    "dixy": [
        "https://dixy.ru/catalog/bakaleya/",
    ],
    "perekrestok": ["https://www.perekrestok.ru/cat/molochnye-produkty"],
    "pyaterochka": ["https://5ka.ru/catalog/"],
}

SKIP = (".js", ".css", ".png", ".jpg", ".webp", ".svg", ".woff", ".gif", ".ttf")

saved_counter = {"n": 0}


async def recon(site: str, urls: list[str]):
    async with AsyncCamoufox(headless=True, geoip=False) as browser:
        page = await browser.new_page()

        async def on_response(resp):
            u = resp.url
            if any(x in u for x in SKIP):
                return
            try:
                body = await resp.body()
            except Exception:
                return
            if not body or len(body) < 500:
                return
            ct = resp.headers.get("content-type", "")
            looks_json = body[:1] in (b"{", b"[") or "json" in ct
            if looks_json:
                saved_counter["n"] += 1
                name = f"{site}_resp_{saved_counter['n']}.json"
                with open(name, "wb") as f:
                    f.write(body)
                print(f"[{site}] JSON {len(body):>8}b -> {name}  {u[:130]}")

        page.on("response", on_response)

        for i, url in enumerate(urls):
            print(f"\n=== {site} [{i}]: {url} ===")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"[goto error] {type(e).__name__}: {str(e)[:200]}")
                continue
            await page.wait_for_timeout(7000)
            for _ in range(5):
                await page.mouse.wheel(0, 4000)
                await page.wait_for_timeout(1500)

            html = await page.content()
            hname = f"{site}_page_{i}.html"
            with open(hname, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"[{site}] HTML {len(html):>8}b -> {hname}")
            print(f"[{site}] __NEXT_DATA__: {'__NEXT_DATA__' in html}")

            await page.wait_for_timeout(2000)


async def main():
    for site, urls in TARGETS.items():
        await recon(site, urls)

asyncio.run(main())
