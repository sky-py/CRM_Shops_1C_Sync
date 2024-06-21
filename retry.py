import time
import asyncio
from functools import wraps


def retry(stop_after_delay=None, max_tries=None, max_delay=20):
    def decorator(func):
        if not asyncio.iscoroutinefunction(func):
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                nonlocal max_tries
                if not stop_after_delay and not max_tries:
                    max_tries = 1
                start = time.time()
                delay = 1
                tries = 0
                while True:
                    try:
                        result = func(*args, **kwargs)
                    except Exception as e:
                        if (stop_after_delay and time.time() - start > stop_after_delay) or (max_tries and tries >= max_tries):
                            raise
                        else:
                            print(f"{type(e).__name__} Error: {e}")
                            time.sleep(delay)
                            delay = min(delay * 2, max_delay)
                            tries += 1
                    else:
                        return result

            return sync_wrapper

        else:
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                nonlocal max_tries
                if not stop_after_delay and not max_tries:
                    max_tries = 1
                start = time.time()
                delay = 1
                tries = 0
                while True:
                    try:
                        result = await func(*args, **kwargs)
                    except Exception as e:
                        if (stop_after_delay and time.time() - start > stop_after_delay) or (max_tries and tries >= max_tries):
                            raise
                        else:
                            print(f"{type(e).__name__} Error: {e}")
                            await asyncio.sleep(delay)
                            delay = min(delay * 2, max_delay)
                            tries += 1
                    else:
                        return result

            return async_wrapper

    return decorator

