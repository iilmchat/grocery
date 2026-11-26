import json
from datetime import datetime, timezone

import scrapy

from grocery.items import Product


class ChizhikSpider(scrapy.Spider)
    name = chizhik
    store = HBBN  # ID магазина из твоего дампа

    custom_settings = {
        CONCURRENT_REQUESTS 4,
        DOWNLOAD_DELAY 0.5,
        DEFAULT_REQUEST_HEADERS {
            Accept texthtml,applicationjson,,
            Accept-Language ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,
            Referer httpschizhik.club,
            User-Agent (
                Mozilla5.0 (Windows NT 10.0; Win64; x64) AppleWebKit537.36 
                (KHTML, like Gecko) Chrome126.0 Safari537.36
            ),
        },
    }

    def start_requests(self)
        yield scrapy.Request(httpschizhik.clubcatalog, callback=self.parse_catalog)

    def parse_catalog(self, response)
        # buildId меняется при каждом деплое — берём со страницы, не хардкодим
        raw = response.xpath('script[@id=__NEXT_DATA__]text()').get()
        build_id = json.loads(raw)[buildId] if raw else None
        if not build_id
            self.logger.warning(buildId не найден — идём только по HTML)

        for href in response.css('a[href=catalog]attr(href)').getall()
            slug = href.rstrip().rsplit(, 1)[-1]
            if -- not in slug
                continue

            if build_id
                yield scrapy.Request(
                    fhttpschizhik.club_nextdata{build_id}catalog{slug}.json,
                    callback=self.parse_category_json,
                    meta={slug slug, build_id build_id},
                    priority=10,  # JSON-путь в приоритете
                )
            yield response.follow(href, callback=self.parse_category_html,
                                  meta={slug slug}, priority=1)

    def parse_category_json(self, response)
        Основной путь JSON-роут Next.js по живому buildId.
        if response.status != 200
            self.logger.info(JSON-роут отдал %s для %s, response.status, response.meta[slug])
            return
        data = response.json()
        items = self._extract_products(data.get(pageProps, {}))
        self.logger.info(Категория %s (json) %d товаров, response.meta[slug], len(items))
        for item in items
            yield self._format_product_item(item, response.meta[slug])

    def parse_category_html(self, response)
        Фолбэк товары из __NEXT_DATA__ внутри HTML страницы.
        raw = response.xpath('script[@id=__NEXT_DATA__]text()').get()
        if not raw
            self.logger.warning(В HTML категории нет __NEXT_DATA__ %s, response.url)
            return
        data = json.loads(raw)
        props = data.get(props, {}).get(pageProps, {})
        items = self._extract_products(props)
        self.logger.info(Категория %s (html) %d товаров, response.meta[slug], len(items))
        for item in items
            yield self._format_product_item(item, response.meta[slug])

    @staticmethod
    def _extract_products(node, found=None, depth=0)
        Рекурсивно ищем объекты с plu+name в глубоко вложенном pageProps.
        if found is None
            found = []
        if depth  30  # страховка от бесконечной вложенности
            return found
        if isinstance(node, dict)
            if plu in node and name in node
                found.append(node)
            else
                for value in node.values()
                    ChizhikSpider._extract_products(value, found, depth + 1)
        elif isinstance(node, list)
            for value in node
                ChizhikSpider._extract_products(value, found, depth + 1)
        return found

    def _format_product_item(self, item, category_slug)
        prices = item.get(prices) or []
        price_map = {p.get(placement_type) p.get(value) for p in prices}

        attrs = {a.get(name) a.get(value) for a in (item.get(attributes) or [])}
        photos = (item.get(image_links) or {}).get(normal) or []
        rating = item.get(rating) or {}
        plu = item.get(plu)

        return Product(
            retailer=chizhik,
            product_id=plu,
            name=item.get(name),
            category_path=[category_slug],
            price=price_map.get(regular_primary),
            promo_price=next(
                (v for k, v in price_map.items() if k != regular_primary), None
            ),
            url=fhttpschizhik.clubproduct{plu},
            image_url=photos[0] if photos else None,
            store_id=self.store,
            scraped_at=datetime.now(timezone.utc).isoformat(),
            in_stock=item.get(is_available),
            stock_limit=item.get(stock_limit),
            uom=item.get(uom),
            rating=rating.get(rating_average),
            rates_count=rating.get(rates_count),
            ingredients=item.get(ingredients),
            attributes=attrs,
            nutrients={n.get(text) n.get(value) for n in (item.get(nutrients) or [])},
        )
