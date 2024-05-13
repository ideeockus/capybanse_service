import json
import typing as t

import psycopg
from psycopg_pool import AsyncConnectionPool

from common.clients import CREATE_RESONANSE_EVENTS_TABLE
from common.clients import CREATE_RESONANSE_USERS_TABLE
from common.models import EventData
from common.models import EventSource
from common.models import Image
from common.models import Price
from common.models import Venue
from common.utils import get_logger

logger = get_logger('postgres_client')


class PostgresDB:
    _pool: AsyncConnectionPool | None = None

    @classmethod
    async def get_client(
            cls,
            pg_user,
            pg_password,
            pg_host,
            pg_port,
            pg_db,
    ) -> t.Self:
        db_url = f'postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}'

        if cls._pool is None:
            cls._pool = AsyncConnectionPool(
                db_url,
                open=False,
            )
            await cls._pool.open()

        # init db schemas
        async with cls._pool.connection() as aconn:
            async with aconn.cursor() as acur:
                await acur.execute(CREATE_RESONANSE_EVENTS_TABLE)
                await acur.execute(CREATE_RESONANSE_USERS_TABLE)

        return cls()

    async def add_event(self, event: EventData) -> bool:
        query = '''
            INSERT INTO resonanse_events (
                id, title, description, datetime_from, datetime_to, city,
                venue_title, venue_address, venue_lat, venue_lon,
                image_url, local_image_path, price_price, price_currency,
                tags, contact, service_id, service_type, service_data
            ) VALUES (
                %(id)s, %(title)s, %(description)s, %(datetime_from)s, %(datetime_to)s, %(city)s,
                %(venue_title)s, %(venue_address)s, %(venue_lat)s, %(venue_lon)s,
                %(image_url)s, %(local_image_path)s, %(price_price)s, %(price_currency)s,
                %(tags)s, %(contact)s, %(service_id)s, %(service_type)s, %(service_data)s
            )
        '''

        try:
            async with self._pool.connection() as aconn:
                async with aconn.cursor() as acur:
                    price_price = None
                    price_currency = None
                    if event.price is not None:
                        price_price = event.price.price
                        price_currency = event.price.currency

                    await acur.execute(
                        query,
                        {
                            'id': event.id,
                            'title': event.title,
                            'description': event.description,
                            'datetime_from': event.datetime_from,
                            'datetime_to': event.datetime_to,
                            'city': event.city,
                            'venue_title': event.venue.title,
                            'venue_address': event.venue.address,
                            'venue_lat': event.venue.lat,
                            'venue_lon': event.venue.lon,
                            'image_url': str(event.picture.image_url),
                            'local_image_path': event.picture.local_image,
                            'price_price': price_price,
                            'price_currency': price_currency,
                            'tags': event.tags,
                            'contact': event.contact,
                            'service_id': event.service_id,
                            'service_type': event.service_type,
                            'service_data': json.dumps(event.service_data),
                        }
                    )
        except psycopg.errors.Error as err:
            logger.exception('Error on add_event %s', err)
            return False

        return True

    async def fetch_events(self) -> list[EventData]:
        # todo possibly not working (not checked)
        query = '''
        SELECT id, title, description, datetime_from, datetime_to, city,
               venue_title, venue_address, venue_lat, venue_lon,
               image_url, local_image_path, price_price, price_currency,
               tags, contact, service_id, service_type, service_data
        FROM resonanse_events;
        '''

        async with self._pool.connection() as aconn:
            async with aconn.cursor() as acur:
                rows = acur.execute(query).fetchall()
                events = []

                for row in rows:
                    event = EventData(
                        id=row['id'],
                        title=row['title'],
                        description=row['description'],
                        datetime_from=row['datetime_from'],
                        datetime_to=row['datetime_to'],
                        city=row['city'],
                        venue=Venue(
                            title=row['venue_title'],
                            address=row['venue_address'],
                            lat=row['venue_lat'],
                            lon=row['venue_lon']
                        ),
                        picture=Image(
                            image_url=row['image_url'],
                            local_image=row['local_image_path']
                        ),
                        price=Price(
                            price=row['price_price'],
                            currency=row['price_currency']
                        ),
                        tags=row['tags'],
                        contact=row['contact'],
                        service_id=row['service_id'],
                        service_type=EventSource(row['service_type']),
                        service_data=row['service_data']
                    )
                    events.append(event)
                return events

    async def fetch_description_by_user_id(self, user_id: int) -> str | None:
        query = '''
        SELECT description FROM resonanse_users
        WHERE id = %(id)s;
        '''

        async with self._pool.connection() as aconn:
            async with aconn.cursor() as acur:
                user_description = acur.execute(
                    query,
                    {'id': user_id},
                ).fetchone()
                if user_description:
                    return user_description[0]

                return None
