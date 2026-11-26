import json
import sys

ours_path = sys.argv[1]
ref_path = sys.argv[2]

ours = json.load(open(ours_path, encoding="utf-8"))["product"]
ref = json.load(open(ref_path, encoding="utf-8"))["product"]

FIELDS = ["plu", "name", "product_url", "image_url",
          "composition", "description", "nutrition", "attributes"]

for f in FIELDS:
    a, b = ours.get(f), ref.get(f)
    same = a == b
    print(f"{'OK  ' if same else 'DIFF'} {f}")
    if not same:
        if isinstance(a, dict):
            print(f"    наша:    {json.dumps(a, ensure_ascii=False)[:200]}")
            print(f"    эталон:  {json.dumps(b, ensure_ascii=False)[:200]}")
        else:
            sa = (a or "")[:200].replace("\n", " ")
            sb = (b or "")[:200].replace("\n", " ")
            print(f"    наша:    {sa}")
            print(f"    эталон:  {sb}")

# галерею сравниваем по количеству и набору размеров
ga = {g["url"].split("?")[0] for g in ours.get("image_gallery", [])}
gb = {g["url"].split("?")[0] for g in ref.get("image_gallery", [])}
print(f"{'OK  ' if ga == gb else 'DIFF'} gallery (у нас {len(ga)}, в эталоне {len(gb)})")

# rating в эталоне нет — только показываем, что парсер взял
print(f"INFO rating: {ours.get('rating')}")
