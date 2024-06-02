import re
import typing as t
import uuid
from datetime import datetime

from httpx import AsyncClient

from common import models
from common.models import EventData
from common.utils import get_logger
from parsers import storage
from parsers.common_parser import EventsParser
from parsers.utils import get_service_id
from parsers.utils import get_today_dt
from parsers.utils import retry

# import requests

logger = get_logger('kudago_parser')

API_URL_BASE = 'https://kudago.com/public-api/'
API_VERSION = 'v1.4'

API_URL = API_URL_BASE + API_VERSION


class KudagoParser(EventsParser):
    PAGE_SIZE = 40  # up to 100, default 20
    FIELDS = (
        'id,publication_date,dates,title,short_title,slug,place,description,'
        'body_text,location,categories,tagline,age_restriction,price,is_free,'
        'images,favorites_count,comments_count,site_url,tags,participants'
    )
    PAGE_STATE_KEY = 'kudago_page'

    def __init__(self, proxies: list[str]):
        super().__init__(proxies)

        persisted_state = storage.get_state(KudagoParser.PAGE_STATE_KEY) or 1
        self.page: int = int(persisted_state)
        logger.info('%s initialized with page %s', self.__class__.__name__, self.page)

    @staticmethod
    def parser_name():
        return 'kudago'

    async def _reset_state(self):
        self.page = 1
        storage.set_state(KudagoParser.PAGE_STATE_KEY, str(1))

    @retry(times=3)
    async def _get_next_events(self) -> t.Iterable[EventData] | None:
        base_url = API_URL + '/events/'

        async with AsyncClient() as client:
            response = await client.get(base_url, params={
                'page': self.page,
                'page_size': KudagoParser.PAGE_SIZE,
                'fields': KudagoParser.FIELDS,
                'text_format': 'plain',
                'actual_since': get_today_dt(),
            })

            logger.debug('got events response %s', response)
            if response.is_success:
                response_json = response.json()
                if len(response_json['results']) == 0:
                    return None

                parsed_events = parse_kudago_response_as_events_data(response_json)

                self.page += 1
                storage.set_state(KudagoParser.PAGE_STATE_KEY, str(self.page))
                return parsed_events
            else:
                logger.warning(
                    'page %s parsing error: %s',
                    self.page,
                    response.text
                )

        return None


CITY_CODE_TO_NAME_MAP = {
    'online': 'Онлайн',
    'spb': 'Санкт-Петербург',
    'msk': 'Москва',
    'nsk': 'Новосибирск',
    'ekb': 'Екатеринбург',
    'nnv': 'Нижний Новгород',
    'kzn': 'Казань',
    'vbg': 'Выборг',
    'smr': 'Самара',
    'krd': 'Краснодар',
    'sochi': 'Сочи',
    'ufa': 'Уфа',
    'krasnoyarsk': 'Красноярск',
    'kev': 'Киев',
    'new-york': 'Нью-Йорк',
    'london': 'Лондон',
    'atlanta': 'Атланта',
    'mns': 'Минск',
    'ryazan': 'Рязань',
    'singapore': 'Сингапур',
}


def extract_minimum_price(text: str) -> int | None:
    numbers = re.findall(r'\d+', text)
    numbers = list(map(int, numbers))
    return min(numbers) if numbers else None


def parse_kudago_response_as_events_data(kudago_response: dict) -> t.Generator[EventData, None, None]:
    results = kudago_response['results']
    logger.debug('Parsed %s events', len(results))

    for kudago_event in results:
        try:
            price = kudago_event.get('price') or None
            if price and str(price).isnumeric():
                event_price = models.Price(
                    price=float(price),
                    currency='₽',
                )
            elif price:
                if extracted_price := extract_minimum_price(price):
                    event_price = models.Price(
                        price=extracted_price,
                        currency='₽',
                    )
            else:
                event_price = None

            city_slug = kudago_event['location']['slug']
            city = CITY_CODE_TO_NAME_MAP.get(city_slug) or city_slug
            place = city

            datetime_from = datetime.fromtimestamp(kudago_event['dates'][0]['start'])
            datetime_to = None
            if end_date := kudago_event['dates'][0].get('end'):
                datetime_to = datetime.fromtimestamp(end_date)

            event_data = EventData(
                id=uuid.uuid4(),
                title=kudago_event['title'],
                description=kudago_event['body_text'],
                datetime_from=datetime_from,
                datetime_to=datetime_to,
                city=city,
                venue=models.Venue(title=place),
                picture=models.Image(image_url=kudago_event['images'][0].get('image') or None),
                price=event_price,
                tags=kudago_event['tags'],
                contact=kudago_event.get('site_url'),
                service_id=get_service_id('kudago', kudago_event['id']),
                service_type=models.EventSource.KUDAGO,
                service_data=kudago_event,
            )

            yield event_data
        except Exception as err:
            logger.exception('Cannot parse event %s. Error %s', kudago_event, err)
            # should we suppress exception ?
            raise Exception('Event parse failed') from err


"""
Sample kudago response

{
"id": 161043,
"publication_date": 1507554305,
"dates": [
    {
        "start": 1509811200,
        "end": 1509912000
    }
],
"title": "Фестиваль света",
"slug": "prazdnik-festival-sveta-2017",
"place": null,
"description": "Петербург славится своими культурными традициями, и одна из них зарождается прямо на наших глазах — это Фестиваль света. Праздник проходит второй год подряд и привлекает тысячи зрителей. В этот раз темой стал юбилей Октябрьской революции.\n\n",
"body_text": "4 и 5 ноября в Петербурге пройдёт очередной Фестиваль света. На этот раз действо захватит сразу две площадки — площади Островского https://kudago.com/spb/place/ploshad-ostrovskogo/ .\n",
"location": {
    "slug": "spb"
},
"categories": [
    "holiday",
    "festival"
],
"tagline": "",
"age_restriction": 0,
"price": "",
"is_free": true,
"images": [
    {
        "image": "https://media.kudago.com/images/event/82/bb/82bb410cca413007c5598f40c6ebd68c.jpg",
        "source": {
            "name": "",
            "link": ""
        }
    }
],
"favorites_count": 352,
"comments_count": 6,
"site_url": "https://kudago.com/spb/event/prazdnik-festival-sveta-2017/",
"short_title": "Фестиваль света",
"tags": [
    "free",
    "праздники",
    "фестивали",
    "open air",
    "городские"
],
"participants": []
},
"""
