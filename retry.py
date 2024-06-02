import time
from typing import Callable
import asyncio
from functools import wraps


def retry(stop_after_delay=300, max_delay=20):
    def decorator(func: Callable) -> Callable:
        if not asyncio.iscoroutinefunction(func):
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start = time.time()
                delay = 1
                while True:
                    try:
                        result = func(*args, **kwargs)
                    except Exception as e:
                        if time.time() - start > stop_after_delay:
                            raise
                        else:
                            print(f"{type(e).__name__} Error: {e}")
                            time.sleep(delay)
                            delay = min(delay * 2, max_delay)
                    else:
                        return result

            return sync_wrapper

        else:
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start = time.time()
                delay = 1
                while True:
                    try:
                        result = await func(*args, **kwargs)
                    except Exception as e:
                        if time.time() - start > stop_after_delay:
                            raise
                        else:
                            print(f"{type(e).__name__} Error: {e}")
                            await asyncio.sleep(delay)
                            delay = min(delay * 2, max_delay)
                    else:
                        return result

            return async_wrapper

    return decorator

