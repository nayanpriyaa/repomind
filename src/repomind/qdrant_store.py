from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


class QdrantVectorStore:

    def __init__(
        self,
        collection_name: str = "repomind_chunks",
        host: str = "localhost",
        port: int = 6333,
    ):
        self.collection_name = collection_name

        self.client = QdrantClient(
            host=host,
            port=port,
        )

    def create_collection(self, vector_size: int) -> None:
        collections = self.client.get_collections()

        collection_names = {
            collection.name
            for collection in collections.collections
        }

        if self.collection_name in collection_names:
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )

    def add(
        self,
        point_id: int,
        vector: list[float],
        payload: dict,
    ) -> None:
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            ],
        )

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
    ):
        return self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
        ).points