import asyncio
import json
import typing as t

import aio_pika

from common.clients import PostgresDB
from common.clients import VectorDB
from common.utils import get_logger
from event_handler.config import RABBITMQ_HOST
from event_handler.config import RABBITMQ_PASSWORD
from event_handler.config import RABBITMQ_USER
from recommendation_service.config import POSTGRES_DB
from recommendation_service.config import POSTGRES_HOST
from recommendation_service.config import POSTGRES_PASSWORD
from recommendation_service.config import POSTGRES_PORT
from recommendation_service.config import POSTGRES_USER
from recommendation_service.config import QDRANT_HOST
from recommendation_service.config import QDRANT_PORT
from recommendation_service.rs import get_recommendation_for_user

logger = get_logger('main')

RPC_QUEUE_RECOMMENDATION_BY_USER = 'recommendations.requests.by_user'
RPC_QUEUE_SET_USER_DESCRIPTION = 'resonanse_api.requests.set_user_description'

QueueHandler = t.Callable[
    [
        aio_pika.abc.AbstractIncomingMessage,
        aio_pika.exchange.AbstractExchange,
    ],
    t.Awaitable[None]
]


async def rpc_get_recommendation_by_user(
        message: aio_pika.abc.AbstractIncomingMessage,
        exchange: aio_pika.exchange.AbstractExchange,
) -> None:
    async with message.process(requeue=False):
        if message.reply_to is None:
            logger.warning('message.reply_to is', message.reply_to)
            return

        req_json = json.loads(message.body)
        user_id = req_json['user_id']

        response = await get_recommendation_for_user(user_id)
        resp_json = json.dumps(response)

        logger.debug('Send response: rpc_get_recommendation_by_user')
        await exchange.publish(
            aio_pika.Message(
                body=resp_json.encode(),
                correlation_id=message.correlation_id,
            ),
            routing_key=message.reply_to,
        )


async def rpc_set_user_description(
        message: aio_pika.abc.AbstractIncomingMessage,
        exchange: aio_pika.exchange.AbstractExchange,
) -> None:
    async with message.process(requeue=False):
        if message.reply_to is None:
            logger.warning('message.reply_to is', message.reply_to)
            return

        req_json = json.loads(message.body)
        user_id: int = req_json['user_id']
        user_description: str = req_json['description']

        # save to postgres
        postgres_client = await PostgresDB.get_client(
            pg_user=POSTGRES_USER,
            pg_password=POSTGRES_PASSWORD,
            pg_host=POSTGRES_HOST,
            pg_port=POSTGRES_PORT,
            pg_db=POSTGRES_DB,
        )
        status = await postgres_client.set_user_description(
            user_id,
            user_description,
        )

        # save to vector db
        vectordb_client = await VectorDB.get_client(
            QDRANT_HOST,
            QDRANT_PORT,
        )
        status &= await vectordb_client.add_user_description(
            user_id,
            user_description,
        )

        resp_json = json.dumps({'status': status})

        logger.debug('Send response: rpc_set_user_description')
        await exchange.publish(
            aio_pika.Message(
                body=resp_json.encode(),
                correlation_id=message.correlation_id,
            ),
            routing_key=message.reply_to,
        )


async def run_queue_handler(
        queue: aio_pika.queue.AbstractQueue,
        resp_exchange: aio_pika.exchange.AbstractExchange,
        handler: QueueHandler,
):
    async with queue.iterator() as qiterator:
        message: aio_pika.message.AbstractIncomingMessage
    async for message in qiterator:
        try:
            await handler(
                message,
                resp_exchange,
            )
        except Exception as err:
            logger.exception("Processing error %s for message %r", err, message)


RPC_QUEUE_HANDLERS = {
    RPC_QUEUE_RECOMMENDATION_BY_USER: rpc_get_recommendation_by_user,
    RPC_QUEUE_SET_USER_DESCRIPTION: rpc_set_user_description,
}


async def main() -> None:
    connection = await aio_pika.connect_robust(
        host=RABBITMQ_HOST,
        login=RABBITMQ_USER,
        password=RABBITMQ_PASSWORD,
    )

    channel = await connection.channel()
    exchange = channel.default_exchange
    logger.info('Starting recommendation service RPC')

    # it seems that big prefetch count depletes db connection pool
    await channel.set_qos(prefetch_count=10)

    queue_handling_tasks = []
    for (mq_queue_name, handler) in RPC_QUEUE_HANDLERS.items():
        queue = await channel.declare_queue(mq_queue_name, durable=True)
        queue_handling_tasks.append(
            asyncio.create_task(run_queue_handler(
                queue,
                exchange,
                handler,
            ))
        )

    while queue_handling_tasks:
        await asyncio.wait(queue_handling_tasks)


if __name__ == "__main__":
    asyncio.run(main())
