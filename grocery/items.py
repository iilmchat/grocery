import scrapy


class Product(scrapy.Item):
    retailer = scrapy.Field()      # "chizhik" / "dixy"
    product_id = scrapy.Field()    # plu у Чижика, артикул у Дикси
    name = scrapy.Field()
    category_path = scrapy.Field() # пока слаг категории, потом нормализуем
    price = scrapy.Field()
    promo_price = scrapy.Field()
    url = scrapy.Field()
    image_url = scrapy.Field()
    store_id = scrapy.Field()
    scraped_at = scrapy.Field()
    # доп. поля из API Чижика
    in_stock = scrapy.Field()
    stock_limit = scrapy.Field()
    uom = scrapy.Field()
    rating = scrapy.Field()
    rates_count = scrapy.Field()
    ingredients = scrapy.Field()
    attributes = scrapy.Field()
    nutrients = scrapy.Field()
