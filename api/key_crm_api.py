import json
import requests
from enum import Enum

REQUEST_TIMEOUT = 20
results_per_page = 50
include_order_fields = 'buyer,manager,products.offer,shipping.deliveryService,custom_fields,payments'
main_url = 'https://openapi.keycrm.app/v1'

headers = {
    'Content-type': 'application/json',
    'Accept': 'application/json',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Authorization': f'Bearer + key'
}


class Method(Enum):
    GET = 'get'
    POST = 'post'
    PUT = 'put'


class Route(Enum):
    ORDER = '/order'
    STAGE = '/order/status'
    PAYMENT_METHODS = '/order/payment-method'
    OFFERS = '/offers'


class KeyCRM:
    def __init__(self, api_key):
        self.headers = headers
        self.headers['Authorization'] = f'Bearer {api_key}'

    def raw_request(self, url):
        r = requests.get(url=url, headers=headers, timeout=REQUEST_TIMEOUT)
        return r

    def make_request(self, method: Method, route: str, params=None, data=None) -> dict:
        if params is None:
            params = {}
        if data is None:
            data = {}
        url = main_url + route
        match method:
            case Method.GET: r = requests.get(url=url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            case Method.PUT: r = requests.put(url=url, headers=self.headers, params=params, data=data, timeout=REQUEST_TIMEOUT)
            case Method.POST: r = requests.post(url=url, headers=self.headers, params=params, data=data, timeout=REQUEST_TIMEOUT)
        print('Remaining limit:', r.headers.get('X-Ratelimit-Remaining'))
        return r.json()

    def get_orders(self, last_orders_amount=results_per_page, filter: dict = None) -> list:
        """
        Returns list of orders dicts
        :param last_orders_amount: 0 meens ALL
        :param filter: dictionary of filters
        :return: list of orders dicts
        """
        params = {'limit': results_per_page,
                  'include': include_order_fields,
                  }

        if filter is not None:
            for key, value in filter.items():
                params[f'filter[{key}]'] = value

        r = self.make_request(Method.GET, Route.ORDER.value, params=params)

        if last_orders_amount == 0:
            pages = r['last_page']
        else:
            pages = last_orders_amount // results_per_page + (last_orders_amount % results_per_page > 0)

        orders = r['data']
        if pages == 1:  # all orders on one page, no need to fetch more pages
            return orders
        else:
            for page in range(2, pages + 1):
                params['page'] = page
                r = self.make_request(Method.GET, Route.ORDER.value, params=params)
                orders += r['data']
            return orders

    def get_one_order(self, order_id: int | str):
        return self.make_request(Method.GET, Route.ORDER.value + f'/{order_id}', params={'include': include_order_fields})

    def new_order(self, data) -> dict:
        return self.make_request(Method.POST, Route.ORDER.value, data=json.dumps(data))

    def get_stages(self):
        return self.make_request(Method.GET, Route.STAGE.value, params={'limit': results_per_page})

    def get_pay_methods(self):
        return self.make_request(Method.GET, Route.PAYMENT_METHODS.value, params={'limit': results_per_page})

    def get_offers(self):
        return self.make_request(Method.GET, Route.OFFERS.value, params={'limit': results_per_page,
                                                                         'include': 'product'})

    def get_order_by_source_uuid(self, source_uuid: str) -> dict:
        orders = self.get_orders(last_orders_amount=1000)
        for order in orders:
            if str(order['source_uuid']) == str(source_uuid):
                return order


