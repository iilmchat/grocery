import json
from collections import Counter


def check(path):
    items = json.load(open(path, encoding="utf-8"))
    ids = [i.get("product_id") for i in items]
    print(f"\n=== {path}")
    print("  records:", len(items), "unique ids:", len(set(ids)))
    print("  retailers:", Counter(i.get("retailer") for i in items))
    for f in ("name", "url", "image_url", "price", "scraped_at"):
        miss = sum(1 for i in items if i.get(f) is None)
        print(f"  missing {f}: {miss}")
    with_old = sum(1 for i in items if i.get("old_price") is not None)
    print("  with old_price:", with_old)
    prices = [i["price"] for i in items if i.get("price") is not None]
    print("  price range:", min(prices), "-", max(prices))
    print("  categories:", Counter(i.get("category_slug") for i in items).most_common(8))


check("globus_products.json")
check("auchan_products.json")

# сравнение с уже собранными ранее ритейлерами
for p in ("chizhik_products.json", "dixy_products.json",
          "pyaterochka_products.json", "perekrestok_products.json"):
    try:
        d = json.load(open(p, encoding="utf-8"))
        print(f"{p}: {len(d)}")
    except Exception as e:
        print(p, type(e).__name__)
