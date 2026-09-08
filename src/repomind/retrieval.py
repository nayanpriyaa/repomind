from repomind.embeddings import EmbeddingModel
from repomind.file_hash import calculate_file_hash
from repomind.ids import generate_chunk_id
from repomind.index_state import IndexState
from repomind.keyword_search import keyword_score
from repomind.parser import parse_python_file
from repomind.qdrant_store import QdrantVectorStore
from repomind.scanner import scan_repository


class RepositorySearcher:

    def __init__(self):
        self.embedding_model = EmbeddingModel()
        self.vector_store = QdrantVectorStore()
        self.index_state = IndexState()

    def index_repository(self, repository_path: str) -> None:
        code_files = scan_repository(repository_path)

        indexed_files = self.index_state.get_indexed_files(
            repository_path
        )

        current_files = {
            str(code_file.path)
            for code_file in code_files
        }

        # Remove files that no longer exist.
        for indexed_file in indexed_files:
            if indexed_file not in current_files:
                self.vector_store.delete_file(
                    repository_path=repository_path,
                    file_path=indexed_file,
                )

                self.index_state.delete_file_record(
                    repository_path=repository_path,
                    file_path=indexed_file,
                )

        if not code_files:
            return

        collection_created = False

        for code_file in code_files:

            if code_file.language != "python":
                continue

            current_hash = calculate_file_hash(
                code_file.path
            )

            stored_hash = self.index_state.get_file_hash(
                repository_path=repository_path,
                file_path=str(code_file.path),
            )

            # File has not changed.
            if stored_hash == current_hash:
                continue

            # Delete old vectors if the file was
            # previously indexed.
            if stored_hash is not None:
                self.vector_store.delete_file(
                    repository_path=repository_path,
                    file_path=str(code_file.path),
                )

            chunks = parse_python_file(
                code_file.path
            )

            for chunk in chunks:

                embedding = self.embedding_model.embed(
                    chunk.content
                )

                if not collection_created:
                    self.vector_store.create_collection(
                        vector_size=len(embedding)
                    )

                    collection_created = True

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

            self.index_state.save_file_hash(
                repository_path=repository_path,
                file_path=str(code_file.path),
                file_hash=current_hash,
            )

    def search(
        self,
        query: str,
        repository_path: str | None = None,
        top_k: int = 5,
    ):
        """
        Search the indexed repository using semantic similarity.

        Keyword scoring is calculated separately and used to
        improve ranking of exact identifiers.
        """

        query_embedding = self.embedding_model.embed(query)

        semantic_results = self.vector_store.search(
            query_vector=query_embedding,
            top_k=top_k * 3,
            repository_path=repository_path,
        )

        ranked_results = []

        for result in semantic_results:
            payload = result.payload

            # Reconstruct enough information from the Qdrant
            # payload to perform keyword scoring.
            from repomind.models import CodeChunk

            chunk = CodeChunk(
                file_path=payload["file_path"],
                chunk_type=payload["chunk_type"],
                name=payload["name"],
                start_line=payload["start_line"],
                end_line=payload["end_line"],
                content=payload["content"],
            )

            semantic_score = result.score

            lexical_score = keyword_score(
                query=query,
                chunk=chunk,
            )

            # Hybrid score:
            #
            # 70% semantic similarity
            # 30% keyword matching
            hybrid_score = (
                0.7 * semantic_score
                + 0.3 * lexical_score
            )

            ranked_results.append(
                (
                    result,
                    hybrid_score,
                )
            )

        ranked_results.sort(
            key=lambda item: item[1],
            reverse=True,
        )

        return [
            result
            for result, _ in ranked_results[:top_k]
        ]