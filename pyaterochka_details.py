import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone

from camoufox.async_api import AsyncCamoufox

PRODUCTS_FILE = "pyaterochka_products.json"
DONE_FILE = "pyaterochka_details_done.json"
DETAILS_JSON = "pyaterochka_details.json"
OUT_DIR = "exports_details"
SAP_CODE = "35XY"
BASE = "https://5ka.ru"

DETAILS_TEXT_LIMIT = 20000
PAUSE_SEC = 6            # пауза между товарами
BATCH = 25               # раз в сколько товаров чекпоинт консолидированного файла

# --- парсеры текста страницы (устойчивы к переверстке) ---

def parse_nutrition(text):
    """'Белки 0.0 Жиры 3.0 Углеводы 62.0 Ккал' -> словарь без Ккал, как в эталоне."""
    out = {}
    for key in ("Белки", "Жиры", "Углеводы"):
        m = re.search(rf"{key}\s*([\d.,]+)", text)
        if m:
            out[key] = m.group(1).replace(",", ".")
    return out or None


def parse_composition(text):
    """От 'Состав' до конца текста — как в эталоне, с хвостом атрибутов."""
    m = re.search(r"Состав\s+(.+)", text, re.S)
    return m.group(1).strip() if m else None


def parse_description(text):
    """В эталоне description пустой — держим None, текст живёт в details_text."""
    return None


def parse_attributes(text):
    out = {}
    m = re.search(r"Вес\s+([\d.,]+\s*(?:кг|г|л|мл|шт))", text)
    if m:
        out["Вес"] = m.group(1).strip()
    m = re.search(r"Срок хранения\s+(.+?)(?:Условия хранения|Бренд|Показать|$)", text)
    if m:
        out["Срок хранения"] = m.group(1).strip()
    m = re.search(r"Условия хранения\s+(.+?)(?:Бренд|Показать|Состав\b|$)", text)
    if m:
        out["Условия хранения"] = m.group(1).strip()
    m = re.search(r"Бренд\s+(.+?)(?:Показать|Состав\b|Описание|$)", text)
    if m:
        out["Бренд"] = m.group(1).strip()
    for key in ("Белки", "Жиры", "Углеводы"):
        m = re.search(rf"{key}\s*([\d.,]+)\s*г", text)
        if m:
            out[key] = f"{m.group(1).replace(',', '.')} г"
    return out or None


def parse_rating(text):
    m = re.search(r"(\d[.,]\d{1,2})\s*\x28(\d[\d\s\xA0]*)\s*оцен", text)
    if m:
        cnt = m.group(2).replace(" ", "").replace("\x00A0", " ")
        return {"value": m.group(1).replace(",", "."), "count": int(cnt.strip())}
    return None
# === КОНЕЦ parse_rating: если видишь эту строку, блок скопировался целиком ===
def to_800(url):
    """320x320 -> 800x800 (на странице деталей отдаётся крупная картинка)."""
    if url and "320x320" in url:
        return url.replace("320x320", "800x800")
    return url


EXTRACT = """() => {
    const text = document.body ? document.body.innerText.slice(0, 20000) : "";
    const seen = new Set();
    const gallery = [];
    document.querySelectorAll("img").forEach(img => {
        const src = img.src || "";
        if (!src.includes("x5static.net")) return;
        if (!/\\d+x\\d+/.test(src)) return;
        const key = src.split("?")[0];
        if (seen.has(key)) return;
        seen.add(key);
        gallery.push({
            url: src,
            alt: img.getAttribute("alt") || null,
        });
    });
    const h1 = document.querySelector("h1");
    return {
        title: h1 ? h1.textContent.trim() : null,
        gallery: gallery.slice(0, 12),
        text: text,
        url: location.href,
    };
}"""


def build_product_page(plu, name, url, raw):
    gallery = []
    for i, g in enumerate(raw.get("gallery") or [], 1):
        gallery.append({
            "url": g["url"],
            "alt": g["alt"] or name,
            "position": i,
        })
    text = raw.get("text") or ""
    return {
        "plu": str(plu),
        "name": name,
        "product_url": url,
        "image_url": to_800(gallery[0]["url"] if gallery else None),
        "image_alt": name,
        "image_gallery": gallery,
        "composition": parse_composition(text),
        "description": parse_description(text),
        "nutrition": parse_nutrition(text),
        "attributes": parse_attributes(text),
        "rating": parse_rating(text),
        "details_text": text[:DETAILS_TEXT_LIMIT],
    }


async def main():
    probe = len(sys.argv) > 1 and sys.argv[1] == "--probe"
    pause = 0 if probe else PAUSE_SEC

    items = json.load(open(PRODUCTS_FILE, encoding="utf-8"))
    print(f"[cache] товаров в базе: {len(items)}")

    done = (json.load(open(DONE_FILE, encoding="utf-8"))
            if os.path.exists(DONE_FILE) else [])
    done_set = set(done)

    details: dict = {}
    if os.path.exists(DETAILS_JSON):
        for it in json.load(open(DETAILS_JSON, encoding="utf-8")):
            details[it["plu"]] = it
        print(f"[cache] деталей из прошлого прогона: {len(details)}")

    if probe:
        plu = sys.argv[2] if len(sys.argv) > 2 else "4359405"
        items = [it for it in items if str(it.get("product_id")) == str(plu)]
        if not items:
            print(f"[!] товар {plu} не найден в {PRODUCTS_FILE}")
            return

    os.makedirs(OUT_DIR, exist_ok=True)

    async with AsyncCamoufox(
        headless=True,
        persistent_context=True,
        user_data_dir="profile_5ka_det",
        i_know_what_im_doing=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        todo = [it for it in items if str(it.get("product_id")) not in done_set]
        print(f"[plan] к сбору деталей: {len(todo)}")

        for n, it in enumerate(todo, 1):
            plu = str(it.get("product_id") or "")
            url = it.get("url") or f"{BASE}/product/--{plu}/"
            slug = (it.get("name") or "")[:40]
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(5000)

                content = await page.content()
                if "captcha" in content.lower():
                    print(f"[!] {plu}: капча — останавливаю прогон")
                    break
                if "такой страницы больше нет" in content:
                    print(f"[404] {plu} {slug}: карточка мертва")
                    done.append(plu)
                    done_set.add(plu)
                    continue

                raw = await page.evaluate(EXTRACT)
                if not raw.get("text"):
                    print(f"[!] {plu}: пустая страница — пропускаю")
                    continue

                prod = build_product_page(
                    plu, it.get("name") or raw.get("title") or "", url, raw)
                details[plu] = prod

                now = datetime.now(timezone.utc)
                captured = (now.strftime("%Y-%m-%dT%H-%M-%S-")
                            + f"{now.microsecond // 1000:03d}Z")
                payload = {
                    "schema_version": 1,
                    "source": "5ka.ru-collector-product-details",
                    "captured_at": now.isoformat(timespec="milliseconds")
                        .replace("+00:00", "Z"),
                    "source_url": url,
                    "store": {"sap_code": SAP_CODE, "name": None},
                    "collection_mode": "collector-current-product-dom-only",
                    "note": ("Товар собран автоматическим сборщиком со страницы деталей. "
                             "API-запросы к 5ka.ru не выполнялись. "
                             "attributes и nutrition спарсены из текста страницы."),
                    "product": prod,
                }
                fname = f"5ka_detail_{SAP_CODE}_{plu}_{captured}.json.txt"
                with open(os.path.join(OUT_DIR, fname), "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)

                done.append(plu)
                done_set.add(plu)

                print(f"[+] {n}/{len(todo)} {plu} {slug}: "
                      f"галерея {len(prod['image_gallery'])}, "
                      f"состав {'да' if prod['composition'] else 'нет'}, "
                      f"КБЖУ {'да' if prod['nutrition'] else 'нет'}")

                if n % BATCH == 0:
                    json.dump(list(details.values()),
                              open(DETAILS_JSON, "w", encoding="utf-8"),
                              ensure_ascii=False, indent=2)
                    json.dump(done, open(DONE_FILE, "w", encoding="utf-8"))

                await asyncio.sleep(pause)
            except Exception as e:
                print(f"[!] {plu}: {type(e).__name__}: {str(e)[:100]} — пропускаю")
                await asyncio.sleep(30)

    json.dump(list(details.values()), open(DETAILS_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(done, open(DONE_FILE, "w", encoding="utf-8"))
    print(f"\nИТОГ: {len(details)} карточек деталей -> {DETAILS_JSON}")
    if details:
        sample = list(details.values())[0]
        print("образец:", json.dumps(sample, ensure_ascii=False)[:600])

# === КОНЕЦ ФАЙЛА: если видишь эту строку, хвост скопировался целиком ===

asyncio.run(main())




