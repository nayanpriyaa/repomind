from repomind.embeddings import EmbeddingModel
from repomind.ingestion import ingest_repository
from repomind.vector_store import VectorStore


class RepositorySearcher:

    def __init__(self):
        self.embedding_model = EmbeddingModel()
        self.vector_store = VectorStore()

    def index_repository(self, repository_path: str) -> None:
        chunks = ingest_repository(repository_path)

        for chunk in chunks:
            embedding = self.embedding_model.embed(
                chunk.content
            )

            self.vector_store.add(
                chunk,
                embedding,
            )

    def search(
        self,
        query: str,
        top_k: int = 5,
    ):
        query_embedding = self.embedding_model.embed(query)

        return self.vector_store.search(
            query_embedding,
            top_k=top_k,
        )