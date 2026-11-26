import scrapy


class DixySpider(scrapy.Spider):
    name = "dixy"
    allowed_domains = ["dixy.ru"]
    start_urls = ["https://dixy.ru"]

    def parse(self, response):
        pass
