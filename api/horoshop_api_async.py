import httpx
from enum import Enum
from typing import Optional


class Route(Enum):
    AUTH = 'auth'
    ORDERS = 'orders/get/'
    PRODUCTS = 'catalog/import/'


class HoroshopClient:
    main_url = 'http://shop233144.horoshop.ua/api/'
    headers = {'Content-type': 'application/json'}
    REQUEST_TIMEOUT = 20

    def __init__(self, login, password):
        self.client = httpx.AsyncClient()
        self.token = self.get_token(login, password)

    def get_token(self, user, password) -> str:
        sync_client = httpx.Client()
        r = sync_client.post(url=f'{self.main_url}{Route.AUTH.value}', json={'login': user, 'password': password},
                             headers=self.headers, timeout=self.REQUEST_TIMEOUT)
        parsed_data = self.parce_validate_response(r)
        return parsed_data['response']['token']

    def parce_validate_response(self, r: httpx.Response) -> dict:
        # print('status_code=', r.status_code)
        # print(r.text)
        r.raise_for_status()
        parsed_data = r.json()
        if parsed_data['status'] in ['UNAUTHORIZED', 'AUTHORIZATION_ERROR', 'EXCEPTION',
                                     'ERROR', 'UNDEFINED_FUNCTION', 'HTTP_ERROR']:
            raise Exception(f'{parsed_data["status"]} '
                            f'{parsed_data.get('response', '') and parsed_data.get('response').get('message', '')} '
                            f'{parsed_data.get('response', '') and parsed_data.get('response').get('code', '')}'
                            )
        return parsed_data

    async def make_request(self, route: Route, data: Optional[dict] = None) -> dict:
        if data is None:
            data = dict()
        data['token'] = self.token
        r = await self.client.post(url=f'{self.main_url}{route.value}',
                             json=data,
                             headers=self.headers, timeout=self.REQUEST_TIMEOUT)
        parsed_data = self.parce_validate_response(r)
        return parsed_data

    async def get_orders(self, limit: int = None, date_from: str = None, date_to: str = None) -> list:
        data = dict()
        if limit:
            data['limit'] = limit
        if date_from:
            data['from'] = date_from
        if date_to:
            data['to'] = date_to
        parced_data = await self.make_request(route=Route.ORDERS, data=data)
        return parced_data['response']['orders'] if parced_data['response'].get('orders') else []

    async def import_products(self, products: list) -> dict:
        return await self.make_request(route=Route.PRODUCTS, data={'products': products})

    async def close(self):
        await self.client.aclose()  # Закрытие клиента

