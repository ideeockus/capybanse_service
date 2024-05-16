import itertools
import math
import random
import typing as t
from datetime import datetime
from datetime import timedelta
from uuid import UUID

import numpy as np

from common.clients import ClickHouseDB
from common.clients import PostgresDB
from common.clients import VectorDB
from common.models import InteractionKind
from common.models import RecItem
from common.models import RecSubsystem
from common.models import RecommendationList
from common.models import UserInteraction
from recommendation_service.config import CLICKHOUSE_HOST
from recommendation_service.config import CLICKHOUSE_PASSWORD
from recommendation_service.config import CLICKHOUSE_USERNAME
from recommendation_service.config import POSTGRES_DB
from recommendation_service.config import POSTGRES_HOST
from recommendation_service.config import POSTGRES_PASSWORD
from recommendation_service.config import POSTGRES_PORT
from recommendation_service.config import POSTGRES_USER
from recommendation_service.config import QDRANT_HOST
from recommendation_service.config import QDRANT_PORT


async def get_static_dssm_candidates(
        vectordb_client: VectorDB,
        user_query: str,
) -> RecommendationList:
    result = await vectordb_client.search_event_by_request(user_query, 10)
    return [
        RecItem(
            subsystem=RecSubsystem.BASIC,
            score=item[0],
            event=item[1],
        ) for item in result
    ]


async def get_dynamic_dssm_candidates(
        vectordb_client: VectorDB,
        clickhouse_client: ClickHouseDB,
        user_id: int,
) -> RecommendationList:
    """
    1. get user clicks for recent
    2. calculate average vector for clicked events
    3. prepare candidates
    """
    last_week = datetime.now() - timedelta(days=7)
    considered_interactions = 100
    explicit_coefficient = 5  # value multiplier for explicit feedback

    # todo: 'HttpClient' object has no attribute 'get_interactions_by_user' ???
    interactions = await clickhouse_client.get_interactions_by_user(
        user_id,
        last_week,
        considered_interactions,
    )

    interacted_events_ids = {interaction.event_id for interaction in interactions}
    interacted_events_embeddings = await vectordb_client.get_events_vectors_by_ids(interacted_events_ids)
    interacted_events_embeddings_by_id: dict[UUID, np.ndarray] = {
        event_id: embedding
        for event_id, embedding in zip(interacted_events_ids, interacted_events_embeddings)
    }

    positive_vectors = []
    negative_vectors = []

    for interaction in interactions:
        event_embedding = interacted_events_embeddings_by_id[interaction.event_id]
        if interaction.interaction_type == InteractionKind.CLICK:
            positive_vectors.append(event_embedding)
        elif interaction.interaction_type == InteractionKind.LIKE:
            positive_vectors.append(event_embedding * explicit_coefficient)
        elif interaction.interaction_type == InteractionKind.DISLIKE:
            negative_vectors.append(event_embedding * explicit_coefficient)

    if len(positive_vectors) == 0 or len(negative_vectors) == 0:
        return []

    positive_vector: np.ndarray = sum(positive_vectors) / len(positive_vectors)
    negative_vector: np.ndarray = sum(negative_vectors) / len(negative_vectors)

    # potentially vector search can return events, that was interacted by user
    # then we need to remove those events from candidates list
    limit = len(interacted_events_ids) + 10  # we need at least 10 events that user don't interacted

    result = await vectordb_client.search_by_pos_neg_vectors(
        positive_vector,
        negative_vector,
        limit,
    )

    return [
        RecItem(
            subsystem=RecSubsystem.BASIC,
            score=item[0],
            event=item[1],
        ) for item in result
        if item[1].id not in interacted_events_ids
    ]


async def get_collaborative_dssm_candidates(
        vectordb_client: VectorDB,
        clickhouse_client: ClickHouseDB,
        user_id: int,
) -> RecommendationList:
    last_week = datetime.now() - timedelta(days=7)
    considered_interactions = 100

    # 1. get user clicks
    interactions = await clickhouse_client.get_interactions_by_user(
        user_id,
        last_week,
        considered_interactions,
    )
    interacted_events_ids = {interaction.event_id for interaction in interactions}

    # 2. get users who made same clicks
    # users_interacted_same_events: t.Iterable[UserInteraction] = itertools.chain.from_iterable((
    #     await clickhouse_client.get_interactions_by_event(event_id, last_week, 10)
    #     for event_id in interacted_events_ids
    # ))
    users_interacted_same_events = []
    for event_id in interacted_events_ids:
        users_interacted_same_events.append(await clickhouse_client.get_interactions_by_event(event_id, last_week, 10))

    users_interacted_same_events = itertools.chain.from_iterable(users_interacted_same_events)

    users_ids_interacted_same_events = {interaction.user_id for interaction in users_interacted_same_events}
    similar_users_embeddings = await vectordb_client.get_users_vectors_by_ids(users_ids_interacted_same_events)

    # 3. calculate average vector for those users
    if len(similar_users_embeddings) == 0:
        return []
    collaborative_embedding: np.ndarray = sum(similar_users_embeddings) / len(similar_users_embeddings)

    # 4. get candidates
    result = await vectordb_client.search_event_by_vector(collaborative_embedding, 10)
    return [
        RecItem(
            subsystem=RecSubsystem.BASIC,
            score=item[0],
            event=item[1],
        ) for item in result
    ]


def rescore_randomized(candidates: RecommendationList) -> RecommendationList:
    RAND_AMPLITUDE_COEF = 0.03  # coefficient to regulate randomiastion impact

    for rec in candidates:
        rec.score += random.uniform(-1, 1) * RAND_AMPLITUDE_COEF

    return candidates


def adjust_recommendation_with_time_decay(
        candidate: RecItem,
        time_delta: int,
) -> RecItem:
    # time_delta = days(|event dt - current dt|)
    DECAY = 0.002

    original_score = candidate.score
    adjusted_score = original_score * math.exp(-DECAY * time_delta)
    candidate.score = adjusted_score

    return candidate


def rescore_with_exponential_decay(candidates: RecommendationList) -> RecommendationList:
    request_dt = datetime.now()

    for candidate in candidates:
        event_dt = candidate.event.datetime_from
        time_delta = abs((event_dt - request_dt).days)
        adjust_recommendation_with_time_decay(candidate, time_delta)

    return candidates


def get_top_k(candidates: RecommendationList, limit: int) -> RecommendationList:
    return sorted(
        candidates,
        key=lambda candidate: t.cast(RecItem, candidate).score,
        reverse=True,
    )[:limit]


async def get_recommendation_for_user_query(user_id: int, user_query: str | None) -> RecommendationList:
    vectordb_client = await VectorDB.get_client(QDRANT_HOST, QDRANT_PORT)
    clickhouse_client = await ClickHouseDB.get_client(
        CLICKHOUSE_HOST,
        CLICKHOUSE_USERNAME,
        CLICKHOUSE_PASSWORD,
    )

    # 1. get candidates

    basic_candidates = []
    if user_query is not None:
        basic_candidates = await get_static_dssm_candidates(
            vectordb_client,
            user_query,
        )

    dynamic_candidates = await get_dynamic_dssm_candidates(
        vectordb_client,
        clickhouse_client,
        user_id,
    )
    collaborative_candidates = await get_collaborative_dssm_candidates(
        vectordb_client,
        clickhouse_client,
        user_id,
    )

    # 2. rescore candidates
    all_candidates = [
        *basic_candidates,
        *dynamic_candidates,
        *collaborative_candidates,
    ]

    rescored_candidates = rescore_randomized(
        rescore_with_exponential_decay(
            all_candidates
        )
    )

    # 3. get top k candidates
    recommendation = get_top_k(rescored_candidates, 10)

    # 4. save recommendation
    await clickhouse_client.insert_given_recommendation(
        user_id=user_id,
        recommendation=recommendation,
    )

    return recommendation


async def get_recommendation_for_user(user_id: int) -> RecommendationList:
    postgres_client = await PostgresDB.get_client(
        pg_user=POSTGRES_USER,
        pg_password=POSTGRES_PASSWORD,
        pg_host=POSTGRES_HOST,
        pg_port=POSTGRES_PORT,
        pg_db=POSTGRES_DB,
    )

    user_description = await postgres_client.fetch_description_by_user_id(user_id)
    return await get_recommendation_for_user_query(
        user_id,
        user_description,
    )
