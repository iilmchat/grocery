from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem


class DedupePipeline:
    """Убираем дубли товаров по паре (retailer, product_id)."""

    def __init__(self):
        self.seen = set()

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        key = (adapter.get("retailer"), adapter.get("product_id"))
        if key in self.seen:
            raise DropItem(f"Дубликат: {key}")
        self.seen.add(key)
        return item
