import time
from enum import StrEnum
import requests

REQUEST_TIMEOUT = 20
REQUESTS_EXCEEDED_TIME_TO_SLEEP = 20
RESULTS_PER_PAGE = 50
INCLUDE_ORDER_FIELDS = 'buyer,manager,products.offer,shipping.deliveryService,custom_fields,payments'
INCLUDE_LEAD_FIELDS = 'contact.client,products,manager,status,custom_fields,payments'


class Method(StrEnum):
    GET = 'get'
    POST = 'post'
    PUT = 'put'


class Route(StrEnum):
    ORDER = 'order'
    ORDER_STAGES = 'order/status'
    PAYMENT_METHODS = 'order/payment-method'
    OFFERS = 'offers'
    PRODUCTS = 'products'
    LEEDS = 'pipelines/cards'
    LEED_STAGES = 'pipelines/{pipelineId}/statuses'


class KeyCRM:
    main_url = 'https://openapi.keycrm.app/v1'

    def __init__(self, api_key):
        self.headers = {
            'Content-type': 'application/json',
            'Accept': 'application/json',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Authorization': f'Bearer {api_key}',
        }

    def parse_and_validate_response(self, r: requests.Response) -> dict:
        r.raise_for_status()
        remaining_limits = r.headers.get('X-Ratelimit-Remaining')
        print(f'Remaining limits: {remaining_limits if remaining_limits else 'Not found'}')
        if remaining_limits:
            if int(remaining_limits) < 20:
                print(f'Exceeded limits, waiting {REQUESTS_EXCEEDED_TIME_TO_SLEEP} sec...')
                time.sleep(REQUESTS_EXCEEDED_TIME_TO_SLEEP)
        return r.json()

    def make_request(self, method: Method, route: str, params=None, json_data=None) -> dict:
        url = f'{self.main_url}/{route}'
        match method:
            case Method.GET:
                r = requests.get(url=url, headers=self.headers, params=params, timeout=REQUEST_TIMEOUT)
            case Method.PUT:
                r = requests.put(url=url, headers=self.headers, json=json_data, timeout=REQUEST_TIMEOUT)
            case Method.POST:
                r = requests.post(url=url, headers=self.headers, json=json_data, timeout=REQUEST_TIMEOUT)
            case _:
                raise Exception('Unknown method')

        return self.parse_and_validate_response(r)

    def get_orders(self, last_orders_amount=RESULTS_PER_PAGE, filter: dict = None) -> list[dict]:
        """
        Returns list of orders dicts
        :param last_orders_amount: 0 meens ALL
        :param filter: dictionary of filters
        :return: list of orders dicts
        """
        params = {'limit': RESULTS_PER_PAGE, 'include': INCLUDE_ORDER_FIELDS}

        if filter is not None:
            for key, value in filter.items():
                params[f'filter[{key}]'] = value

        data = self.make_request(Method.GET, Route.ORDER, params=params)

        if last_orders_amount == 0:
            pages = data['last_page']
        else:
            pages = last_orders_amount // RESULTS_PER_PAGE + (last_orders_amount % RESULTS_PER_PAGE > 0)

        orders = data['data']
        if pages == 1:  # all orders on one page, no need to fetch more pages
            return orders
        else:
            for page in range(2, pages + 1):
                params['page'] = page
                data = self.make_request(Method.GET, Route.ORDER, params=params)
                orders += data['data']
            return orders

    def get_order(self, order_id: int | str) -> dict:
        return self.make_request(Method.GET, f'{Route.ORDER}/{order_id}', params={'include': INCLUDE_ORDER_FIELDS})

    def new_order(self, data: dict) -> dict:
        return self.make_request(Method.POST, Route.ORDER, json_data=data)

    def update_order(self, order_id: int | str, data: dict) -> dict:
        return self.make_request(Method.PUT, f'{Route.ORDER}/{order_id}', json_data=data)

    def get_lead(self, lead_id: int | str) -> dict:
        return self.make_request(Method.GET, f'{Route.LEEDS}/{lead_id}', params={'include': INCLUDE_LEAD_FIELDS})
    
    def get_lead_stages(self, pipeline_id) -> dict:
        return self.make_request(Method.GET, Route.LEED_STAGES.format(pipelineId=pipeline_id), params={'limit': RESULTS_PER_PAGE})

    def get_order_stages(self) -> dict:
        return self.make_request(Method.GET, Route.ORDER_STAGES, params={'limit': RESULTS_PER_PAGE})

    def get_pay_methods(self) -> dict:
        return self.make_request(Method.GET, Route.PAYMENT_METHODS, params={'limit': RESULTS_PER_PAGE})

    def get_offers(self) -> dict:
        return self.make_request(Method.GET, Route.OFFERS, params={'limit': RESULTS_PER_PAGE, 'include': 'product'})

    def get_product(self, product_id: int | str) -> dict:
        return self.make_request(Method.GET, f'{Route.PRODUCTS}/{product_id}')

    def update_product(self, product_id: int | str, data: dict) -> dict:
        return self.make_request(Method.PUT, f'{Route.PRODUCTS}/{product_id}', json_data=data)

    def get_order_by_source_uuid(self, source_uuid: str) -> dict:
        orders = self.get_orders(last_orders_amount=1000)
        for order in orders:
            if str(order['source_uuid']) == str(source_uuid):
                return order
