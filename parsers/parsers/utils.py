import typing as t
from datetime import datetime


def retry(times: int, exceptions: t.Collection[Exception] = (Exception,)):
    def decorator(func):
        def new_func(*args, **kwargs):
            attempt = 0
            while attempt < times:
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    print(
                        'Exception thrown when attempting to run %s, attempt '
                        '%d of %d' % (func, attempt, times)
                    )
                    attempt += 1
            return func(*args, **kwargs)

        return new_func

    return decorator


def get_today_dt() -> float:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def get_service_id(service_name: str, inner_id: str) -> str:
    return f'{service_name}_{inner_id}'
