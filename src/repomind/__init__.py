"""RepoMind: LLM-powered codebase analysis and semantic search.

This package is intentionally import-cheap. No module may load a machine-learning
model, open a network connection or touch the filesystem at import time. Heavy
third-party dependencies (sentence-transformers, qdrant-client, tree-sitter,
fastapi) are imported lazily inside the functions that actually need them, which
keeps the domain core testable with nothing but the standard library.
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
