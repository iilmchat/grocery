import asyncio
import json

from camoufox.async_api import AsyncCamoufox

async def main():
    links = json.load(open("perekrestok_links.json", encoding="utf-8"))
    # «Готовая еда» и пара соседей
    probe = [l for l in links if "gotovaya-eda" in l][:1] or [links[3]]
    url = probe[0] if probe[0].startswith("http") else "https://www.perekrestok.ru" + probe[0]
    print("реальная ссылка из файла:", url)

    async with AsyncCamoufox(headless=False, i_know_what_im_doing=True) as b:
        page = await b.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)
        cnt = "document.querySelectorAll('[data-qa^=\"product-card-\"]').length"
        print("карточек до скролла:", await page.evaluate(cnt))
        print("body scrollHeight:", await page.evaluate("document.body.scrollHeight"),
              "| window.innerHeight:", await page.evaluate("window.innerHeight"))
        conts = await page.evaluate("""() => {
            const out = [];
            [...document.querySelectorAll('*')].forEach(e => {
                const s = getComputedStyle(e);
                if ((s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                    e.scrollHeight > e.clientHeight + 200 && e.clientHeight > 300)
                    out.push({cls: (e.className || '').toString().slice(0, 60),
                              scrollHeight: e.scrollHeight, clientHeight: e.clientHeight});
            });
            return out;
        }""")
        print("скроллируемые контейнеры:", conts)
        await page.mouse.move(960, 500)
        for i in range(5):
            await page.mouse.wheel(0, 1500)
            await page.wait_for_timeout(2000)
            print(f"после wheel #{i + 1}:", await page.evaluate(cnt))
        await asyncio.sleep(15)

asyncio.run(main())
