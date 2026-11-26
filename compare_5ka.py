import glob
import json

our = json.load(open("pyaterochka_products.json", encoding="utf-8"))
our_ids = {x.get("product_id") for x in our if x.get("product_id")}
print(f"у нас всего товаров: {len(our)}")

# экспорт может лежать как .json или .json.txt
files = (glob.glob("5ka_35XY_готовая_еда_*.json")
         or glob.glob("5ka_35XY_готовая_еда_*.txt")
         or glob.glob("*готовая_еда*.json*"))
if not files:
    raise SystemExit("не нашёл файл экспорта в папке")
exp = json.load(open(files[0], encoding="utf-8"))
exp_ids = {p["plu"] for p in exp["products"]}
print(f"экспорт: {len(exp_ids)} plu ({files[0]})")

have = exp_ids & our_ids
missing = exp_ids - our_ids
extra = our_ids - exp_ids
print(f"есть у нас из экспорта: {len(have)}")
print(f"нет у нас: {len(missing)}")
print(f"лишних (нет в экспорте): {len(extra)}")

exp_by_plu = {p["plu"]: p for p in exp["products"]}
if missing:
    print("\nпримеры недобранных:")
    for plu in sorted(missing, key=int)[:10]:
        p = exp_by_plu[plu]
        print(f"  {plu} | {p['name'][:50]}")

# сверка цен по пересечению
bad = 0
for plu in sorted(have, key=int):
    ours = next(x for x in our if x.get("product_id") == plu)
    pm = ours.get("price_min")
    if pm is None:
        continue
    m = exp_by_plu[plu]["raw_text"].replace(" ", "")
    if "Цена" in m:
        tail = m.split("Цена")[-1].replace("₽", "")
        try:
            exp_price = float(tail[:-2] + "." + tail[-2:])
            if abs(exp_price - pm) > 0.01:
                bad += 1
                if bad <= 5:
                    print(f"  цена не совпала: {plu} у нас {pm}, в экспорте {exp_price}")
        except (ValueError, IndexError):
            pass
print(f"\nцен сверено: {len(have)}, расхождений: {bad}")
