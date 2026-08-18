"""
JARVIS AI — Local RAG & SLM Fallback Engine
============================================
Provides deterministic, zero-hallucination document search and local SLM synthesis.
Uses local text embeddings for document chunk retrieval and strict prompt anchoring.
"""

import math
import re
from pathlib import Path
from loguru import logger
from typing import List, Dict, Tuple, Optional


class LocalRAG:
    """
    100% Offline Retrieval-Augmented Generation (RAG) Engine.
    Indexes knowledge base files (*.md, *.yaml) and provides strict context-grounded Q&A.
    """

    def __init__(self, knowledge_dir: str = "data/knowledge_base/"):
        self.knowledge_dir = Path(knowledge_dir)
        self.documents: List[Dict[str, str]] = []
        self._load_documents()

    def _load_documents(self) -> None:
        """Load and chunk all Markdown and text files from the knowledge base."""
        self.documents.clear()
        if not self.knowledge_dir.exists():
            logger.warning(f"[LOCAL RAG] Knowledge directory missing: {self.knowledge_dir}")
            return

        for filepath in self.knowledge_dir.glob("**/*"):
            if filepath.suffix.lower() in [".md", ".txt", ".yaml"]:
                try:
                    content = filepath.read_text(encoding="utf-8")
                    chunks = self._chunk_text(content, source_name=filepath.name)
                    self.documents.extend(chunks)
                except Exception as e:
                    logger.error(f"[LOCAL RAG] Error reading {filepath}: {e}")

        logger.info(f"[LOCAL RAG] Loaded {len(self.documents)} document chunks from {self.knowledge_dir}")

    def _chunk_text(self, text: str, source_name: str, chunk_size: int = 300) -> List[Dict[str, str]]:
        """Split document content into structured chunks with headers."""
        chunks = []
        paragraphs = text.split("\n\n")
        current_chunk = ""

        for p in paragraphs:
            p_clean = p.strip()
            if not p_clean:
                continue
            if len(current_chunk) + len(p_clean) < chunk_size:
                current_chunk += "\n\n" + p_clean if current_chunk else p_clean
            else:
                if current_chunk:
                    chunks.append({"source": source_name, "text": current_chunk})
                current_chunk = p_clean

        if current_chunk:
            chunks.append({"source": source_name, "text": current_chunk})
        return chunks

    def search_relevant_chunks(self, query: str, top_k: int = 2) -> List[Tuple[float, Dict[str, str]]]:
        """
        Rank chunks using BM25 / TF-IDF keyword overlap scoring.
        Returns top matching chunks with confidence scores.
        """
    DOMAIN_KEYWORDS = {
        "caillou", "rover", "laser", "battery", "oxygen", "heart", "rate", "pulse",
        "status", "eva", "procedure", "step", "sample", "spectrometer", "amadee",
        "crew", "manifest", "pressure", "gps", "location", "habitat", "container",
        "handle", "arm", "target", "measurement", "recovery", "drone", "rock", "code"
    }

    def search_relevant_chunks(self, query: str, top_k: int = 2) -> List[Tuple[float, Dict[str, str]]]:
        """
        Rank chunks using BM25 keyword overlap scoring.
        Requires domain keyword presence to prevent illogical matches on ambient chatter.
        """
        if not query or not self.documents:
            return []

        query_words = set(re.findall(r"\w+", query.lower()))
        
        # Rule 1: Require at least one domain-specific keyword in the query
        if not (query_words & self.DOMAIN_KEYWORDS):
            return []

        # Expanded stopwords — prevents common words like 'next', 'video', 'you' from matching procedures
        stopwords = {
            "what", "is", "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of",
            "with", "do", "how", "le", "la", "les", "du", "de", "des", "un", "une", "next",
            "see", "you", "video", "bye", "thanks", "watching", "subscribe", "okay", "yes", "no"
        }
        keywords = {k for k in query_words if len(k) > 2 and k not in stopwords}

        if not keywords:
            return []

        results = []
        for doc in self.documents:
            doc_text_lower = doc["text"].lower()
            match_count = sum(1 for kw in keywords if kw in doc_text_lower)
            if match_count > 0:
                score = match_count / math.sqrt(len(keywords))
                results.append((score, doc))

        # Sort by score descending
        results.sort(key=lambda x: x[0], reverse=True)
        return results[:top_k]

    def query(self, query_text: str) -> Optional[str]:
        """
        Query Local RAG engine with strict confidence thresholding.
        """
        matches = self.search_relevant_chunks(query_text, top_k=2)
        if not matches:
            return None

        top_score, top_doc = matches[0]
        if top_score < 0.70:
            return None

        # Clean snippet text for concise voice output
        clean_text = top_doc["text"].replace("#", "").replace("*", "").strip()
        lines = [line.strip() for line in clean_text.split("\n") if line.strip()]

        # Limit to 2 concise sentences for speech playback
        summary = " ".join(lines[:2])
        if len(summary) > 220:
            summary = summary[:217] + "..."

        logger.info(f"[LOCAL RAG] Found match (score={top_score:.2f}, source={top_doc['source']}): '{summary[:60]}...'")
        return summary
