import httpx
from enum import Enum
from typing import Optional


class Route(Enum):
    AUTH = 'auth'
    ORDERS = 'orders/get/'
    PRODUCTS = 'catalog/import/'
    WEBHOOK_SUBSCRIBE = 'hooks/subscribe/'
    WEBHOOK_UNSUBSCRIBE = 'hooks/unSubscribe/'


class HoroshopClient:
    headers = {'Content-type': 'application/json'}
    REQUEST_TIMEOUT = 20

    def __init__(self, shop_url, login, password):
        self.main_url = shop_url.strip('/') + '/api/'
        self.client = httpx.Client()
        self.token = self.get_token(login, password)

    def get_token(self, user, password) -> str:
        r = self.client.post(url=f'{self.main_url}{Route.AUTH.value}', json={'login': user, 'password': password},
                             headers=self.headers, timeout=self.REQUEST_TIMEOUT)
        parsed_data = self.parce_validate_response(r)
        return parsed_data['response']['token']

    def parce_validate_response(self, r: httpx.Response) -> dict:
        print('status_code=', r.status_code)
        print(r.text)
        r.raise_for_status()
        parsed_data = r.json()
        if parsed_data['status'] in ['UNAUTHORIZED', 'AUTHORIZATION_ERROR', 'EXCEPTION',
                                     'ERROR', 'UNDEFINED_FUNCTION', 'HTTP_ERROR']:
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
        return parsed_data

    def get_orders(self, limit: int = None, date_from: str = None, date_to: str = None) -> list:
        data = dict()
        if limit:
            data['limit'] = limit
        if date_from:
            data['from'] = date_from
        if date_to:
            data['to'] = date_to
        parced_data = self.make_request(route=Route.ORDERS, data=data)
        return parced_data['response']['orders'] if parced_data['response'].get('orders') else []

    def import_products(self, products: list) -> dict:
        return self.make_request(route=Route.PRODUCTS, data={'products': products})

    def webhook_subscribe(self, event: str, target_url: str) -> dict:
        """ Event - название события
            order_created - событие срабатывающее при оформлении пользователем заказа либо при создании заказа в админ. панели
            user_signup - событие срабатывающее при регистрации пользователя
            request_call_me - событие срабатывающее при запросе обратного звонка
            Ответ:
            id - идентификатор хука, который необходимо сохранить для отписки от вебхука
            { "id": 1 }"""

        return self.make_request(route=Route.WEBHOOK_SUBSCRIBE, data={'event': event, 'target_url': target_url})

    def webhook_unsubscribe(self, id: int, target_url: str) -> dict:
        """ id - идентификатор подписки полученный в функции hooks/subscribe
            target_url - ссылка на которую отправлялись данные по подписке
            Ответ:
            status - Возвращает OK если подписчик на хук был успешно отписан
            { "status": "OK" }"""

        return self.make_request(route=Route.WEBHOOK_UNSUBSCRIBE, data={'id': id, 'target_url': target_url})

    def close(self):
        self.client.close()  # Закрытие клиента

