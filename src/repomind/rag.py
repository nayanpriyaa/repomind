"""Retrieval-augmented generation pipeline.

question -> retrieval -> context -> prompt -> LLM -> answer + citations.

The service deliberately short-circuits when retrieval returns nothing: calling
the model with an empty evidence block is the single most reliable way to get a
confidently wrong answer about a codebase.
"""

from __future__ import annotations

import logging

from .context import build_context
from .llm import LLMClient, LLMError
from .models import Answer, SearchMode
from .prompt import SYSTEM_PROMPT, build_user_prompt, no_evidence_answer
from .retrieval import RetrievalRequest, RetrievalService

logger = logging.getLogger(__name__)


class RagService:
    """Answers questions about an indexed repository, with citations."""

    def __init__(
        self,
        retrieval: RetrievalService,
        llm: LLMClient,
        max_context_characters: int = 24_000,
    ) -> None:
        self._retrieval = retrieval
        self._llm = llm
        self._max_context_characters = max_context_characters

    def answer(
        self,
        question: str,
        repository_path: str | None = None,
        top_k: int = 5,
        mode: SearchMode = SearchMode.HYBRID,
    ) -> Answer:
        """Run the full pipeline for one question."""
        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")

        chunks = self._retrieval.search(
            RetrievalRequest(
                query=question,
                mode=mode,
                top_k=top_k,
                repository_path=repository_path,
            )
        )
        context = build_context(chunks, self._max_context_characters)

        if context.is_empty:
            return Answer(
                question=question,
                answer=no_evidence_answer(),
                mode=mode,
                citations=[],
                chunks_used=0,
                context_characters=0,
                grounded=False,
            )

        prompt = build_user_prompt(question, context)
        try:
            text = self._llm.generate(SYSTEM_PROMPT, prompt)
        except LLMError as exc:
            logger.error("LLM generation failed: %s", exc)
            raise

        return Answer(
            question=question,
            answer=text,
            mode=mode,
            citations=context.citations,
            chunks_used=context.chunks_used,
            context_characters=context.characters,
            grounded=True,
        )
