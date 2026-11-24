'''Short links on TinyURL: a long link in, a short link out.

    from tinyurl import shorten
    short = shorten('https://ukrstil.com/ua/p1570811216-pedikyurnoe-spa-kreslo.html')   # https://tinyurl.com/xxxxxxx

Async code: `await ashorten(url)`. Command line: `python tinyurl.py <long link> [--alias name]`.

TinyURL API v2 (https://tinyurl.com/app/dev): POST https://api.tinyurl.com/create with the account token
TINY_URL_API_KEY from C:\\etc\\env\\other.env. Every call makes a new short link (with a random name unless `alias` is
given) in the TinyURL account of the token, so call it once per long link and keep the result. The token is never
printed or put into error texts.

Shared module: a project that must not depend on outside folders copies this file into itself; others may do
`sys.path.insert(0, r'C:\\Scripts\\Tools')`. Needs httpx and python-dotenv.
'''
import argparse
import asyncio
import os
import time
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv

API_URL = 'https://api.tinyurl.com/create'
ENV_FILE = r'C:\etc\env\other.env'
TIMEOUT = 30
MAX_RETRIES = 3
RETRY_SLEEP_SECONDS = 5
# Answers after which the link surely was not made, so a repeat makes no duplicate; a 5xx may come after the link was
# made, then a repeat gives a second short link to the same page (harmless, only an extra link in the account).
RETRY_STATUSES = {429, 500, 502, 503, 504}


class TinyURLError(RuntimeError):
    '''TinyURL refused or answered something unexpected.'''


def _token() -> str:
    load_dotenv(ENV_FILE)
    token = os.getenv('TINY_URL_API_KEY')
    if not token:
        raise TinyURLError(f'TINY_URL_API_KEY is not set (expected in {ENV_FILE}).')
    return token


def _request(long_url: str, alias: str | None, tags: list[str] | None, description: str | None) -> dict:
    long_url = long_url.strip()
    parts = urlsplit(long_url)
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        raise ValueError(f'Not a full web link: {long_url!r} (needs http:// or https://).')
    payload = {'url': long_url, 'domain': 'tinyurl.com'}
    if alias:
        payload['alias'] = alias
    if tags:
        payload['tags'] = tags
    if description:
        payload['description'] = description
    return payload


def _headers() -> dict:
    return {'Authorization': f'Bearer {_token()}', 'Accept': 'application/json'}


def _result(r: httpx.Response) -> str:
    try:
        answer = r.json()
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        r.raise_for_status()
        raise TinyURLError(f'TinyURL answered HTTP {r.status_code} without JSON.')
    data = answer.get('data') if isinstance(answer.get('data'), dict) else {}
    tiny_url = data.get('tiny_url')
    if r.status_code != 200 or answer.get('code') != 0 or not isinstance(tiny_url, str):
        raise TinyURLError(f'TinyURL refused (HTTP {r.status_code}, code {answer.get("code")}): {answer.get("errors")}')
    return tiny_url


def _sleep_seconds(r: httpx.Response | None) -> int:
    try:
        return int(r.headers.get('Retry-After')) if r is not None else RETRY_SLEEP_SECONDS
    except (TypeError, ValueError):
        return RETRY_SLEEP_SECONDS


def shorten(long_url: str, alias: str | None = None, tags: list[str] | None = None, description: str | None = None) -> str:
    '''Make a new TinyURL for `long_url` and return it, e.g. "https://tinyurl.com/2p8x7k3a".

    `alias` asks for a readable name (5-30 characters; TinyURL refuses a taken one), `tags` and `description` are seen
    in the TinyURL account only.
    '''
    payload = _request(long_url, alias, tags, description)
    with httpx.Client(timeout=TIMEOUT) as client:
        for attempt in range(MAX_RETRIES + 1):
            try:
                r = client.post(API_URL, json=payload, headers=_headers())
            except (httpx.ConnectError, httpx.ConnectTimeout) as error:
                if attempt == MAX_RETRIES:
                    raise TinyURLError(f'No connection to TinyURL: {error!r}') from error
                time.sleep(RETRY_SLEEP_SECONDS)
                continue
            if r.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                time.sleep(_sleep_seconds(r))
                continue
            return _result(r)
    raise TinyURLError('TinyURL: no answer after retries.')


async def ashorten(
    long_url: str, alias: str | None = None, tags: list[str] | None = None, description: str | None = None
) -> str:
    '''The same as `shorten`, for async code.'''
    payload = _request(long_url, alias, tags, description)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for attempt in range(MAX_RETRIES + 1):
            try:
                r = await client.post(API_URL, json=payload, headers=_headers())
            except (httpx.ConnectError, httpx.ConnectTimeout) as error:
                if attempt == MAX_RETRIES:
                    raise TinyURLError(f'No connection to TinyURL: {error!r}') from error
                await asyncio.sleep(RETRY_SLEEP_SECONDS)
                continue
            if r.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                await asyncio.sleep(_sleep_seconds(r))
                continue
            return _result(r)
    raise TinyURLError('TinyURL: no answer after retries.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Make a TinyURL short link for a long link.')
    parser.add_argument('url', help='the long link, with http:// or https://')
    parser.add_argument('--alias', help='readable name of the short link, 5-30 characters')
    args = parser.parse_args()
    print(shorten(args.url, alias=args.alias))
