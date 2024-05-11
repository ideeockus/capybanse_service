import asyncio
import logging

from parsers.kudago_parser import KudagoParser
from parsers.timepad_parser import TimepadParser
from parsers.utils import get_logger

# logging.basicConfig(
#     level=logging.DEBUG,
#     format='%(asctime)s|%(levelname)1s|%(module)-20s - %(message)s',
#     datefmt='%Y-%m-%d %H:%M:%S',
# )
logger = get_logger('main')


async def run_parsing_service():
    logger.info("Parsing service: starting...")

    # initialize parsers
    kudago_parser = KudagoParser(proxies=[])
    timepad_parser = TimepadParser(proxies=[])
    # networkly_parser = NetworklyParser(proxies=[])

    parsers_tasks = [
        # asyncio.create_task(kudago_parser.run()),
        asyncio.create_task(timepad_parser.run()),
        # timepad_parser.run(),
        # networkly_parser.run(),
    ]

    while parsers_tasks:
        await asyncio.wait(parsers_tasks)

    logger.info("Parsing service: shutdown")


if __name__ == '__main__':
    asyncio.run(run_parsing_service())
