import httpx
import json

REQUEST_TIMEOUT = 20
results_per_page = 50
main_url = 'https://my.prom.ua/api/v1'


class PromClient:
    def __init__(self, token):
        self.token = token
        self.client = httpx.AsyncClient()
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-type': 'application/json'
        }

    async def make_request(self, url, method='GET', params=None, data=None, tries=1):
        match method:
            case 'GET': r = await self.client.get(url=f'{main_url}{url}', params=params, headers=self.headers, timeout=REQUEST_TIMEOUT)
            case 'POST': r = await self.client.post(url=f'{main_url}{url}', data=data, headers=self.headers, timeout=REQUEST_TIMEOUT)
            case 'PUT': r = await self.client.put(url=f'{main_url}{url}', data=data, headers=self.headers, timeout=REQUEST_TIMEOUT)
            case _: raise Exception('Unknown method')
        return r

    async def get_order(self, order_id: int) -> httpx.Response:
        return await self.make_request(f'/orders/{order_id}')

    async def get_orders(self, limit: int = None,
                         last_modified_from: str = None, last_modified_to: str = None,
                         date_from: str = None, date_to: str = None) -> httpx.Response:
        """
        :param limit: Обмеження кількості замовлень у відповіді.
        :param last_modified_from: Запит замовлень, змінених після вказаної дати. Приклад - 2015-04-28T12:50:34
        :param last_modified_to: Запит замовлень, змінених до вказаної дати. Приклад - 2015-04-28T12:50:34
        :param date_from: Запит замовлень, створених до вказаної дати. Приклад - 2015-04-28T12:50:34
        :param date_to: Запит замовлень, створених до вказаної дати. Приклад - 2015-04-28T12:50:34
        """
        params = dict()
        if limit:
            params['limit'] = limit
        if last_modified_from:
            params['last_modified_from'] = last_modified_from
        if last_modified_to:
            params['last_modified_to'] = last_modified_to
        if date_from:
            params['date_from'] = date_from
        if date_to:
            params['date_to'] = date_to

        return await self.make_request(url=f'/orders/list', params=params)

    async def get_products(self, limit=None) -> httpx.Response:
        limit = f'?limit={limit}' if limit else ""
        return await self.make_request(f'/products/list{limit}')    # ?group_id=1780775

    async def import_products(self, products) -> httpx.Response:
        return await self.make_request('/products/edit', method='POST', data=json.dumps(products))

    async def put_translation(self, id: int, lang='uk',
                              name: str = None, description: str = None, keywords: str = None) -> httpx.Response:
        data = {'product_id': id, 'lang': lang}
        if name:
            data['name'] = name
        if description:
            data['description'] = description
        if keywords:
            data['keywords'] = keywords
        return await self.make_request('/products/translation', method='PUT', data=json.dumps(data))

    async def get_product(self, product_id) -> httpx.Response:
        return await self.make_request(f'/products/{product_id}')

    async def get_messages(self, limit=results_per_page) -> httpx.Response:
        return await self.make_request(f'/messages/list?limit={limit}')

