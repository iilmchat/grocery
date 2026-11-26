import json
import re

html = open("chizhik_category.html", encoding="utf-8").read()
m = re.search(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    html, re.S,
)
if not m:
    raise SystemExit("__NEXT_DATA__ не найден — проверьте, что файл сохранён полностью")

d = json.loads(m.group(1))
json.dump(d, open("next_data.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# рекурсивный поиск узлов с товарами
def find(node, out, depth=0):
    if depth > 30:
        return
    if isinstance(node, dict):
        if "plu" in node and "name" in node:
            out.append(node)
        for v in node.values():
            find(v, out, depth + 1)
    elif isinstance(node, list):
        for v in node:
            find(v, out, depth + 1)

items = []
find(d, items)
print("Ключи pageProps:", list(d.get("props", {}).get("pageProps", {}).keys()))
print("buildId:", d.get("buildId"))
print("Товаров найдено:", len(items))
if items:
    print("--- ПЕРВЫЙ ТОВАР ---")
    print(json.dumps(items[0], ensure_ascii=False, indent=2)[:3000])
