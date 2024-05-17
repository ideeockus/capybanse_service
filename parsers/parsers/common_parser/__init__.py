import asyncio
import time
import typing as t
from abc import ABC
from abc import abstractmethod
from datetime import datetime

import aio_pika

from common.models import EventData
from parsers.config import RABBITMQ_HOST
from common.utils import get_logger
from parsers.config import RABBITMQ_PASSWORD
from parsers.config import RABBITMQ_USER

logger = get_logger('common_parser')
PARSING_INTERVAL = 3600 * 3  # 3 hours


class EventsParser(ABC):
    def __init__(self, proxies: list[str]):
        self.proxies = proxies

    @staticmethod
    @abstractmethod
    def parser_name() -> str:
        ...

    @staticmethod
    def get_httpx_client_params() -> dict:
        params = {
            # 'proxy': 'socks5://user:pass@host:port'
        }

        return params

    @abstractmethod
    async def _get_next_events(self) -> t.Iterable[EventData] | None:
        ...

    async def run_parsing(self):
        MQ_EXCHANGE_NAME = 'events_parsing'
        mq_queue_name = f'events.{self.parser_name()}'

        connection = await aio_pika.connect(
            host=RABBITMQ_HOST,
            # login=RABBITMQ_USER,
            # password=RABBITMQ_PASSWORD,
        )

        channel = await connection.channel()

        exchange = await channel.declare_exchange(MQ_EXCHANGE_NAME, type=aio_pika.ExchangeType.DIRECT)
        queue = await channel.declare_queue(mq_queue_name, durable=True)
        await queue.bind(exchange, mq_queue_name)

        while events := await self._get_next_events():
            for event_data in events:
                event_data_json = event_data.json()
                logger.debug('Sending to queue %s: %s', self.parser_name(), event_data_json)
                await exchange.publish(
                    message=aio_pika.Message(
                        body=event_data_json.encode(),
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key=mq_queue_name,
                )

        await connection.close()

    async def run(self):
        while True:
            run_dt = datetime.now()

            try:
                await self.run_parsing()
            except (ConnectionRefusedError, aio_pika.AMQPException) as err:
                logger.exception('Connection error', err)
                time.sleep(10)
            except Exception as e:
                logger.exception('Exception on parsing: %s', e)

                elapsed_seconds = (run_dt - datetime.now()).seconds
                logger.debug('Elapsed seconds %s', elapsed_seconds)

                if elapsed_seconds < PARSING_INTERVAL:
                    seconds_to_sleep = PARSING_INTERVAL - elapsed_seconds
                    logger.info('Parsing failed. Sleeping %s seconds', seconds_to_sleep)
                    await asyncio.sleep(seconds_to_sleep)
                continue

            logger.info(
                'Parsing done for %s. Sleeping %s seconds',
                self.parser_name(),
                PARSING_INTERVAL,
            )
            await asyncio.sleep(PARSING_INTERVAL)
