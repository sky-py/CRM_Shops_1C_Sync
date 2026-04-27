import asyncio
from enum import Enum
from functools import wraps
import json
import httpx
from retry import retry


REQUEST_TIMEOUT = httpx.Timeout(10.0, connect=3.0)
GET_ORDERS_REQUEST_TIMEOUT = httpx.Timeout(4.0, connect=3.0)
REQUESTS_RATE_EXCEEDED_TIME_TO_SLEEP = 30
ORDERS_PER_PAGE = 40


class Method(Enum):
    GET = 'GET'
    POST = 'POST'
    PUT = 'PUT'
    DELETE = 'DELETE'


class Route(Enum):
    GET_ORDERS = '/orders.json'
    ONE_ORDER = "/orders/{order_id}.json"
    CLIENT = "/clients/{client_id}.json"
    CHANGE_BONUSES = "/clients/{client_id}/bonus_system_transactions.json"
    GET_WEBHOOKS = "/webhooks.json"
    ONE_WEBHOOK = "/webhooks/{webhook_id}.json"
    WAREHOUSES = "/warehouses.json"


product = "/admin/products/"
one_blog = "/admin/blogs/"  # /admin/blogs/blog#.json  то что открывается по настройкам блога
blogs = "/admin/blogs.json"  # список блогов
one_article = "/admin/blogs/" # /admin/blogs/blog#/articles/arcticle#.json
articles = "/admin/blogs/"  # /admin/blogs/blog#/articles.json
clients = '/admin/clients.json'
one_client = '/admin/clients/'
reviews = '/admin/reviews.json'


async def sleep_if_rate_limit_reached(response: httpx.Response) -> None:
    remaining_limits = response.headers.get('api-usage-limit')
    print(f'Remaining limits: {remaining_limits if remaining_limits else 'Not found'}')
    if remaining_limits:
        remain, capacity = remaining_limits.split('/')
        if int(remain) / int(capacity) > 0.95:
            print(f'Exceeded limits, waiting {REQUESTS_RATE_EXCEEDED_TIME_TO_SLEEP} sec...')
            await asyncio.sleep(REQUESTS_RATE_EXCEEDED_TIME_TO_SLEEP)


def wait(func):
    @wraps(func)
    async def wrapper(*args, **kwargs) -> httpx.Response:
        return_value = await func(*args, **kwargs)
        if return_value:
            await sleep_if_rate_limit_reached(return_value)
            return return_value
    return wrapper


class Insales:
    headers = {"Content-Type": "application/json"}

    def __init__(self, main_url):
        self.main_url = main_url + '/admin'

    @wait
    @retry(stop_after_delay=300)
    async def make_request(self, method: Method, route: str, params=None, data=None) -> httpx.Response:
        url = self.main_url + route
        async with httpx.AsyncClient(headers=self.headers, timeout=REQUEST_TIMEOUT) as client:
            r = await client.request(method.value, url=url, params=params, content=data)
        r.raise_for_status()
        return r

    async def get_orders(self, page=1) -> httpx.Response:
        params = {'per_page': ORDERS_PER_PAGE, 'page': page}
        url = self.main_url + Route.GET_ORDERS.value
        async with httpx.AsyncClient(headers=self.headers, timeout=GET_ORDERS_REQUEST_TIMEOUT) as client:
            r = await client.get(url=url, params=params)
        r.raise_for_status()
        await sleep_if_rate_limit_reached(r)
        return r

    async def get_one_order(self, order_id: int | str) -> httpx.Response:
        return await self.make_request(Method.GET, Route.ONE_ORDER.value.format(order_id=order_id))

    async def write_order(self, order_id: int | str, data: dict) -> httpx.Response:
        return await self.make_request(Method.PUT, Route.ONE_ORDER.value.format(order_id=order_id), data=json.dumps(data))

    async def get_client(self, client_id) -> httpx.Response:
        return await self.make_request(Method.GET, Route.CLIENT.value.format(client_id=client_id))

    async def write_client(self, client_id, data) -> httpx.Response:
        return await self.make_request(Method.PUT, Route.CLIENT.value.format(client_id=client_id), data=json.dumps(data))

    async def change_bonuses(self, client_id: int | str, number_of_bonuses: int, description: str) -> httpx.Response:
        data = {
            "bonus_system_transaction": {
                "bonus_points": number_of_bonuses,
                "description": description
            }
        }
        return await self.make_request(Method.POST, Route.CHANGE_BONUSES.value.format(client_id=client_id), data=json.dumps(data))
    
    async def get_webhooks(self) -> httpx.Response:
        return await self.make_request(Method.GET, Route.GET_WEBHOOKS.value)
    
    async def create_webhook(self, data) -> httpx.Response:
        return await self.make_request(Method.POST, Route.GET_WEBHOOKS.value, data=json.dumps(data))
    
    async def delete_webhook(self, webhook_id) -> httpx.Response:
        return await self.make_request(Method.DELETE, Route.ONE_WEBHOOK.value.format(webhook_id=webhook_id))
    
    async def get_warehouses(self) -> httpx.Response:
        return await self.make_request(Method.GET, Route.WAREHOUSES.value)

    #
    # def get_clients(page):
    #     add = f'?per_page={results_per_page}&page={page}'
    #     return requests.get(url=f"{constants.main_url}{clients}{add}",
    #                         headers=headers)  # &per_page=100&page={page}
    #
    #
    # def get_reviews(page):
    #     add = f'?per_page={results_per_page}&page={page}'
    #     return requests.get(url=f"{constants.main_url}{reviews}{add}",
    #                         headers=headers)  # &per_page=100&page={page}
    #
    # def read_product(product_id, lang):
    #     return requests.get(url=f"{constants.main_url}{product}{str(product_id)}.json?lang={lang}",
    #                         headers=headers)
    #
    #
    # def write_product(product_id, order_template, lang):
    #     return requests.put(url=f"{constants.main_url}{product}{str(product_id)}.json?lang={lang}",
    #                         data=json.dumps(order_template), headers=headers)
    #
    #
    # def delete_product(product_id):
    #     return requests.delete(url=f"{constants.main_url}/admin/products/{product_id}.json", headers=headers)
    #
    #
    # def get_field_value(product_id, field_id, lang):
    #     return requests.get(
    #         url=f"{constants.main_url}{product}{str(product_id)}/product_field_values/{field_id}.json?lang={lang}",
    #         headers=headers)
    #
    #
    # def get_field_value_all(product_id, lang):
    #     return requests.get(
    #         url=f"{constants.main_url}{product}{str(product_id)}/product_field_values.json?lang={lang}",
    #         headers=headers)
    #
    #
    # def write_field_value(product_id, field_id, value, lang):
    #     return requests.put(
    #         url=f"{constants.main_url}{product}{str(product_id)}/product_field_values/{field_id}.json?lang={lang}",
    #         data=json.dumps(value), headers=headers)
    #
    #
    # def read_property_all(lang):
    #     return requests.get(url=f"{constants.main_url}/admin/properties.json?lang={lang}", headers=headers)
    #
    #
    # def write_property(id, title, lang):
    #     return requests.put(url=f"{constants.main_url}/admin/properties/{id}.json?lang={lang}",
    #                         data=json.dumps({"property": {"title": title}}),
    #                         headers=headers)
    #
    #
    # def read_characteristic_all(id, lang):
    #     return requests.get(url=f"{constants.main_url}/admin/properties/{id}/characteristics.json?lang={lang}",
    #                         headers=headers)
    #
    #
    # def write_characteristic(id, id_characteristic, title, lang):
    #     return requests.put(
    #         url=f"{constants.main_url}/admin/properties/{id}/characteristics/{id_characteristic}.json?lang={lang}",
    #         data=json.dumps({"characteristic": {"title": title}}),
    #         headers=headers)
    #
    #
    # def read_variant_all(lang):
    #     return requests.get(url=f"{constants.main_url}/admin/variant_fields.json?lang={lang}", headers=headers)
    #
    #
    # def write_variant(id, id_variant, title, lang):
    #     return requests.put(
    #         url=f"{constants.main_url}/admin/variants/{id}/variant_field_values/{id_variant}.json?lang={lang}",
    #         data=json.dumps({"characteristic": {"title": title}}),
    #         headers=headers)
    #
    #
    # def read_option_name_all(lang, page):
    #     return requests.get(url=f"{constants.main_url}/admin/option_names.json?lang={lang}", headers=headers)
    #
    #
    # def read_option_name(id, lang):
    #     return requests.get(url=f"{constants.main_url}/admin/option_names/{id}.json?lang={lang}", headers=headers)
    #
    #
    # def read_collection_all(lang):
    #     return requests.get(
    #         url=f"{constants.main_url}/admin/collections.json?lang={lang}?updated_since=2000-07-04+14%3A44%3A43+%2B0300",
    #         headers=headers)
    #
    #
    # def read_collection(id, lang):
    #     return requests.get(url=f"{constants.main_url}/admin/collections/{id}.json?lang={lang}", headers=headers)
    #
    #
    # def write_collection(id, template, lang):
    #     return requests.put(url=f"{constants.main_url}/admin/collections/{id}.json?lang={lang}", data=json.dumps(template),
    #                         headers=headers)
    #
    #
    # def read_page_all(lang):
    #     return requests.get(url=f"{constants.main_url}/admin/pages.json?lang={lang}", headers=headers)
    #
    #
    # def read_page(id, lang):
    #     return requests.get(url=f"{constants.main_url}/admin/pages/{id}.json?lang={lang}", headers=headers)
    #
    #
    # def write_page(id, template, lang):
    #     return requests.put(url=f"{constants.main_url}/admin/pages/{id}.json?lang={lang}", data=json.dumps(template),
    #                         headers=headers)
    #
    #
    # def create_page(template):
    #     return requests.post(url=f"{constants.main_url}/admin/pages.json", data=json.dumps(template),
    #                          headers=headers)
    #
    #
    # def read_blog(blog_id, lang):
    #     return requests.get(url=f"{constants.main_url}/admin/blogs/{blog_id}.json?lang={lang}", headers=headers)
    #
    #
    # def get_articles_list(blog_id, page, lang):
    #     return requests.get(
    #         url=f"{constants.main_url}/admin/blogs/{blog_id}/articles.json?lang={lang}&per_page=100&page={page}",
    #         headers=headers)
    #
    #
    # def read_article(article_id, blog_id, lang):
    #     return requests.get(url=f"{constants.main_url}/admin/blogs/{blog_id}/articles/{article_id}.json?lang={lang}",
    #                         headers=headers)
    #
    #
    # def write_article(article_id, blog_id, article_json, lang):
    #     return requests.put(url=f"{constants.main_url}/admin/blogs/{blog_id}/articles/{article_id}.json?lang={lang}",
    #                         data=json.dumps(article_json), headers=headers)
    #
    #
