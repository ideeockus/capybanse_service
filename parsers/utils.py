import logging
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


def get_logger(module_name: str) -> logging.Logger:
    logger = logging.getLogger(module_name)
    logger.setLevel(logging.DEBUG)

    log_handler = logging.StreamHandler()
    log_formatter = logging.Formatter(
        fmt='%(asctime)s|%(levelname)1s|%(name)-10s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    log_handler.setLevel(logging.DEBUG)
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)

    return logger


def get_today_dt() -> float:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
