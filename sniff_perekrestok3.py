import asyncio
import re
from camoufox.async_api import AsyncCamoufox

async def main():
    async with AsyncCamoufox(
        headless=True,
        persistent_context=True,
        user_data_dir="profile_pk",
        i_know_what_im_doing=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        print("[1] открываю /catalog и собираю ссылки...")
        await page.goto("https://www.perekrestok.ru/cat",
                        wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        links = await page.evaluate("""() => {
            const out = new Set();
            document.querySelectorAll("a[href*='/catalog/']").forEach(a =>
                out.add(a.getAttribute("href")));
            return [...out].slice(0, 50);
        }""")
        print(f"    ссылок /catalog/: {len(links)}")
        for l in links[:30]:
            print("   ", l)

        tree_count = await page.evaluate(
            "document.querySelectorAll('[data-qa=\"sidebar-categories-tree\"]').length")
        print(f"    дерево категорий в разметке: {tree_count}")

        if links:
            full = links[0] if links[0].startswith("http") else "https://www.perekrestok.ru" + links[0]
            print(f"[2] захожу в категорию: {full}")
            await page.goto(full, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(10000)

            counts = await page.evaluate("""() => {
                const c = {};
                c["data-qa^=product-card"] =
                    document.querySelectorAll('[data-qa^="product-card-"]').length;
                c["schema Product"] =
                    document.querySelectorAll('[itemtype*="schema.org/Product"]').length;
                c["schema Offer"] =
                    document.querySelectorAll('[itemtype*="schema.org/Offer"]').length;
                c["pagination"] =
                    document.querySelectorAll('[data-qa="pagination-wrapper"]').length;
                return c;
            }""")
            print("    счётчики карточек:", counts)

            sample = await page.evaluate("""() => {
                const card = document.querySelector('[data-qa^="product-card-"]');
                return card ? card.outerHTML.slice(0, 1200) : null;
            }""")
            print("    образец карточки:")
            print(sample)

            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(6000)
            after = await page.evaluate(
                "document.querySelectorAll('[data-qa^=\"product-card-\"]').length")
            print(f"    карточек после прокрутки: {after}")

asyncio.run(main())
