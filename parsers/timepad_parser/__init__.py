import typing as t
import uuid
from datetime import datetime

from httpx import AsyncClient
from selectolax.lexbor import LexborHTMLParser

import models
from models import EventData
from parsers.common_parser import EventsParser
from parsers.utils import get_logger
from parsers.utils import get_service_id
from parsers.utils import retry

logger = get_logger('timepad_parser')
API_URL = 'https://ontp.timepad.ru/api'


class TimepadParser(EventsParser):
    PAGE_SIZE = 24  # default, cannot be changed (?)

    def __init__(self, proxies: list[str]):
        super().__init__(proxies)
        # todo save state
        self.page = 1

    @staticmethod
    def parser_name():
        return 'timepad'

    async def _get_timepad_event(self, event_id: str) -> dict:
        event_url = API_URL + '/events/' + event_id
        logger.warning('event_url %s', event_url)
        async with AsyncClient(**self.get_httpx_client_params()) as client:
            response = await client.get(event_url)
            logger.debug('got event response %s', response)

            if response.is_success:
                response_json = response.json()
                return response_json
            else:
                logger.warning(
                    'event %s parsing error: %s',
                    event_id,
                    response.text,
                )

    @retry(times=3)
    async def _get_next_events(self) -> t.Iterable[EventData] | None:
        base_url = API_URL + '/events'
        logger.warning('base_url %s', base_url)

        async with AsyncClient(**self.get_httpx_client_params()) as client:
            response = await client.get(base_url, params={
                'page': self.page,
            })

            logger.debug('got events response %s', response)
            if response.is_success:
                # todo rework it
                self.page += 1
                response_json = response.json()
                events = response_json['list']
                events_json = [
                    await self._get_timepad_event(event['id']) for event in events
                ]

                return parse_timepad_response_as_events_data(events_json)
            else:
                logger.warning(
                    'page %s parsing error: %s',
                    self.page,
                    response.text,
                )

        return None


def parse_timepad_response_as_events_data(timepad_events: list[dict]) -> t.Generator[EventData, None, None]:
    logger.debug('Parsed %s events', len(timepad_events))

    for timepad_event in timepad_events:
        try:
            price = timepad_event.get('minPrice') or None
            if price and str(price).isnumeric():
                event_price = models.Price(
                    price=float(price),
                    currency='₽',
                )
            else:
                event_price = None

            # description is html, so we need parse text from it
            html_parser = LexborHTMLParser(timepad_event['body'])
            description = html_parser.text()

            datetime_from = datetime.fromisoformat(timepad_event['startDate'])
            datetime_to = None
            if end_date := timepad_event.get('endDate'):
                datetime_to = datetime.fromisoformat(end_date)

            event_data = EventData(
                id=uuid.uuid4(),
                title=timepad_event['title'],
                description=description,
                datetime_from=datetime_from,
                datetime_to=datetime_to,
                city=timepad_event['address']['city'],
                venue=models.Venue(
                    title=timepad_event['organization']['name'],
                    address=timepad_event['address']['street'],
                    lat=timepad_event['address']['lat'],
                    lon=timepad_event['address']['lon'],
                ),
                picture=models.Image(image_url=timepad_event.get('photo') or None),
                price=event_price,
                contact=timepad_event.get('contact_phone'),
                service_id=get_service_id('timepad', timepad_event['id']),
                service_type=models.EventSource.TIMEPAD,
                service_data=timepad_event,
            )

            yield event_data
        except Exception as err:
            logger.exception('Cannot parse event %s. Error %s', timepad_event, err)
            # todo should we suppress exception ?
            raise Exception('Event parse failed') from err


"""
Sample timepad response

as element from list  
{
"id": "2870001",
"parentId": "",
"status": "ok",
"recurringStatus": "ok",
"hits": "56",
"title": "Кукольный спектакль «Морская сказка» в «Фуд Парк Меркурий».",
"isAdvertisement": false,
"isRepeated": false,
"GAID": null,
"startDate": "2024-05-11 15:00:00",
"endDate": "2024-05-11 16:00:00",
"minPrice": 300,
"maxPrice": 300,
"ordersNumber": 0,
"ticketsNumber": 0,
"repeatedData": {
    "count": null,
    "nearest": null,
    "furthest": null
},
"ofertaLink": "https:\/\/fud-park-merkuriy.timepad.ru\/event\/oferta\/2870001\/",
"allowRegistration": true,
"categories": [
    "379"
],
"address": {
    "city": "Санкт-Петербург",
    "street": "Савушкина 141",
    "text": "Санкт-Петербург, Савушкина 141",
    "lat": "59.990899",
    "lon": "30.205789"
},
"contact_phone": "+79311031717",
"organization": {
    "id": "281061",
    "logo": "https:\/\/ucare.timepad.ru\/5be460c3-32c2-4d3b-a9e6-8f25b3754af3\/-\/preview\/308x600\/-\/format\/jpeg\/",
    "name": "ФудПарк Меркурий",
    "description": "",
    "pdAddress": "197374, г Санкт-Петербург, ул Савушкина, д 141 литера а, помещ 431 офис 1Н",
    "pdEmail": "info@foodparkmercury.ru",
    "inn": "7814758484",
    "ogrn": "1197847109349",
    "workingTime": "10:00 - 22:00",
    "shareLink": null,
    "poster": null,
    "socials": [
        {
            "name": "vk",
            "url": "https:\/\/vk.com\/foodparkmercury"
        },
        {
            "name": "facebook",
            "url": ""
        },
        {
            "name": "twitter",
            "url": ""
        },
        {
            "name": "telegram",
            "url": "https:\/\/t.me\/foodparkmercury"
        },
        {
            "name": "instagram",
            "url": ""
        },
        {
            "name": "web",
            "url": "https:\/\/foodparkmercury.ru\/"
        }
    ],
    "subscribers": 17,
    "eventCount": null,
    "isFavorite": null,
    "contact_phone": "+79311031717"
},
"isFavorite": false,
"order_mail": null,
"rating": null,
"startDateUnknown": false,
"ageLimit": "6"
},



as specified event

{
"ordersNumber": 0,
"ticketsNumber": 0,
"body": "<p><span style=\"font-size:12pt;\"><span><span style=\"font-size:14pt;\"><span>Участники встречи узнают о жизненном пути армянского писателя Егише Чаренца и обсудят его творчество. Ведущая расскажет также о музыке современной группы <\/span><\/span><span style=\"font-size:14pt;\"><span>ProjectLA<\/span><\/span><span style=\"font-size:14pt;\"><span>, вдохновленной стихами Чаренца. <\/span><\/span><\/span><\/span><\/p>\n\n<p><span style=\"font-size:12pt;\"><span><span style=\"font-size:14pt;\"><span>В завершении встречи присутствующие попробуют самостоятельно написать стихотворение.<\/span><\/span><\/span><\/span><\/p>\n\n<p><img alt=\"\" src=\"https:\/\/ucare.timepad.ru\/31f6b6a8-345a-405d-bdd2-96d0b63f559d\/-\/crop\/702x832\/537,128\/-\/preview\/\" \/><br \/>\n<br \/>\n<span style=\"font-size:12pt;\"><span><strong><span style=\"font-size:14pt;\"><span>Спикер &#151; Мари Мартиросян, <\/span><\/span><\/strong><span style=\"font-size:14pt;\"><span>автор экскурсий на армянском языке в главных музеях и арт-пространствах Москвы, ведущая телеграм-канала <a href=\"https:\/\/t.me\/Artinaccent\" rel=\"nofollow\">«Искусство с акцентом»<\/a>. <\/span><\/span><\/span><\/span><\/p>\n\n<hr \/>\n<p>Лекция пройдёт в Центре восточной литературы Российской государственной библиотеки, в конференц-зале. Выход № 4 из станции метро «Библиотека имени Ленина» по указателям к кассам Кремлёвского дворца, далее налево.<\/p>",
"header": "Центр восточной литературы Российской государственной библиотеки приглашает на встречу разговорного клуба армянского языка, организованную в рамках работы выставки «От линий к слову».",
"ageLimit": "12",
"shareLink": "https:\/\/leninka.timepad.ru\/event\/share\/2874594\/",
"photo": "https:\/\/ucare.timepad.ru\/e1824557-18d5-4a3e-9c6d-d27dfec1e4bd\/",
"id": "2874594",
"parentId": "",
"status": "ok",
"recurringStatus": "ok",
"hits": "7779",
"title": "Встреча разговорного клуба армянского языка",
"isAdvertisement": false,
"isRepeated": false,
"GAID": null,
"startDate": "2024-05-11 16:00:00",
"endDate": "2024-05-11 18:00:00",
"minPrice": null,
"maxPrice": null,
"repeatedData": null,
"ofertaLink": "https:\/\/leninka.timepad.ru\/event\/oferta\/2874594\/",
"allowRegistration": false,
"categories": [
    "525"
],
"address": {
    "city": "Москва",
    "street": "Москва, ул. Моховая, 6, 8",
    "text": "Москва, Москва, ул. Моховая, 6, 8",
    "lat": "55.750119",
    "lon": "37.609865"
},
"contact_phone": "+74995570470",
"organization": {
    "id": "67912",
    "logo": "https:\/\/ucare.timepad.ru\/bfdce00f-9f56-49d6-97ba-4ee83bda4c4c\/",
    "name": "Российская государственная библиотека",
    "description": "Главная библиотека России ",
    "pdAddress": "119019, Москва, ул. Воздвиженка, 3\/5",
    "pdEmail": "proekt@rsl.ru",
    "inn": null,
    "ogrn": null,
    "workingTime": "09:00 - 20:00",
    "shareLink": "https:\/\/leninka.timepad.ru\/org\/share\/67912\/",
    "personalDataPolicyLink": "https:\/\/leninka.timepad.ru\/org\/processing_of_personal_data\/",
    "poster": null,
    "socials": [
        {
            "name": "vk",
            "url": "https:\/\/vk.com\/leninka_ru"
        },
        {
            "name": "facebook",
            "url": "https:\/\/www.facebook.com\/pg\/Leninka.ru\/posts\/?ref=page_internal"
        },
        {
            "name": "twitter",
            "url": ""
        },
        {
            "name": "telegram",
            "url": "https:\/\/t.me\/leninka_ru"
        },
        {
            "name": "instagram",
            "url": "https:\/\/www.instagram.com\/leninka_official\/"
        },
        {
            "name": "web",
            "url": "https:\/\/www.rsl.ru\/"
        }
    ],
    "subscribers": 253,
    "eventCount": null,
    "isFavorite": false,
    "contact_phone": "+74995570470",
    "analytics": {
        "google_analytics": null,
        "yandex_metrika": "95331583"
    }
},
"isFavorite": false,
"order_mail": null,
"rating": null,
"startDateUnknown": false
}
"""
