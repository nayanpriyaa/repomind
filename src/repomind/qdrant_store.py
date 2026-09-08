from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)


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
      repository_path: str | None = None,
):
      query_filter = None

      if repository_path is not None:
          query_filter = Filter(
              must=[
                  FieldCondition(
                      key="repository_path",
                      match=MatchValue(
                          value=repository_path,
                    ),
                )
            ]
        )

      return self.client.query_points(
          collection_name=self.collection_name,
          query=query_vector,
          query_filter=query_filter,
          limit=top_k,
      ).points

    def delete_repository(self, repository_path: str) -> None:
      self.client.delete(
        collection_name=self.collection_name,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="repository_path",
                    match=MatchValue(
                        value=repository_path,
                    ),
                )
            ]
        ),
    )

    def delete_file(
    self,
    repository_path: str,
    file_path: str,
) -> None:
      self.client.delete(
        collection_name=self.collection_name,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="repository_path",
                    match=MatchValue(
                        value=repository_path,
                    ),
                ),
                FieldCondition(
                    key="file_path",
                    match=MatchValue(
                        value=file_path,
                    ),
                ),
            ]
        ),
    )