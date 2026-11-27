"""Сбор товаров сети «Глобус» через публичный BFF-API сайта.

За основу взят chizhik_collect.py: те же принципы (API + кеш + чекпоинты),
но без браузера — страница каталога нужна только один раз, чтобы достать
browserAPIHost и uuid из __NEXT_DATA__.

API: POST {browserAPIHost}/api-web/v1/catalog:product-list
     {"url", "category_id", "sort", "include", "pagination", ...}
Ответ: data.products.{items[], pagination{page,total,total_page}}.
Цены приходят в копейках.
"""

import asyncio
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.client import HTTPException

CATALOG_URL = "https://online.globus.ru/catalog/"
BASE = "https://online.globus.ru"
OUT = "globus_products.json"
LINKS_FILE = "globus_links.json"
DONE_FILE = "globus_done.json"
RAW_DIR = "globus_raw"

PER_PAGE = 1000          # API отдаёт до 1000 позиций за запрос
MAX_PAGES = 100          # страховка от бесконечной пагинации
RETRIES = 4
TIMEOUT = 60
UA = "Mozilla/5.0 (Windows NT 10.0; Win32; x64) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"

NEXT_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def money(v):
    """копейки -> рубли"""
    if v is None:
        return None
    try:
        v = float(v) / 100.0
    except (TypeError, ValueError):
        return None
    return round(v, 2) if 0 < v < 1_000_000 else None


def clean_name(p):
    parts = [(p.get("name_optional") or "").strip().rstrip(","),
             (p.get("name_required") or "").strip()]
    return re.sub(r"\s+", " ", " ".join(x for x in parts if x)).strip() or None


def post_json(url, body, headers=None, retries=RETRIES):
    """POST с ретраями; возвращает dict или None."""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    hdrs = {
        "Content-Type": "application/json",
        "User-Agent": UA,
        "Origin": BASE,
        "Referer": CATALOG_URL,
    }
    if headers:
        hdrs.update(headers)

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                payload = json.loads(r.read().decode("utf-8"))
            if isinstance(payload, dict):
                return payload
            raise ValueError(f"неожиданный тип ответа: {type(payload).__name__}")
        except (urllib.error.URLError, urllib.error.HTTPError, HTTPException,
                TimeoutError, ValueError, json.JSONDecodeError, OSError) as e:
            if attempt == retries:
                print(f"    [!] POST Failed после {retries} попыток: "
                      f"{type(e).__name__}: {str(e)[:120]}")
                return None
            time.sleep(2 ** attempt + random.uniform(0, 1))
    return None


def get_text(url, retries=RETRIES):
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            if attempt == retries:
                raise RuntimeError(f"GET {url}: {type(e).__name__}: {e}") from e
            time.sleep(2 ** attempt + random.uniform(0, 1))
    return None


def next_data(html):
    m = NEXT_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def collect_tree(nodes, parents=None):
    if parents is None:
        parents = []
    result = []
    for n in nodes or []:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        item = {
            "id": n["id"],
            "name": n.get("name") or "",
            "url": n.get("url") or "",
            "slug": re.sub(r"-\d+/?$", "", (n.get("url") or "").strip("/").split("/")[-1]),
            "depth": len(parents),
            "path": parents + [n.get("name") or ""],
        }
        result.append(item)
        result.extend(collect_tree(n.get("categories"), item["path"]))
    return result


def bootstrap():
    """Достаём API-хост, uuid и дерево категорий со страницы /catalog/."""
    html = get_text(CATALOG_URL)
    nd = next_data(html)
    if not nd:
        raise RuntimeError("__NEXT_DATA__ не найден на странице каталога")

    rc = nd.get("runtimeConfig") or {}
    api_host = (rc.get("browserAPIHost") or "").rstrip("/")
    puid = (nd.get("props") or {}).get("pageProps") or {}
    uuid = puid.get("uuid") or ""

    cats = []
    queries = (((puid.get("dehydratedState") or {}).get("queries")) or [])
    for q in queries:
        key = q.get("queryKey")
        key0 = key[0] if isinstance(key, list) and key else key
        if key0 not in ("catalog-main", "header-dropdown-and-menu"):
            continue
        dat = (q.get("state") or {}).get("data") or {}
        dat = dat.get("data") if isinstance(dat, dict) and "data" in dat else dat
        menu = (dat.get("menu") or {}) if isinstance(dat, dict) else {}
        tree = menu.get("catalog") or []
        if tree:
            # категории верхнего уровня покрывают весь каталог (проверено
            # на «Мясо»: родитель содержит все товары подкатегорий)
            cats = [c for c in collect_tree(tree) if c["depth"] == 0 and c["url"]]
            break

    if not api_host or not cats:
        raise RuntimeError(
            f"не удалось получить api_host={api_host!r} или категории ({len(cats)})")
    print(f"[bootstrap] API: {api_host}; uuid: {uuid[:8]}…; категорий: {len(cats)}")
    return api_host, uuid, cats


def make_body(cat, page):
    return {
        "url": cat["url"],
        "category_id": cat["id"],
        "sort": "default",
        "include": ["category", "products"],
        "pagination": {"per_page": PER_PAGE, "page": page},
        "is_tag": False,
        "is_edlp": False,
    }


def make_item(p, cat, seen):
    pid = p.get("id")
    if not pid:
        return None, False

    repr_ = p.get("price_representation") or {}
    price = money(p.get("price"))
    order_price = money(p.get("order_price"))
    old_price = money(p.get("cost"))
    values = [v for v in (price, order_price, old_price) if v is not None]
    style = repr_.get("style")
    promo = (price if style and style.startswith("special") else None)

    item = {
        "retailer": "globus",
        "product_id": pid,
        "name": clean_name(p),
        "category_path": list(cat["path"]),
        "category_slug": cat["slug"],
        "category_id": cat["id"],
        "url": BASE + p["url"] if p.get("url", "").startswith("/") else p.get("url"),
        "image_url": (p.get("preview_image") or {}).get("url"),
        "price": price,
        "order_price": order_price,
        "old_price": old_price,
        "promo_price": promo,
        "price_style": style,
        "price_min": min(values) if values else None,
        "price_max": max(values) if values else None,
        "uom": p.get("unit_price_text"),
        "package_type": p.get("package_type"),
        "weight_text": p.get("weight_text"),
        "basket_step": p.get("basket_step"),
        "quantity_max": p.get("quantity_max"),
        "in_stock": bool(p.get("active")),
        "badges": [b.get("code") for b in (p.get("badges") or [])
                   if isinstance(b, dict) and b.get("code")],
        "scraped_at": now_iso(),
    }

    if pid in seen:
        # тот же товар из другой категории: дополняем путь, цену обновляем
        old = seen[pid]
        for part in item["category_path"]:
            if part and part not in old["category_path"]:
                old["category_path"].append(part)
        if price is not None:
            old["price"], old["order_price"] = price, order_price
            old["old_price"], old["promo_price"] = old_price, promo
            old["price_style"] = style
            old["price_min"], old["price_max"] = (
                min(values) if values else None, max(values) if values else None)
            old["scraped_at"] = item["scraped_at"]
        return item, False
    seen[pid] = item
    return item, True


def checkpoint(seen):
    """Атомарная запись, чтобы прерывание не оставило битый JSON."""
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(list(seen.values()), f, ensure_ascii=False, indent=2)
    # на Windows замена файла может упереться в чужой открытый дескриптор
    for attempt in range(10):
        try:
            os.replace(tmp, OUT)
            return
        except PermissionError:
            time.sleep(1 + attempt * 0.5)
    raise RuntimeError(f"не удалось перезаписать {OUT}: файл занят")


async def main():
    os.makedirs(RAW_DIR, exist_ok=True)

    seen = {}
    if os.path.exists(OUT):
        try:
            for it in json.load(open(OUT, encoding="utf-8")):
                key = it.get("product_id")
                if key:
                    seen[key] = it
            print(f"[cache] товаров из прошлого прогона: {len(seen)}")
        except (json.JSONDecodeError, OSError) as e:
            print(f"[!] не удалось прочитать {OUT}: {e}")

    api_host, uuid, cats = bootstrap()
    api_url = f"{api_host}/api-web/v1/catalog:product-list"
    headers = {"X-App-Id": uuid} if uuid else None

    if os.path.exists(LINKS_FILE):
        cached = json.load(open(LINKS_FILE, encoding="utf-8"))
        if cached and len(cached) == len(cats):
            cats = cached
            print(f"[cache] категорий из файла: {len(cats)}")
        else:
            print("[cache] файл категорий устарел — использую свежий")
    json.dump(cats, open(LINKS_FILE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    done = json.load(open(DONE_FILE, encoding="utf-8")) if os.path.exists(DONE_FILE) else []
    done_set = set(done)

    total_new = 0
    for i, cat in enumerate(cats, 1):
        if cat["id"] in done_set:
            continue

        first = None
        for attempt in range(1, 4):
            first = post_json(api_url, make_body(cat, 1), headers)
            if first:
                break
            print(f"    [retry] {cat['name']}: попытка {attempt} не удалась")
            time.sleep(5 * attempt)
        if not first:
            print(f"[!] {cat['name']}: API не ответил — пропускаю")
            continue

        dat = first.get("data") or {}
        products = dat.get("products") or {}
        pag = products.get("pagination") or {}
        total_page = min(int(pag.get("total_page") or 1), MAX_PAGES)
        items = products.get("items") or []

        # сырой ответ первой страницы — для отладки/контроля качества
        raw_name = f"{cat['id']}_p1.json"
        if not os.path.exists(os.path.join(RAW_DIR, raw_name)):
            with open(os.path.join(RAW_DIR, raw_name), "w", encoding="utf-8") as f:
                json.dump(first, f, ensure_ascii=False)

        added = 0
        for p in items:
            _, is_new = make_item(p, cat, seen)
            added += int(is_new)
        checkpoint(seen)  # первая страница уже не потеряется при падении

        for page in range(2, total_page + 1):
            resp = post_json(api_url, make_body(cat, page), headers)
            if not resp:
                print(f"    [!] {cat['name']}: страница {page} не получена")
                continue
            page_added = 0
            for p in ((resp.get("data") or {}).get("products") or {}).get("items") or []:
                _, is_new = make_item(p, cat, seen)
                added += int(is_new)
                page_added += int(is_new)
            checkpoint(seen)
            print(f"    {cat['name']}: стр.{page}/{total_page} "
                  f"новых {page_added}, уникальных {len(seen)}", flush=True)
            await asyncio.sleep(random.uniform(0.2, 0.5))

        total_new += added
        print(f"[{i}/{len(cats)}] {cat['name']}: всего {pag.get('total')}, "
              f"страниц {total_page}, новых {added}, уникальных {len(seen)}", flush=True)

        # сначала товары, потом done — при прерывании состояние консистентно
        checkpoint(seen)
        done.append(cat["id"])
        json.dump(done, open(DONE_FILE, "w", encoding="utf-8"))
        await asyncio.sleep(random.uniform(0.4, 0.9))

    print(f"\nИТОГ: новых {total_new}, всего {len(seen)} товаров -> {OUT}")
    if seen:
        sample = next(iter(seen.values()))
        print("образец записи:", json.dumps(sample, ensure_ascii=True)[:600])


if __name__ == "__main__":
    asyncio.run(main())
