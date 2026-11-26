import asyncio
import json

from camoufox.async_api import AsyncCamoufox

URL = "https://5ka.ru/catalog/gotovaya-eda--251C12884/"

PROBE = """() => {
    const cards = document.querySelectorAll('[data-qa^="product-card-"]').length;
    const priceEls = [...document.querySelectorAll('[itemprop="price"]')].slice(0, 3)
        .map(el => ({
            content: el.getAttribute("content"),
            rubles: el.parentElement.querySelector('[data-qa="price-tag-rubles"]')
                ? el.parentElement.querySelector('[data-qa="price-tag-rubles"]').textContent.trim()
                : null,
            pennies: el.parentElement.querySelector('[data-qa="price-tag-pennies"]')
                ? el.parentElement.querySelector('[data-qa="price-tag-pennies"]').textContent.trim()
                : null,
        }));
    const card = document.querySelector('[data-qa^="product-card-"]');
    return {
        url: location.href,
        title: document.title,
        cards: cards,
        prices_on_page: document.querySelectorAll('[itemprop="price"]').length,
        price_els: priceEls,
        sample_card: card ? card.outerHTML.slice(0, 3000) : null,
        body_head: cards ? null
            : (document.body ? document.body.innerText.slice(0, 500) : null),
    };
}"""


async def main():
    async with AsyncCamoufox(
        headless=True,
        persistent_context=True,
        user_data_dir="profile_5ka",   # родной профиль — без капчи
        i_know_what_im_doing=True,
    ) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)
        info = await page.evaluate(PROBE)
        print(json.dumps(info, ensure_ascii=False, indent=2))

asyncio.run(main())
