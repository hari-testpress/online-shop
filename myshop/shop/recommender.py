import redis
from django.conf import settings
from .models import Product
import itertools


# connect to redis
redis_client = redis.Redis(
    host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB
)


class Recommender(object):
    def get_product_key(self, id):
        return f"product:{id}:purchased_with"

    def products_bought(self, products):
        product_ids = [p.id for p in products]
        combinations = itertools.combinations(product_ids, 2)
        for product_id, purchased_with_id in combinations:
            redis_client.zincrby(
                self.get_product_key(product_id), 1, purchased_with_id
            )

    def suggest_products_for(self, products, max_results=6):
        product_ids = [p.id for p in products]
        if len(products) == 1:
            suggestions = self.for_single_product(product_ids[0], max_results)
        else:
            tmp_key = self.create_redis_unionstore(product_ids)
            suggestions = self.get_suggestions_from_redis(tmp_key, max_results)
        suggested_products = self.get_suggested_product_objects(suggestions)
        return suggested_products

    def for_single_product(self, product_id, max_results):
        return redis_client.zrange(
            self.get_product_key(product_id), 0, -1, desc=True
        )[:max_results]

    def create_redis_unionstore(self, product_ids):
        flat_ids = "".join([str(id) for id in product_ids])
        tmp_key = f"tmp_{flat_ids}"
        keys = [self.get_product_key(id) for id in product_ids]
        redis_client.zunionstore(tmp_key, keys)
        redis_client.zrem(tmp_key, *product_ids)
        return tmp_key

    def get_suggested_product_objects(self, suggestions):
        suggested_products_ids = [int(id) for id in suggestions]
        suggested_products = list(
            Product.objects.filter(id__in=suggested_products_ids)
        )
        suggested_products.sort(
            key=lambda x: suggested_products_ids.index(x.id)
        )
        return suggested_products

    def get_suggestions_from_redis(self, tmp_key, max_results):
        suggestions = redis_client.zrange(tmp_key, 0, -1, desc=True)[
            :max_results
        ]
        redis_client.delete(tmp_key)
        return suggestions

    def clear_purchases(self):
        for id in Product.objects.values_list("id", flat=True):
            redis_client.delete(self.get_product_key(id))
