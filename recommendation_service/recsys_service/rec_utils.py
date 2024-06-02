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
from recsys_service.config import CLICKHOUSE_HOST
from recsys_service.config import CLICKHOUSE_PASSWORD
from recsys_service.config import CLICKHOUSE_USERNAME
from recsys_service.config import POSTGRES_DB
from recsys_service.config import POSTGRES_HOST
from recsys_service.config import POSTGRES_PASSWORD
from recsys_service.config import POSTGRES_PORT
from recsys_service.config import POSTGRES_USER
from recsys_service.config import QDRANT_HOST
from recsys_service.config import QDRANT_PORT


async def get_static_dssm_candidates(
        vectordb_client: VectorDB,
        user_id: int,
) -> RecommendationList:
    user_embeddings = await vectordb_client.get_users_vectors_by_ids({user_id})
    user_embedding = next(iter(user_embeddings), None)
    if user_embedding is None:
        return []

    result = await vectordb_client.search_event_by_vector(user_embedding, 10)
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

    implicit_coefficient = 0.2
    explicit_coefficient = 1  # value multiplier for explicit feedback

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
            positive_vectors.append(event_embedding * implicit_coefficient)
        elif interaction.interaction_type == InteractionKind.LIKE:
            positive_vectors.append(event_embedding * explicit_coefficient)
        elif interaction.interaction_type == InteractionKind.DISLIKE:
            negative_vectors.append(event_embedding * explicit_coefficient)

    if len(positive_vectors) == 0 and len(negative_vectors) == 0:
        return []

    # then count dynamic_embedding

    # user embedding from description or None if no description
    user_embeddings = await vectordb_client.get_users_vectors_by_ids({user_id})
    user_embedding = next(iter(user_embeddings), None)

    dynamic_embeddings_summed = sum(positive_vectors) + sum(negative_vectors)
    dynamic_embeddings_amount = len(positive_vectors) + len(negative_vectors)
    if user_embedding is not None:
        dynamic_embeddings_summed += user_embedding
        dynamic_embeddings_amount += 1

    dynamic_embedding = dynamic_embeddings_summed / dynamic_embeddings_amount

    # potentially vector search can return events, that was interacted by user
    # then we need to remove those events from candidates list
    limit = len(interacted_events_ids) + 10  # we need at least 10 events that user don't interacted

    result = await vectordb_client.search_event_by_vector(dynamic_embedding, limit)

    return [
        RecItem(
            subsystem=RecSubsystem.DYNAMIC,
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
    users_interacted_same_events = []
    for event_id in interacted_events_ids:
        users_interacted_same_events.append(await clickhouse_client.get_interactions_by_event(event_id, last_week, 10))

    users_interacted_same_events = itertools.chain.from_iterable(users_interacted_same_events)

    users_ids_interacted_same_events = {
        interaction.user_id for interaction in users_interacted_same_events
        if interaction.user_id != user_id
    }
    similar_users_embeddings = await vectordb_client.get_users_vectors_by_ids(users_ids_interacted_same_events)

    # 3. calculate average vector for those users
    if len(similar_users_embeddings) == 0:
        return []
    collaborative_embedding: np.ndarray = sum(similar_users_embeddings) / len(similar_users_embeddings)

    # 4. get candidates
    result = await vectordb_client.search_event_by_vector(collaborative_embedding, 10)
    return [
        RecItem(
            subsystem=RecSubsystem.COLLABORATIVE,
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


def get_candidates_events_ids(candidates: list[RecItem]) -> list[UUID]:
    return [
        selected_candidate.event.id
        for selected_candidate in candidates
    ]


def rescore_with_exponential_decay(candidates: RecommendationList) -> RecommendationList:
    request_dt = datetime.now()

    for candidate in candidates:
        event_dt = candidate.event.datetime_from
        time_delta = abs((event_dt - request_dt).days)
        adjust_recommendation_with_time_decay(candidate, time_delta)

    return candidates


def get_top_k(candidates: RecommendationList, limit: int, exclude=None) -> RecommendationList:
    """
    sort candidates by score and return K candidates
    :param candidates:
    :param limit: amount of items
    :param exclude: events to exclude from top k
    :return:
    """
    if exclude is None:
        exclude = []
    selected_candidates = []

    filtered_candidates = filter(
        lambda candidate: t.cast(RecItem, candidate).event.id,
        candidates
    )
    sorted_candidates = sorted(
        filtered_candidates,
        key=lambda candidate: t.cast(RecItem, candidate).score,
        reverse=True,
    )

    for candidate in sorted_candidates:
        candidate = t.cast(RecItem, candidate)
        if candidate.event.id in [
            *get_candidates_events_ids(selected_candidates),
            *exclude,
        ]:
            continue

        selected_candidates.append(candidate)
        if len(selected_candidates) >= limit:
            break

    return selected_candidates


def compose_recommendation_from_candidates_groups(
        candidates_by_groups: list[list[RecItem]],
        min_by_group: int,
        limit: int,
) -> list[RecItem]:
    """
    Rescores candidates and compose balanced sorted list of recommendations
    :param candidates_by_groups: list of recommendations by subsystem
    :param min_by_group: minimum amount of items from each group
    :param limit: amount of items in final result
    :return:
    """
    # 1. rescore candidates and take min amount from each group
    rescored_candidates_by_groups = []
    for candidates_group in candidates_by_groups:
        rescored_candidates = rescore_randomized(
            rescore_with_exponential_decay(
                candidates_group
            )
        )
        sorted_rescored_candidates = get_top_k(rescored_candidates, limit)
        rescored_candidates_by_groups.append(sorted_rescored_candidates)

    selected_candidates = []
    for index in range(min_by_group):
        for candidates_group in rescored_candidates_by_groups:
            for candidate in candidates_group:
                if candidate.event.id not in get_candidates_events_ids(selected_candidates):
                    selected_candidates.append(candidate)
                    break

    # 2. get top k candidates from remained
    remained = limit - len(selected_candidates)
    if remained > 0:
        other_candidates: list[RecItem] = itertools.chain.from_iterable(rescored_candidates_by_groups)
        selected_candidates.extend(get_top_k(
            other_candidates,
            remained,
            exclude=get_candidates_events_ids(selected_candidates),
        ))
    elif remained < 0:
        selected_candidates = selected_candidates[:-remained]
    return selected_candidates


async def get_recommendation_for_user_query(user_id: int) -> RecommendationList:
    vectordb_client = await VectorDB.get_client(QDRANT_HOST, QDRANT_PORT)
    clickhouse_client = await ClickHouseDB.get_client(
        CLICKHOUSE_HOST,
        CLICKHOUSE_USERNAME,
        CLICKHOUSE_PASSWORD,
    )

    # 1. get candidates
    basic_candidates = await get_static_dssm_candidates(
        vectordb_client,
        user_id,
    )

    DYNAMIC_REC_COEFFICIENT = 0.95  # noqa
    dynamic_candidates = await get_dynamic_dssm_candidates(
        vectordb_client,
        clickhouse_client,
        user_id,
    )
    for dynamic_candidate in dynamic_candidates:
        dynamic_candidate.score *= DYNAMIC_REC_COEFFICIENT

    COLLABORATIVE_REC_COEFFICIENT = 0.99  # noqa
    collaborative_candidates = await get_collaborative_dssm_candidates(
        vectordb_client,
        clickhouse_client,
        user_id,
    )
    for collaborative_candidate in collaborative_candidates:
        collaborative_candidate.score *= COLLABORATIVE_REC_COEFFICIENT

    candidates_by_groups = [
        basic_candidates,
        dynamic_candidates,
        collaborative_candidates,
    ]

    # 2. compose recommendation
    recommendation = compose_recommendation_from_candidates_groups(
        candidates_by_groups,
        2,
        10,
    )

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

    return await get_recommendation_for_user_query(
        user_id,
    )
