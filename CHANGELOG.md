# История изменений

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).
Даты и хеши — по истории коммитов репозитория.

## [Unreleased]

- Добавлена документация: `README.md`, `docs/README.md`,
  `docs/COLLECTORS.md`, `docs/DATA_SCHEMA.md`, `requirements.txt`.

## 2026-11-27 — `2ce4d03` «Парсеры grocery: Глобус и Ашан»

### Added

- `globus_collect.py` — сборщик Глобуса через BFF API
  (`catalog:product-list`), 29 категорий верхнего уровня, до 1000 товаров
  за запрос. Итог: **48 158** товаров.
- `auchan_collect.py` — сборщик Ашана через `/v3/catalog/products/`
  из браузерного контекста Camoufox (обход Qrator), 56 категорий.
  Итог: **81 413** товаров.
- `globus_raw/` — сырые ответы первых страниц категорий Глобуса.
- `fix_fpgen.py` — восстановление `values.dat` для Camoufox при ошибке
  `Unable to create a ZSTDSeekContext`.
- `final_check.py` — сводная проверка локальных выгрузок.

### Fixed

- В сборщике Глобуса добавлены ретраи на `IncompleteRead` и других
  `HTTPException`;
- атомарная запись `*_products.json` с ретраем на `PermissionError`
  (перезапись файла, открытого другим процессом в Windows).

## 2026-11-27 — `94f2e07` «Парсеры grocery: pyaterochka_collect_v2.py»

- Обновлён сборщик Пятёрочки: полный DOM-сбор с persistent-профилем.
- Добавлены/обновлены скрипты прогрева профиля.

## 2026-11-27 — `1c929e6`, `445db90`

- Исправлена полнота прокрутки категорий X5 и разбор цен.
- Добавлен `pyaterochka_details.py` — сбор деталей карточек.

## 2026-11-27 — `71da6b5`

- Полный сбор Пятёрочки, базовый сбор Дикси, подготовка Перекрёстка.

## 2026-11-26 — `c6e27d8` «init»

- Первоначальная структура: Scrapy-проект `grocery/`, сборщики Чижика и
  Дикси, разведочные скрипты.
