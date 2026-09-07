from sentence_transformers import SentenceTransformer


class EmbeddingModel:

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]:
        vector = self.model.encode(text)

        return vector.tolist()