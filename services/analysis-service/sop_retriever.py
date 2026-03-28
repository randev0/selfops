"""
BM25-based Standard Operating Procedure (SOP) retriever.

Loads all Markdown files from the sop/ directory at startup and uses
BM25Okapi to find the most relevant SOPs for a given incident query.
The retrieved SOPs are injected into the agent prompt so the AI can
cite company policy in its recommendations.
"""

from pathlib import Path

import structlog
from rank_bm25 import BM25Okapi

log = structlog.get_logger()

_SOP_DIR = Path(__file__).parent / "sop"


class SOPRetriever:
    def __init__(self, sop_dir: Path = _SOP_DIR) -> None:
        self._docs: list[dict] = []
        self._bm25: BM25Okapi | None = None
        self._load(sop_dir)

    def _load(self, sop_dir: Path) -> None:
        if not sop_dir.exists():
            log.warning("SOP directory not found", path=str(sop_dir))
            return

        for md_file in sorted(sop_dir.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            self._docs.append({"source": md_file.name, "content": content})

        if not self._docs:
            log.warning("No SOP files found", path=str(sop_dir))
            return

        tokenized = [d["content"].lower().split() for d in self._docs]
        self._bm25 = BM25Okapi(tokenized)
        log.info("SOP retriever loaded", count=len(self._docs))

    def retrieve(self, query: str, top_k: int = 2) -> list[dict]:
        """Return the top-k most relevant SOP docs for the given query."""
        if not self._bm25 or not self._docs:
            return []

        tokens = query.lower().split()
        scores = self._bm25.get_scores(tokens)

        # Sort by score descending, return docs above a minimum relevance threshold
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [
            self._docs[i]
            for i, score in indexed[:top_k]
            if score > 0.1
        ]

    def format_for_prompt(self, query: str) -> str:
        """
        Return a formatted string of relevant SOPs ready to inject into
        the agent prompt. Returns empty string if no relevant SOPs found.
        """
        docs = self.retrieve(query)
        if not docs:
            return ""

        parts = [
            f"[SOP: {d['source']}]\n{d['content'].strip()}"
            for d in docs
        ]
        header = "\nRELEVANT COMPANY SOPs (you MUST cite these in your recommendation):\n"
        return header + "\n\n".join(parts) + "\n"


# Module-level singleton — loaded once at import time
_retriever: SOPRetriever | None = None


def get_retriever() -> SOPRetriever:
    global _retriever
    if _retriever is None:
        _retriever = SOPRetriever()
    return _retriever
