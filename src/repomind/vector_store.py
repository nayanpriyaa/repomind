from dataclasses import dataclass

import numpy as np

from repomind.models import CodeChunk


@dataclass
class StoredChunk:
    chunk: CodeChunk
    embedding: list[float]


class VectorStore:

    def __init__(self):
        self.items: list[StoredChunk] = []

    def add(
        self,
        chunk: CodeChunk,
        embedding: list[float],
    ) -> None:
        self.items.append(
            StoredChunk(
                chunk=chunk,
                embedding=embedding,
            )
        )

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[tuple[CodeChunk, float]]:

        query = np.array(query_embedding)

        results = []

        for item in self.items:
            vector = np.array(item.embedding)

            similarity = self._cosine_similarity(
                query,
                vector,
            )

            results.append(
                (item.chunk, similarity)
            )

        results.sort(
            key=lambda result: result[1],
            reverse=True,
        )

        return results[:top_k]

    @staticmethod
    def _cosine_similarity(
        vector_a: np.ndarray,
        vector_b: np.ndarray,
    ) -> float:

        magnitude_a = np.linalg.norm(vector_a)
        magnitude_b = np.linalg.norm(vector_b)

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return float(
            np.dot(vector_a, vector_b)
            / (magnitude_a * magnitude_b)
        )