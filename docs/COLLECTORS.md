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

## Верный — `verno_collect.py` (API приложения)

Официальный сайт сети — `https://www.verno-info.ru/` (IP `185.191.32.15`,
доступен). Страница `/products` показывает только PDF-каталоги акций по
регионам (`/storage/catalogs/<region>/...pdf`) и не содержит товаров с
ценами. Адрес `verny.ru` (`31.177.76.145`) — не сайт сети: DNS резолвится,
но TCP/443 таймаутится — по этому симптому почти наверняка и проверялся
«недоступный» домен в старом прогоне.

Настоящий каталог обслуживает мобильное приложение `ru.vcr.verniy_all`:
его API-эндпоинты вытащены из APK, скачанного через публичный API RuStore
(`backapi.rustore.ru/applicationData/overallInfo/...` → `download-link`).

Авторизация (проверена 27.11.2026 на реальном номере):

1. `POST https://apptrade.ivoin.ru/api/v2/auth/send-sms` — телефон плюс
   четыре поля согласий (`agreement_user`, `agreement_user_date`,
   `agreement_adv`, `agreement_adv_date`); ответ `expires_in: 600`.
2. `POST .../v2/auth/verify-sms` с `phone` и `code` — временный токен
   `temp_…`, поле `is_registered: false`.
3. `POST .../v2/register` с `{token, phone, name, lastname, region}` —
   постоянный JWT и `delivery_token`. `region` — **не** 1, а ID из
   `GET .../v2/region-indices` (Москва = `3`).
4. `POST .../v2/devicekit` с JWT — регистрация устройства.

Каталог без цен доступен через `apptrade` по подписанным S3-ссылкам
(заголовок `Authorization: Bearer <JWT>`, `X-Region-City-Id: 3`):

| Эндпоинт | Что отдаёт |
| :--- | :--- |
| `GET .../v2/catalog/categories` | URL на JSON с 229 категориями |
| `GET .../v2/catalog/filters` | URL на JSON с 31 367 ID товаров (фacet'ы, без цен) |
| `POST .../v2/catalog/products/urls` с `{"uuids": [...]}` | URLs на JSON товаров по их ID: имя, картинка, описание, характеристики, но **без цен** |

Цены и остатки живут в API `https://app.verno-dostavka.ru/api3/`.
Аутентификация там — **query-параметр `delivery_token`** (не `Authorization`).
Каталожные эндпоинты сначала отвечают `400 «Не выбран магазин»`: магазин
фиксируется на сервере, когда пользователь выбирает его в приложении.
После выбора в приложении `GET /api3/catalog/categories-and-combos`,
`/api3/catalog/combos/`, `/api3/catalog/sliders/` и `/api4/sync/stocks`
начинают отдавать данные. Текущий `store_id` берётся из
`GET /api3/address/get-addresses`.

Цены отдаёт `apptrade`:
`GET .../v2/catalog/prices/<store_id>` (Bearer JWT) возвращает подписанную
ссылку на `price.ivoin.ru/mp/prices/<store_id>.json` с полями
`goods_id`, `price_for_unit`, `with_sale`, `price_for_quantum`.

Сборщик [`verno_collect.py`](../verno_collect.py) объединяет категории,
индекс товаров, карточки, цены и остатки в `verno_products.json`. Токены
создаёт [`verno_login.py`](../verno_login.py) и сохраняет в
`verno_auth.json` (в Git не попадает). Важно: повторный вход в приложении
инвалидирует предыдущий JWT — перед сбором нужно перелогиниться.

Алгоритм:

1. `GET .../v2/catalog/categories` → 229 категорий (построение `category_path`).
2. `GET .../v2/catalog/filters` → индекс из 31 367 товаров.
3. `GET .../v2/catalog/prices/<store_id>` → цены и скидки по магазину.
4. `GET https://app.verno-dostavka.ru/api4/sync/stocks?delivery_token=…`
   → остатки (`max_count`).
5. `POST .../v2/catalog/products/urls` батами по **100** UUID (лимит API)
   → подписанные ссылки на карточки; карточки кешируются в
   `verno_goods_cache.jsonl`.

В контрольном прогоне 27.11.2026: **4 466 товаров с ценами**, из них
3 725 в наличии, 182 категории. Цены привязаны к конкретному магазину —
товары без цены в нём в выгрузку не попадают.

## Победа — разведка 27.11.2026, сборщик не добавлен

Сайт `https://магазинпобеда.рф/` — витрина с новостями и списком магазинов,
каталога цен там нет. Приложение `ru.tkleto.app.magazinpobeda` (Kotlin +
Ktor), APK скачан через публичный API RuStore (`appId 2063596798`).
OpenAPI-спецификации доступны по `/core/openapi.json` и `/openapi.json`.

| Назначение | Эндпоинт | Доступ |
| :--- | :--- | :--- |
| Каталог | `GET https://pobeda-magazin.siberian.pro/core/api/catalog/` | без токена отдаёт только 87 товаров; параметры `category_ids`, `shop_id`, `limit`, `offset`, `sort`, `search` |
| Категории | `GET .../core/api/categories/?parent_id=…` | 4 корня, подкатегории через `parent_id` |
| Магазины | `GET .../core/api/shops` | 791 магазин |
| Карточка | `GET .../core/api/catalog/{goods_id}`, `/ean/{ean}` | без токена |
| Фильтры | `GET .../core/api/catalog/filters?category_ids=…` | `401 Invalid authentication credentials` |
| Полная выгрузка | `GET .../core/api/catalog/sync?shop_id=…&updated_to=…&limit=…&after_id=…` | `401`, нужен JWT |
| OTP | `POST https://fastapi-app-prod.gulliver-ul.ru/auth/api/auth/otp/generate` | `{"phone": "+7…"}`, ответ `retryAfter` |
| Токены | `POST .../auth/api/auth/sms` | `{"phone", "code"}` → `access_token`, `refresh_token` |

Важно: префиксы разные — `core/api/…` и `auth/api/…` (не просто `/api/…`).
Анонимный каталог одинаков для всех магазинов: 25 случайных `shop_id`
дали те же 87 `goods_id`. Похоже, полный ассортимент открывается только
через `/catalog/sync` с JWT.

Проблема на текущий момент: после успешной отправки OTP хост
`fastapi-app-prod.gulliver-ul.ru` (`185.175.44.20:443`) перестал отвечать по
TCP, обменять код на токен не удалось. Хост
`pobeda-magazin.siberian.pro/auth/...` жив, но его БД не знает этот номер
(`user_not_found`). Дальше — повторить OTP, когда auth-хост поднимется,
и проверить `/catalog/sync`.

## Магнит — `magnit_collect.py` (webgate API сайта)

В отличие от предыдущих сетей, у Магнита есть полноценный интернет-магазин
`https://magnit.ru/` с ценами. Сайт на Nuxt; API вызывается без авторизации:

- `POST https://magnit.ru/webgate/v2/goods/search`
- заголовки: `X-Client-Name: magnit`, `X-Device-Platform: Web`,
  `X-App-Version: 2026.11.27-12.47`, `X-Platform-Version`, `X-Device-ID`,
  `X-Device-Tag: disabled`;
- тело: `{pagination:{limit:50,offset}, sort:{order:"desc",type:"popularity"},
  storeCode:"992301", storeType:"dostavka", catalogType:"2", term:"",
  categories:[id]}`.

Важно: `limit` больше 50 и `offset` больше ~10 000 дают 400 (`pagoffset`).
Поэтому сборщик разбивает каталог по **753 категориям** из
`/__sitemap__/catalog.xml` и в каждой идёт по `pagination.nextOffset`.
Поля `categories` должны быть целыми числами; `categoryIDs` игнорируется.
`storeCode` берётся из `window.__NUXT__.config` главной страницы
(по умолчанию Краснодар, `992301`), переопределяется `MAGNIT_STORE_CODE`.

Цены приходят **в копейках** (`price`, `promotion.oldPrice`), скидка — в
`promotion`. Ещё доступны `/webgate/v1/goods/filters` (фильтры/бренды),
`/webgate/v2/goods/multisearch`, `/webgate/catalog-bdui/v2/shelf`; картинки
раздаёт `images-foodtech.magnit.ru`.

Контрольный прогон 27.11.2026 для магазина `992301`: **21 126 товаров**,
все с ценами, без ошибок; 279 категорий с товарами (из 752 URL в sitemap).

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
