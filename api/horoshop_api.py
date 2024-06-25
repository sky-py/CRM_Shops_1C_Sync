import httpx
from enum import Enum
from typing import Optional


class Route(Enum):
    AUTH = 'auth'
    ORDERS = 'orders/get/'


class HoroshopClient:
    main_url = 'http://shop233144.horoshop.ua/api/'
    headers = {'Content-type': 'application/json'}
    REQUEST_TIMEOUT = 20

    def __init__(self, login, password):
        self.client = httpx.Client()
        self.token = self.get_token(login, password)

    def get_token(self, user, password) -> str:
        r = self.client.post(url=f'{self.main_url}{Route.AUTH.value}', json={'login': user, 'password': password},
                             headers=self.headers, timeout=self.REQUEST_TIMEOUT)
        parsed_data = self.parce_validate_response(r)
        return parsed_data['response']['token']

    def parce_validate_response(self, r: httpx.Response) -> dict:
        # print('status_code=', r.status_code)
        # print(r.text)
        r.raise_for_status()
        parsed_data = r.json()
        if parsed_data['status'] != 'OK':
            raise Exception(f'{parsed_data["status"]} '
                            f'{parsed_data.get('response', '') and parsed_data.get('response').get('message', '')} '
                            f'{parsed_data.get('response', '') and parsed_data.get('response').get('code', '')}'
                            )
        return parsed_data

    def make_request(self, route: Route, data: Optional[dict] = None) -> dict:
        if data is None:
            data = dict()
        data['token'] = self.token
        r = self.client.post(url=f'{self.main_url}{route.value}',
                             json=data,
                             headers=self.headers, timeout=self.REQUEST_TIMEOUT)
        parsed_data = self.parce_validate_response(r)
        return parsed_data['response']

    def get_orders(self, limit: int = None, date_from: str = None, date_to: str = None) -> list:
        data = dict()
        if limit:
            data['limit'] = limit
        if date_from:
            data['from'] = date_from
        if date_to:
            data['to'] = date_to
        response = self.make_request(route=Route.ORDERS, data=data)
        return response['orders'] if response.get('orders') else []

    def close(self):
        self.client.close()  # Закрытие клиента

