import json
import os
from datetime import datetime, timezone

IN = "pyaterochka_products.json"
OUT_DIR = "exports"
SAP_CODE = "35XY"          # sap-код магазина из эталонного экспорта
SOURCE = "5ka.ru-collector-persistent-context"

# русские названия категорий, где знаем; остальное — слаг как есть
CATEGORY_RU = {
    "gotovaya-eda": "Готовая еда",
}

if not os.path.exists(OUT_DIR):
    os.makedirs(OUT_DIR)

items = json.load(open(IN, encoding="utf-8"))

# группируем по категориям
by_cat: dict = {}
for it in items:
    by_cat.setdefault(it.get("category_slug") or "unknown", []).append(it)

def make_raw_text(it):
    """Синтетический raw_text: у нас нет DOM-снапшота текста карточки."""
    parts = []
    if it.get("badge"):
        parts.append(it["badge"])
    parts.append(it.get("name") or "")
    if it.get("price_min") is not None:
        rub = int(it["price_min"])
        pen = round((it["price_min"] - rub) * 100)
        parts.append(f"Цена {rub} {pen:02d} ₽")
    return " ".join(parts)

total_out = 0
for cat, products in sorted(by_cat.items()):
    cat_ru = CATEGORY_RU.get(cat, cat)
    now = datetime.now(timezone.utc)
    captured = now.strftime("%Y-%m-%dT%H-%M-%S-") + f"{now.microsecond // 1000:03d}Z"

    payload = {
        "schema_version": 1,
        "source": SOURCE,
        "expected_sap_code_from_previous_test": SAP_CODE,
        "captured_at": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "source_url": f"https://5ka.ru/catalog/",
        "category": cat_ru,
        "store": {
            "sap_code": SAP_CODE,
            "name": None,
        },
        "collection_mode": "collector-scroll-full-category",
        "pagination": {
            "current_page_number": None,
            "visible_page_numbers": [],
            "max_page_linked": None,
            "meaning": "Сборщик скроллит категорию до конца; номер страницы не фиксировался.",
        },
        "note": ("Товары собраны автоматическим сборщиком из DOM карточек категории "
                 "(все страницы до конца списка). Цены взяты из meta[itemprop=price] "
                 "(рубли с копейками); price_min — акционная цена, price_max — обычная. "
                 "raw_text синтезирован из полей карточки, а не скопирован из DOM."),
        "products": [],
    }

    for it in products:
        payload["products"].append({
            "plu": str(it.get("product_id") or ""),
            "name": it.get("name") or "",
            "product_url": it.get("url") or "",
            "image_url": it.get("image_url") or None,
            "image_alt": it.get("name") or "",
            "raw_text": make_raw_text(it),
        })

    fname = f"5ka_{SAP_CODE}_{cat_ru.replace(' ', '_')}_{captured}.json.txt"
    path = os.path.join(OUT_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    total_out += len(products)
    print(f"[export] {cat_ru}: {len(products)} товаров -> {fname}")

print(f"\nИТОГ: {total_out} товаров в {len(by_cat)} файлах -> {OUT_DIR}/")
