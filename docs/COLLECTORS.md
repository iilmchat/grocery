# Сборщики по сетям

Здесь — подробности, которые не поместились в [README.md](../README.md).
Каждый раздел соответствует одному файлу в корне репозитория.

## Ашан — `auchan_collect.py`

**Тип:** API через браузерный контекст. **Результат:** `auchan_products.json`.

Почему браузер: сайт за Qrator, простой `urllib`/`requests` получает `401`
с крошечным телом. В Camoufox челлендж проходится автоматически, куки
сохраняются в persistent-профиле `profile_auchan/`.

- Страница каталога: `https://www.auchan.ru/catalog/` → 56 ссылок
  `/catalog/<code>/` (кеш `auchan_links.json`).
- API: `POST https://www.auchan.ru/v3/catalog/products/?orderField=rank&orderDirection=asc&merchantId=0&deliveryAddressSelected=0&perPage=100&page=N`
- Тело запроса:

  ```json
  {
    "filter": {
      "cashback_only": false,
      "active_only": true,
      "promo_only": false,
      "category": ["ovoschi-frukty-zelen-griby-yagody"]
    }
  }
  ```

- Ответ: `{"items": [...], "range": 1292, "activeRange": ..., "minPrice": ..., "maxPrice": ...}`.
  Количество страниц = `ceil(range / 100)`.
- Даже при `perPage=200` / `perPage=1000` API возвращает **100** товаров —
  это жёсткий лимит сервера.
- URL товара собирается как `https://www.auchan.ru/product/<code>/`.
- Категория `bezalkogolnoe-vino-i-pivo` ответила 404 и пропускается;
  вино всё равно присутствует через категорию «Алкоголь (самовывоз)».

Кеши: `auchan_links.json`, `auchan_done.json`, `profile_auchan/`.

## Глобус — `globus_collect.py`

**Тип:** чистый API, без браузера. **Результат:** `globus_products.json`.

- `GET https://online.globus.ru/catalog/` → из `__NEXT_DATA__` берём
  `runtimeConfig.browserAPIHost` и `props.pageProps.uuid`.
- Там же в `catalog-main` лежит дерево категорий; в сбор берётся только
  **верхний уровень** (29 узлов): проверено на «Мясе», что родитель содержит
  все товары подкатегорий.
- API: `POST {browserAPIHost}/api-web/v1/catalog:product-list`
  с телом `{url, category_id, sort, include: ["category","products"],
  pagination: {per_page, page}, is_tag, is_edlp}`.
- Заголовок `X-App-Id: <uuid>`; авторизация не нужна.
- `per_page` до **1000** — самый быстрый сборщик в репозитории.
- Цены приходят **в копейках**, делятся на 100. `price` — цена за единицу
  (≈ 1 шт или 1 кг), `order_price` — за упаковку, `cost` — старая цена.
- Сырые ответы первых страниц сохраняются в `globus_raw/<category_id>_p1.json`.

Кеши: `globus_links.json`, `globus_done.json`.

## Чижик — `chizhik_collect.py`

**Тип:** API через `page.evaluate(fetch)` в Camoufox. **Результат:** `chizhik_products.json`.

- Store: `HBBN`.
- Категории: `GET /catalog/v3/stores/HBBN/categories?mode=delivery&include_subcategories=1&include_restrict=true`.
- Товары: `GET /catalog/v2/stores/HBBN/categories/{cid}/overview?mode=delivery`.
- Если в родителе меньше товаров, чем `products_count`, отдельно дёргаются
  overview подкатегорий.
- Сырые overview сохраняются в `overviews/<cid>.json`.
- Ключ дедупликации — `plu`; если товар попал в несколько категорий,
  `category_path` дополняется.
- Кеша `*_done.json` нет: повторный прогон просто переписывает выгрузку.

## Дикси — `dixy_collect.py`

**Тип:** DOM + Camoufox. **Результат:** `dixy_products.json`.

- Ссылки: `https://dixy.ru/catalog/` → все `a[href*="/catalog/"]`
  (кеш `dixy_links.json`).
- На странице категории нажимается «Показать ещё» или прокручивается лента,
  пока количество `article` перестанет расти.
- Из карточки берутся `href`, `img`, `h2/h3/alt` и все `[class*=price]`;
  `price_min` / `price_max` — минимум и максимум найденных чисел.
- Чекпоинт каждые 5 категорий.

## Пятёрочка — `pyaterochka_collect_v2.py`

**Тип:** DOM + Camoufox, persistent-профиль. **Результат:** `pyaterochka_products.json`.

- Ссылки: `https://5ka.ru/catalog/` → href с `--` (кеш `pyaterochka_links.json`).
- Профиль `profile_5ka`, `i_know_what_im_doing=True`.
- `scroll_collect()` опрашивает DOM с шагом 1 с, ждёт до 18 с появления новых
  карточек; конец списка — нет новых карточек и высота не растёт; для
  «дёрганья» ленивой подгрузки делает толчок вверх/вниз.
- Цена: `meta[itemprop="price"]` (рубли с копейками), fallback — пары
  `[data-qa="price-tag-rubles"]` + `[data-qa="price-tag-pennies"]`, затем
  числа рядом с `₽`.
- Капча определяется по заголовку и виджету; при Detected прогон останавливается.
- Дополнительно: `pyaterochka_details.py` — сбор деталей карточек.

## Перекрёсток — `perekrestok_collect_v2.py`

**Тип:** DOM + Camoufox, persistent-профиль. **Результат:** `perekrestok_products.json`.

Та же логика, что у Пятёрочки, но:

- база `https://www.perekrestok.ru`, ссылки берутся с `/cat`;
- профиль `profile_pk`;
- при капче скрипт ждёт 10 минут и повторяет категорию до 3 раз, затем
  останавливает прогон.

Подготовка профиля: `warmup_pk.py` (для Пятёрочки — `warmup_5ka.py`).

## Вспомогательные скрипты

| Файл | Назначение |
| :--- | :--- |
| `smoke_env.py` | проверка Python и Camoufox |
| `fix_fpgen.py` | восстановление `values.dat` для Camoufox |
| `final_check.py` | сводка по всем локальным выгрузкам |
| `make_export_5ka.py` | экспорт 5ka-подобных JSON в `exports/` |
| `compare_5ka.py`, `compare_details.py` | сравнение выгрузок с эталоном |
| `extract_next_data.py` | вытаскивание `__NEXT_DATA__` из сохранённого HTML |
| `recon_stores.py`, `recon2.py`, `probe_*.py`, `sniff_*.py` | разведка сайтов и API |
| `grocery/` | экспериментальный Scrapy-проект |
