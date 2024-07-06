import time
from enum import Enum
import requests
import json


REQUEST_TIMEOUT = 20
time_to_sleep = 30
results_per_page = 500
orders_per_page = 100


class Method(Enum):
    GET = 'get'
    POST = 'post'
    PUT = 'put'
    DELETE = 'delete'


class Route(Enum):
    GET_ORDERS = '/orders.json'
    ONE_ORDER = "/orders/{order_id}.json"
    CLIENT = "/clients/{client_id}.json"
    CHANGE_BONUSES = "/clients/{client_id}/bonus_system_transactions.json"


product = "/admin/products/"
one_blog = "/admin/blogs/"  # /admin/blogs/blog#.json  то что открывается по настройкам блога
blogs = "/admin/blogs.json"  # список блогов
one_article = "/admin/blogs/" # /admin/blogs/blog#/articles/arcticle#.json
articles = "/admin/blogs/"  # /admin/blogs/blog#/articles.json
clients = '/admin/clients.json'
one_client = '/admin/clients/'
reviews = '/admin/reviews.json'


def wait(func):
    def wrapper(*args, **kwargs) -> requests.Response:
        return_value = func(*args, **kwargs)
        if return_value:
            limits = return_value.headers['api-usage-limit']
            print('limits: ', limits)
            limits = limits.split('/')
            if int(limits[0])/int(limits[1]) > 0.95:
                print(f'waiting {time_to_sleep} sec')
                time.sleep(time_to_sleep)
            return return_value
    return wrapper


class Insales:
    headers = {"Content-Type": "application/json"}

    def __init__(self, main_url):
        self.main_url = main_url + '/admin'

    @wait
    def make_request(self, method: Method, route: str, params=None, data=None) -> requests.Response:
        if params is None:
            params = {}
        if data is None:
            data = {}
        url = self.main_url + route
        match method:
            case Method.GET: r = requests.get(url=url, headers=self.headers, params=params, timeout=REQUEST_TIMEOUT)
            case Method.PUT: r = requests.put(url=url, headers=self.headers, params=params, data=data, timeout=REQUEST_TIMEOUT)
            case Method.POST: r = requests.post(url=url, headers=self.headers, params=params, data=data, timeout=REQUEST_TIMEOUT)
            case Method.DELETE: r = requests.delete(url=url, headers=self.headers, params=params, data=data, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r

    def get_orders(self, page=1) -> requests.Response:
        params = {'per_page': orders_per_page, 'page': page}
        return self.make_request(Method.GET, Route.GET_ORDERS.value,  params=params)

    def get_one_order(self, order_id: int | str) -> requests.Response:
        return self.make_request(Method.GET, Route.ONE_ORDER.value.format(order_id=order_id))

    def write_order(self, order_id: int | str, data: dict) -> requests.Response:
        return self.make_request(Method.PUT, Route.ONE_ORDER.value.format(order_id=order_id), data=json.dumps(data))

    def get_client(self, client_id) -> requests.Response:
        return self.make_request(Method.GET, Route.CLIENT.value.format(client_id=client_id))

    def write_client(self, client_id, data) -> requests.Response:
        return self.make_request(Method.PUT, Route.CLIENT.value.format(client_id=client_id), data=json.dumps(data))

    def change_bonuses(self, client_id: int | str, number_of_bonuses: int, description: str) -> requests.Response:
        data = {
            "bonus_system_transaction": {
                "bonus_points": number_of_bonuses,
                "description": description
            }
        }
        return self.make_request(Method.POST, Route.CHANGE_BONUSES.value.format(client_id=client_id), data=json.dumps(data))

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
