import asyncio
import json

from camoufox.async_api import AsyncCamoufox

async def main():
    items = json.load(open("dixy_products.json", encoding="utf-8"))[:5]
    out = []
    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()
        for it in items:
            await page.goto(it["url"], wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)
            data = await page.evaluate("""() => ({
                url: location.href,
                title: document.querySelector("h1")?.textContent.trim() || null,
                body_sample: document.body.innerText.slice(0, 3000),
                has_jsonld: !!document.querySelector('script[type="application/ld+json"]'),
                jsonld: [...document.querySelectorAll('script[type="application/ld+json"]')]
                    .map(s => s.textContent.slice(0, 2000)),
            })""")
            out.append(data)
            print(f"[probe] {it['name'][:40]}: h1={data['title']!r}, ld+json x{len(data['jsonld'])}")
    json.dump(out, open("dixy_probe.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("сохранено: dixy_probe.json — пришли его мне")

asyncio.run(main())
