"""
Consume events from queues, vectorize and save to databases
"""
import asyncio

import aio_pika

from common.clients.posgres_client import PostgresDB
from common.clients.vectordb_client import VectorDB
from common.models import EventData
from common.utils import get_logger
from config import POSTGRES_DB
from config import POSTGRES_HOST
from config import POSTGRES_PASSWORD
from config import POSTGRES_PORT
from config import POSTGRES_USER
from config import QDRANT_HOST
from config import QDRANT_PORT
from config import RABBITMQ_HOST
from config import RABBITMQ_PASSWORD
from config import RABBITMQ_USER

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
    event.description = event.description.strip()

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
    # init qdrant before message handling: issues with concurrent collection extistance check
    await VectorDB.get_client(
        qdrant_host=QDRANT_HOST,
        qdrant_port=int(QDRANT_PORT),
    )

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
