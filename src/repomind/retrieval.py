from repomind.embeddings import EmbeddingModel
from repomind.ids import generate_chunk_id
from repomind.ingestion import ingest_repository
from repomind.qdrant_store import QdrantVectorStore


class RepositorySearcher:

    def __init__(self):
        self.embedding_model = EmbeddingModel()
        self.vector_store = QdrantVectorStore()

    def index_repository(self, repository_path: str) -> None:
        chunks = ingest_repository(repository_path)

        if not chunks:
            return

        first_embedding = self.embedding_model.embed(
            chunks[0].content
        )

        self.vector_store.create_collection(
            vector_size=len(first_embedding)
        )

        self.vector_store.delete_repository(
    repository_path
)

        for chunk in chunks:
            embedding = self.embedding_model.embed(
                chunk.content
            )

            chunk_id = generate_chunk_id(
                repository_path=repository_path,
                file_path=str(chunk.file_path),
                chunk_type=chunk.chunk_type,
                name=chunk.name,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
            )

            self.vector_store.add(
                point_id=chunk_id,
                vector=embedding,
                payload={
                    "repository_path": repository_path,
                    "file_path": str(chunk.file_path),
                    "chunk_type": chunk.chunk_type,
                    "name": chunk.name,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content": chunk.content,
                },
            )

    def search(
        self,
        query: str,
        top_k: int = 5,
    ):
        query_embedding = self.embedding_model.embed(query)

        return self.vector_store.search(
            query_vector=query_embedding,
            top_k=top_k,
        )