import typing as t
from datetime import datetime
from uuid import UUID

import clickhouse_connect

from common.clients.prepared_sql import CREATE_GIVEN_RECOMMENDATIONS_TABLE
from common.clients.prepared_sql import CREATE_USERS_INTERACTION_TABLE
from common.models import RecommendationList
from common.models import UserInteraction
from common.utils import get_logger

logger = get_logger('clickhouse_client')


class ClickHouseDB:
    _clickhouse_client: clickhouse_connect.driver.client.Client | None = None

    @classmethod
    async def get_client(cls, host, username, password) -> t.Self:
        if cls._clickhouse_client is not None:
            return cls._clickhouse_client

        client = clickhouse_connect.get_client(host=host, username=username, password=password)
        client.command(CREATE_USERS_INTERACTION_TABLE)
        client.command(CREATE_GIVEN_RECOMMENDATIONS_TABLE)

        cls._clickhouse_client = client

        return cls()

    async def insert_interaction(self, user_id: int, event_id: UUID, interaction_type: str):
        self._clickhouse_client.insert(
            'users_interactions',
            [(user_id, event_id.hex, interaction_type, datetime.now())],
            column_names=['user_id', 'event_id', 'interaction_type', 'interaction_dt'],
        )

    async def insert_given_recommendation(
            self,
            user_id: int,
            recommendation: RecommendationList,
    ):
        recommended_events = [
            (rec.event.id, rec.subsystem, rec.score)
            for rec in recommendation
        ]
        self._clickhouse_client.insert(
            'given_recommendations',
            [(user_id, recommended_events, datetime.now())],
            column_names=['user_id', 'recommended_events', 'recommendation_dt'],
        )

    async def get_interactions_by_user(self, user_id: int, after_dt: datetime, limit: int) -> list[UserInteraction]:
        result = self._clickhouse_client.query(
            '''
            SELECT * FROM users_interactions WHERE (user_id = %(v1)s) AND (interaction_dt >= %(v2)s)
            ORDER BY interaction_dt DESC
            LIMIT %(v3)s
            ''',
            parameters={
                'v1': user_id,
                'v2': after_dt,
                'v3': limit,
            }
        )

        return [
            UserInteraction(
                user_id=row[0], event_id=row[1],
                interaction_type=row[2], interaction_dt=row[3],
            )
            for row in result.result_rows
        ]

    async def get_interactions_by_event(self, event_id: UUID, after_dt: datetime, limit: int) -> list[UserInteraction]:
        result = self._clickhouse_client.query(
            '''
            SELECT * FROM users_interactions WHERE (event_id = %(v1)s) AND (interaction_dt >= %(v2)s)
            ORDER BY interaction_dt DESC
            LIMIT %(v3)s);
            ''',
            parameters={
                'v1': event_id.hex,
                'v2': after_dt,
                'v3': limit,
            }
        )

        return [
            UserInteraction(
                user_id=row[0], event_id=row[1],
                interaction_type=row[2], interaction_dt=row[3],
            )
            for row in result.result_rows
        ]
