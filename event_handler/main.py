"""
Consume events from queues, vectorize and save to databases
"""
import asyncio
import time

import aio_pika

from common.clients import PostgresDB
from common.clients import VectorDB
from common.models import EventData
from common.utils import get_logger
from event_handler.config import POSTGRES_DB
from event_handler.config import POSTGRES_HOST
from event_handler.config import POSTGRES_PASSWORD
from event_handler.config import POSTGRES_PORT
from event_handler.config import POSTGRES_USER
from event_handler.config import QDRANT_HOST
from event_handler.config import QDRANT_PORT
from event_handler.config import RABBITMQ_HOST
from event_handler.config import RABBITMQ_PASSWORD
from event_handler.config import RABBITMQ_USER

logger = get_logger('main')

EVENTS_QUEUES = [
    'events.kudago',
    'events.timepad',
    'events.resonanse',
    'events.networkly',
]


async def handle_event_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    postgres_client = await PostgresDB.get_client(
        pg_user=POSTGRES_USER,
        pg_password=POSTGRES_PASSWORD,
        pg_host=POSTGRES_HOST,
        pg_port=POSTGRES_PORT,
        pg_db=POSTGRES_DB,
    )

    event = EventData.model_validate_json(message.body)

    saved_to_pg = await postgres_client.add_event(event)
    if saved_to_pg:
        # then save to vector db too
        vectordb_client = await VectorDB.get_client(
            qdrant_host=QDRANT_HOST,
            qdrant_port=int(QDRANT_PORT),
        )
        await vectordb_client.add_event(event)

    logger.debug('message %s for event %s handled', message.message_id, event.service_id)
    await message.ack()


async def main() -> None:
    connection = await aio_pika.connect_robust(
        host=RABBITMQ_HOST,
        login=RABBITMQ_USER,
        password=RABBITMQ_PASSWORD,
    )

    channel = await connection.channel()
    # it seems that big prefetch count depletes db connection pool
    await channel.set_qos(prefetch_count=10)
    for mq_queue_name in EVENTS_QUEUES:
        queue = await channel.declare_queue(mq_queue_name, durable=True)
        await queue.consume(handle_event_message)

    try:
        # Wait until terminate
        await asyncio.Future()
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
