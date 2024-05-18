import os
import typing as t
from datetime import datetime
from datetime import timedelta
from uuid import UUID

import numpy as np
from fastembed import TextEmbedding
from qdrant_client import AsyncQdrantClient
from qdrant_client import models

from common.models import EventData
from common.utils import get_logger

# todo fix this path
CACHE_DIR = os.getenv('FASTEMBED_CACHE_DIR') or '/var/capybanse/model'
QDRANT_EVENTS_COLLECTION = 'events_collection'
QDRANT_USERS_COLLECTION = 'users_collection'
RECOMMENDATION_PERIOD = timedelta(days=180)

logger = get_logger('vectordb_client')


class VectorDB:
    _qdrant_client: AsyncQdrantClient | None = None
    _multilingual_model = TextEmbedding(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        cache_dir=CACHE_DIR,
    )

    @classmethod
    async def get_client(
            cls,
            qdrant_host: str,
            qdrant_port: int | None = None,
    ) -> t.Self:
        if cls._qdrant_client is not None:
            return cls()

        qdrant_client = AsyncQdrantClient(
            host=qdrant_host,
            port=qdrant_port,
        )

        # initialize collections if not exists
        is_events_collections_exists = await qdrant_client.collection_exists(QDRANT_EVENTS_COLLECTION)
        if not is_events_collections_exists:
            logger.info('no collection %s, creating', QDRANT_EVENTS_COLLECTION)
            await qdrant_client.create_collection(
                collection_name=QDRANT_EVENTS_COLLECTION,
                vectors_config=models.VectorParams(
                    size=384, distance=models.Distance.COSINE, on_disk=True
                ),
            )

        is_users_collections_exists = await qdrant_client.collection_exists(QDRANT_USERS_COLLECTION)
        if not is_users_collections_exists:
            logger.info('no collection %s, creating', QDRANT_USERS_COLLECTION)
            await qdrant_client.create_collection(
                collection_name=QDRANT_USERS_COLLECTION,
                vectors_config=models.VectorParams(
                    size=384, distance=models.Distance.COSINE, on_disk=True
                ),
            )

        cls._qdrant_client = qdrant_client
        return cls()

    async def add_event(self, event: EventData) -> bool:
        # vectorize description if not empty
        if event.description is None or len(event.description) <= 20:
            # no reason to vectorize such event
            return False

        embeddings_generator = self._multilingual_model.embed(event.description)
        event_embedding = list(embeddings_generator)[0]

        # then add to qdrant
        await self._qdrant_client.upsert(
            collection_name=QDRANT_EVENTS_COLLECTION,
            points=[
                models.PointStruct(
                    id=event.id.hex,
                    payload=event.model_dump(),
                    vector=event_embedding,
                )
            ]
        )

        return True

    async def search_event_by_vector(
            self,
            embedding: np.ndarray | list[float],
            limit: int,
    ) -> list[tuple[float, EventData]]:
        """
        perform search by request, filtering by date of event
        """
        request_dt = datetime.now()

        scored_points = await self._qdrant_client.search(
            collection_name=QDRANT_EVENTS_COLLECTION,
            query_vector=embedding,
            with_vectors=False,
            with_payload=True,
            limit=limit,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="datetime_from",
                        range=models.DatetimeRange(
                            gte=request_dt,
                            lte=request_dt + RECOMMENDATION_PERIOD,
                        ),
                    ),
                ]
            ),
        )

        return [
            (scored_point.score, EventData.model_validate(scored_point.payload))
            for scored_point in scored_points
        ]

    async def search_event_by_request(self, request: str, limit: int) -> list[tuple[float, EventData]]:
        embeddings_generator = self._multilingual_model.embed(request)
        embedding = list(embeddings_generator)[0]

        return await self.search_event_by_vector(embedding, limit)

    async def search_by_pos_neg_vectors(
            self,
            positive: list[str] | None,
            negative: list[str] | None,
            limit: int,
    ) -> list[tuple[float, EventData]]:
        if not positive and not negative:
            return []
        request_dt = datetime.now()

        scored_points = await self._qdrant_client.recommend(
            collection_name=QDRANT_EVENTS_COLLECTION,
            positive=positive,
            negative=negative,
            strategy=models.RecommendStrategy.BEST_SCORE,
            with_vectors=False,
            with_payload=True,
            limit=limit,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="datetime_from",
                        range=models.DatetimeRange(
                            gte=request_dt,
                            lte=request_dt + RECOMMENDATION_PERIOD,
                        ),
                    ),
                ]
            ),
        )

        return [
            (scored_point.score, EventData.model_validate(scored_point.payload))
            for scored_point in scored_points
        ]

    async def get_events_vectors_by_ids(self, events_ids: set[UUID]) -> list[np.ndarray]:
        records = await self._qdrant_client.retrieve(
            collection_name=QDRANT_EVENTS_COLLECTION,
            ids=[event_id.hex for event_id in events_ids],
            with_payload=False,
            with_vectors=True,
        )

        vectors: list[np.ndarray] = [
            np.array(record.vector, dtype=np.float32)
            for record in records
        ]
        return vectors

    async def add_user_description(self, user_id: int, description: str) -> bool:
        # vectorize description if not empty
        if description is None or len(description) <= 10:
            return False

        embeddings_generator = self._multilingual_model.embed(description)
        description_embedding = list(embeddings_generator)[0]

        # then add to qdrant
        await self._qdrant_client.upsert(
            collection_name=QDRANT_USERS_COLLECTION,
            points=[
                models.PointStruct(
                    id=user_id,
                    vector=description_embedding,
                )
            ]
        )

        return True

    async def get_users_vectors_by_ids(self, users_ids: set[int]) -> list[np.ndarray]:
        records = await self._qdrant_client.retrieve(
            collection_name=QDRANT_USERS_COLLECTION,
            ids=list(users_ids),
            with_payload=False,
            with_vectors=True,
        )

        vectors: list[np.ndarray] = [
            np.array(record.vector, dtype=np.float32)
            for record in records
        ]
        return vectors
