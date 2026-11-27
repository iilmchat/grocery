# Формат выходных данных

Каждый сборщик пишет массив объектов в `*_products.json`:

```json
[
  { "retailer": "globus", "product_id": "...", "name": "...", "...": "..." },
  { "retailer": "globus", "product_id": "...", "name": "...", "...": "..." }
]
```

Все цены в готовых файлах — **рубли** (`float`, копейки отделены точкой).
В API Глобуса цены приходят в копейках; сборщик делит их на 100.
`scraped_at` — ISO-8601, UTC, например `2026-11-27T02:33:13.123456+00:00`.

## Общие поля

| Поле | Тип | Описание | Где есть |
| :--- | :--- | :--- | :--- |
| `retailer` | string | Идентификатор сети: `globus`, `auchan`, `chizhik`, `dixy`, `pyaterochka`, `perekrestok` | везде |
| `product_id` | string / int | `plu` у Чижика, артикул/ID у остальных | везде, кроме Дикси (используется `url`) |
| `name` | string | Название товара | везде |
| `url` | string | Абсолютная ссылка на карточку | везде |
| `image_url` | string / null | Ссылка на изображение | везде |
| `category_path` | array[string] | Путь(category) — от сети до подкатегории | Chizhik, Globus, Auchan |
| `category_slug` | string | Слаг категории, откуда взят товар | Dixy, X5, Globus, Auchan |
| `price` | float / null | Текущая цена | Chizhik, Globus, Auchan |
| `price_min` | float / null | Меньшая из найденных цен (обычно акционная) | Dixy, X5, Globus, Auchan |
| `price_max` | float / null | Большая из найденных цен (обычно обычная) | Dixy, X5, Globus, Auchan |
| `scraped_at` | string | Время получения записи | везде |

## Поля по сетям

### Глобус (`globus_products.json`)

| Поле | Описание |
| :--- | :--- |
| `product_id` | ID вида `000000000000746791_ST` |
| `category_path` | Путь по дереву; если товар в нескольких категориях — пути дополняются |
| `category_id`, `category_slug` | Категория верхнего уровня, откуда товар впервые получен |
| `price` | Цена за единицу (`price` API / 100) |
| `order_price` | Цена за упаковку (`order_price` / 100); для весовых товаров отличается от `price` |
| `old_price` | Старая цена (`cost` / 100), если есть |
| `promo_price` | `price`, если `price_representation.style` начинается с `special` |
| `price_style` | `regular` / `special` / `special+regular_crossed` |
| `uom` | Единица цены (`1 кг`, `1 шт`) |
| `package_type` | `piece` / `weight` / `weight-by-piece` |
| `weight_text`, `basket_step`, `quantity_max` | Параметры весового товара |
| `in_stock` | `active` из API |
| `badges` | Массив кодов бейджей |

### Ашан (`auchan_products.json`)

| Поле | Описание |
| :--- | :--- |
| `product_id` | `productId` из API (int) |
| `category_path` | названия из `categoryCodes` (сеть → подкатегория) |
| `category_slug` | Код категории каталога (`bakaleya`, `superceny`, ...) |
| `price`, `old_price` | `price.value`, `oldPrice.value` |
| `discount_percent` | Процент скидки из API |
| `brand` | Название бренда |
| `uom` | `price.per` (`weight_kg`, `piece`, ...) |
| `rating`, `reviews` | Рейтинг и число отзывов |
| `in_stock` | `active` и не `stock.not_available` |
| `badges` | Массив текстов/кодов бейджей |

### Чижик (`chizhik_products.json`)

| Поле | Описание |
| :--- | :--- |
| `product_id` | `plu` |
| `store_id` | Магазин (`HBBN`) |
| `price`, `promo_price` | Обычная и акционная цена из `prices` |
| `in_stock`, `stock_limit` | Наличие и остаток |
| `uom`, `rating`, `rates_count` | Единица, рейтинг, число оценок |
| `max_qty_per_order`, `orange_loyalty_points`, `property_clarification` | Доп. поля API |

### Дикси (`dixy_products.json`)

Минимальный набор: `retailer`, `url`, `name`, `image_url`, `category_slug`,
`price_min`, `price_max`, `scraped_at`. `price_min`/`price_max` вычисляются
из всех чисел, найденных в элементах карточки с классом `price`.
Поле	Описание
price_min / price_max	Из акционной и обычной цены карточки
price_old	Зачёркнутая цена (card__price-crossed), если есть
rating, badge	Рейтинг («4.6») и бейдж («по акции»)
category_name	Название секции с карточки

### Пятёрочка / Перекрёсток

Набор X5: `retailer`, `product_id`, `url`, `name`, `image_url`,
`category_slug`, `badge`, `scraped_at`, опционально `price_min` / `price_max`.
Цены берутся из `meta[itemprop="price"]`, затем из span-ов рублей/копеек,
затем из текста рядом с `₽`.

## Примеры

Глобус:

```json
{
  "retailer": "globus",
  "product_id": "000000000000746791_ST",
  "name": "Каша ржаная Yelli яблоко-корица 60г",
  "category_path": ["Акции", "Бакалея", "Здоровый выбор"],
  "category_slug": "akcii",
  "category_id": 20,
  "price": 73.99,
  "order_price": 73.99,
  "old_price": 99.99,
  "price_min": 73.99,
  "price_max": 99.99,
  "price_style": "special",
  "uom": "1 шт",
  "in_stock": true,
  "scraped_at": "2026-11-27T02:33:13.123456+00:00"
}
```

Ашан:

```json
{
  "retailer": "auchan",
  "product_id": 55839,
  "name": "Фейхоа, вес",
  "category_path": ["Овощи, фрукты, орехи", "Фрукты", "Экзотические"],
  "category_slug": "ovoschi-frukty-zelen-griby-yagody",
  "url": "https://www.auchan.ru/product/feyhoa_kg_ves/",
  "price": 249.99,
  "old_price": 449.99,
  "discount_percent": 44,
  "uom": "weight_kg",
  "in_stock": true,
  "scraped_at": "2026-11-27T03:56:47.654321+00:00"
}
```

> Поля `category_path` и `category_id` у Глобуса отражают **первую**
> категорию, в которой товар был встречен; при повторной встрече путь
> дополняется. Поэтому `category_slug` не всегда совпадает с первым
> элементом `category_path`.
