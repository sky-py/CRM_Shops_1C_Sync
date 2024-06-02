import requests
import json

REQUEST_TIMEOUT = 20
results_per_page = 50
tries_per_request = 20
pause_between_tries = 20
main_url = 'https://my.prom.ua/api/v1'


class PromClient:
    def __init__(self, token):
        self.token = token
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-type': 'application/json'
        }

    def make_request(self, url, method='GET', data=None) -> requests.Response:
        url = f'{main_url}{url}'
        # print(data)
        if method == 'GET':
            r = requests.get(url=url, headers=self.headers)
        elif method == 'POST':
            r = requests.post(url=url, data=data, headers=self.headers)
        elif method == 'PUT':
            r = requests.put(url=url, data=data, headers=self.headers)
        else:
            raise Exception('Unknown method')
        # print('status_code=', r.status_code)
        # print(r.text)
        return r

    def get_orders_list(self, limit=None):
        limit = f'?limit={limit}' if limit else ""
        # return requests.get(url=f'{constants.prom_url}/orders/list{limit}', headers=self.headers).json()
        return self.make_request(f'/orders/list{limit}')

    def get_product_list(self, limit=None):
        limit = f'?limit={limit}' if limit else ""
        return self.make_request(f'/products/list{limit}')    # ?group_id=1780775

    def push_products(self, products: list[dict]):
        return self.make_request('/products/edit', method='POST', data=json.dumps(products))

    def put_translation(self, id: int, lang='uk', name: str = None, description: str = None, keywords: str = None):
        data = {'product_id': id, 'lang': lang}
        if name:
            data['name'] = name
        if description:
            data['description'] = description
        if keywords:
            data['keywords'] = keywords
        return self.make_request('/products/translation', method='PUT', data=json.dumps(data))

    def get_product(self, product_id: int):
        return self.make_request(f'/products/{product_id}')


