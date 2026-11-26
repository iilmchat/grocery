# settings.py (общие)
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

ITEM_PIPELINES = {
    "grocery.pipelines.DedupePipeline": 300,
}

# Приоритет живости над вежливостью: у Чижика уже есть антибот,
# и robots.txt тут ничего не решает. Если не хочешь — оставь True.
ROBOTSTXT_OBEY = False

# Логи парсинга читаемее
LOG_LEVEL = "INFO"
