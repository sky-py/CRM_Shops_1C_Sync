import json
from datetime import datetime, timedelta
from typing import Optional
import httpx
import asyncio

REQUEST_TIMEOUT = 20
PROM_OUTPUT_LIMIT = 100
INITIAL_DAYS_INTERVAL_FOR_ORDERS = 30
main_url = 'https://my.prom.ua/api/v1'


def get_timestamp(dt: datetime) -> str:
    # return dt.strftime('%Y-%m-%dT%H:%M:%S')
    return dt.isoformat(timespec='seconds')


class PromClient:
    def __init__(self, token):
        self.token = token
        self.client = httpx.AsyncClient()
        self.headers = {'Authorization': f'Bearer {self.token}', 'Content-type': 'application/json'}

    async def make_request(self, url, method='GET', params=None, data=None, tries=1):
        match method:
            case 'GET':
                r = await self.client.get(
                    url=f'{main_url}{url}', params=params, headers=self.headers, timeout=REQUEST_TIMEOUT
                )
            case 'POST':
                r = await self.client.post(
                    url=f'{main_url}{url}', data=data, headers=self.headers, timeout=REQUEST_TIMEOUT
                )
            case 'PUT':
                r = await self.client.put(
                    url=f'{main_url}{url}', data=data, headers=self.headers, timeout=REQUEST_TIMEOUT
                )
            case _:
                raise Exception('Unknown method')
        r.raise_for_status()
        return r

    async def get_order(self, order_id: int) -> httpx.Response:
        return await self.make_request(f'/orders/{order_id}')

    async def get_orders(
        self,
        limit: int = PROM_OUTPUT_LIMIT,
        last_modified_from: Optional[datetime] = None,
        last_modified_to: Optional[datetime] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list:
        """
        :param limit: Обмеження кількості замовлень у відповіді.
        :param last_modified_from: Запит замовлень, змінених після вказаної дати. 
        :param last_modified_to: Запит замовлень, змінених до вказаної дати. 
        :param date_from: Запит замовлень, створених до вказаної дати. 
        :param date_to: Запит замовлень, створених до вказаної дати. 
        Можна використовувати тільки один з параметрів date_from, date_to або last_modified_from 
        """
        orders = []
        if date_from and date_to or last_modified_from and last_modified_to:
            d_from = date_from if date_from and date_to else last_modified_from
            d_to = date_to if date_from and date_to else last_modified_to
            key_from = 'date_from' if date_from else 'last_modified_from'
            key_to = 'date_to' if date_to else 'last_modified_to'
            days_interval_adapted = INITIAL_DAYS_INTERVAL_FOR_ORDERS
            while d_from < d_to:
                params = {}
                params['limit'] = limit
                params[key_from] = get_timestamp(d_from)
                d_to_intermediate = min(d_to, d_from + timedelta(days=days_interval_adapted))
                params[key_to] = get_timestamp(d_to_intermediate)
                r = await self.make_request(url='/orders/list', params=params)
                chunk_orders = r.json()['orders']
                if len(chunk_orders) >= PROM_OUTPUT_LIMIT:
                    days_interval_adapted //= 1.5
                    continue
                print(f'Got {len(chunk_orders)} orders')
                orders.extend(chunk_orders)
                d_from = d_to_intermediate
                await asyncio.sleep(2)
        else:
            params = {}
            params['limit'] = limit
            if last_modified_from:
                params['last_modified_from'] = get_timestamp(last_modified_from)
            if last_modified_to:
                params['last_modified_to'] = get_timestamp(last_modified_to)
            if date_from:
                params['date_from'] = get_timestamp(date_from)
            if date_to:
                params['date_to'] = get_timestamp(date_to)

            r = await self.make_request(url='/orders/list', params=params)
            orders = r.json()['orders']

        return orders

    async def get_products(self, limit=None) -> httpx.Response:
        limit = f'?limit={limit}' if limit else ''
        return await self.make_request(f'/products/list{limit}')  # ?group_id=1780775

    async def import_products(self, products) -> httpx.Response:
        return await self.make_request('/products/edit', method='POST', data=json.dumps(products))

    async def put_translation(
        self, id: int, lang='uk', name: str = None, description: str = None, keywords: str = None
    ) -> httpx.Response:
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

    async def get_messages(self, limit=PROM_OUTPUT_LIMIT) -> httpx.Response:
        return await self.make_request(f'/messages/list?limit={limit}')
    
    async def get_chat_messages(self, limit=PROM_OUTPUT_LIMIT) -> httpx.Response:
        return await self.make_request(f'/chat/messages_history?limit={limit}')
