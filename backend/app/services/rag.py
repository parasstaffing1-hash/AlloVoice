"""pgvector semantic retrieval over KB articles, with keyword fallback.

All entry points never raise — worst case they return [] / False so chat
endpoints can never 500 because of RAG. No ORM model changes; the
kb_embeddings table is managed via raw SQL.
"""

import logging
import re
import time
import uuid

from sqlalchemy import text

log = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"
EMBED_DIM = 384
CHUNK_CHARS = 500

_model = None
_load_failed_at: float | None = None
_LOAD_RETRY_S = 300.0
_vector_ok: bool | None = None


def _get_model():
    """Lazy singleton SentenceTransformer. Returns None (never raises) on failure."""
    global _model, _load_failed_at
    if _model is not None:
        return _model
    if _load_failed_at is not None and (time.monotonic() - _load_failed_at) < _LOAD_RETRY_S:
        return None
    try:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
        return _model
    except Exception:
        log.warning("rag: embedding model unavailable, using keyword fallback", exc_info=True)
        _load_failed_at = time.monotonic()
        return None


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Never raises — returns [] on any failure."""
    try:
        clean = [(t or "").strip() for t in (texts or [])]
        clean = [t for t in clean if t]
        if not clean:
            return []
        model = _get_model()
        if model is None:
            return []
        vectors = model.encode(clean, show_progress_bar=False)
        return [[float(x) for x in row] for row in vectors]
    except Exception:
        log.warning("rag: embed failed", exc_info=True)
        return []


async def _pgvector_available(db) -> bool:
    """True when the `vector` extension exists. Positive result is cached."""
    global _vector_ok
    if _vector_ok:
        return True
    try:
        result = await db.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'"))
        if result.first():
            _vector_ok = True
            return True
        return False
    except Exception:
        return False


async def ensure_store(db) -> bool:
    """Create kb_embeddings table if missing. Returns False (never raises) on failure."""
    try:
        if not await _pgvector_available(db):
            return False
        await db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS kb_embeddings ("
                "id UUID PRIMARY KEY, "
                "article_id UUID NOT NULL, "
                "business_id UUID NULL, "
                f"embedding vector({EMBED_DIM}) NOT NULL, "
                "chunk_text TEXT NOT NULL, "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_kb_embeddings_article "
                "ON kb_embeddings (article_id)"
            )
        )
        await db.commit()
        return True
    except Exception:
        log.warning("rag: ensure_store failed", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        return False


def _chunk(title: str, content: str, size: int = CHUNK_CHARS) -> list[str]:
    full = ((title or "").strip() + "\n\n" + (content or "").strip()).strip()
    if not full:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(full):
        end = min(start + size, len(full))
        if end < len(full):
            cut = full.rfind(" ", start, end)
            if cut > start + size // 2:
                end = cut
        piece = full[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end
    return chunks


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def index_article(db, article_id, business_id, title: str, content: str) -> bool:
    """(Re)index one article: delete old rows, insert fresh chunk embeddings.

    Never raises — returns False on any failure (article stays searchable
    via keyword fallback).
    """
    try:
        if not await ensure_store(db):
            return False
        chunks = _chunk(title, content)
        await db.execute(
            text("DELETE FROM kb_embeddings WHERE article_id = :aid"),
            {"aid": str(article_id)},
        )
        if chunks:
            vecs = embed(chunks)
            if not vecs:
                await db.commit()
                return False
            for chunk_text, vec in zip(chunks, vecs):
                await db.execute(
                    text(
                        "INSERT INTO kb_embeddings "
                        "(id, article_id, business_id, embedding, chunk_text) "
                        "VALUES (:id, :aid, :bid, CAST(:emb AS vector), :ct)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "aid": str(article_id),
                        "bid": str(business_id) if business_id is not None else None,
                        "emb": _vec_literal(vec),
                        "ct": chunk_text,
                    },
                )
        await db.commit()
        return True
    except Exception:
        log.warning("rag: index_article failed", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        return False


async def _keyword_fallback(db, query: str, business_id=None, limit: int = 3) -> list[dict]:
    """Replicates the title×3/content×1 keyword scoring from chatbot.py."""
    try:
        from app.models.models import KnowledgeBaseArticle
        from sqlalchemy import select

        tokens = re.findall(r"[a-z]{3,}", (query or "").lower())
        if not tokens or db is None:
            return []
        stmt = select(KnowledgeBaseArticle).where(
            KnowledgeBaseArticle.is_published == True  # noqa: E712
        )
        if business_id is not None:
            stmt = stmt.where(KnowledgeBaseArticle.business_id == business_id)
        result = await db.execute(stmt)
        articles = result.scalars().all()
        if not articles:
            return []
        scored: list[tuple] = []
        for article in articles:
            title_lower = (article.title or "").lower()
            content_lower = (article.content or "").lower()
            score = 0
            for token in tokens:
                score += title_lower.count(token) * 3 + content_lower.count(token) * 1
            if score > 0:
                scored.append(
                    (
                        score,
                        {
                            "title": article.title,
                            "excerpt": (article.content or "")[:300],
                            "score": float(score),
                        },
                    )
                )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [hit for _, hit in scored[:limit]]
    except Exception:
        return []


async def retrieve(db, query: str, business_id=None, limit: int = 3) -> list[dict]:
    """Semantic retrieval; falls back to keyword search when embeddings or
    pgvector are unavailable (or yield nothing). Never raises."""
    try:
        vecs = embed([query or ""])
        if vecs and await ensure_store(db):
            try:
                params: dict = {"vec": _vec_literal(vecs[0]), "limit": limit}
                scope = ""
                if business_id is not None:
                    scope = "AND a.business_id = :bid"
                    params["bid"] = str(business_id)
                rows = (
                    await db.execute(
                        text(
                            "SELECT a.title, e.chunk_text, "
                            "e.embedding <=> CAST(:vec AS vector) AS distance "
                            "FROM kb_embeddings e "
                            "JOIN kb_articles a ON a.id = e.article_id "
                            "WHERE a.is_published = true "
                            f"{scope} "
                            "ORDER BY e.embedding <=> CAST(:vec AS vector) "
                            "LIMIT :limit"
                        ),
                        params,
                    )
                ).all()
                hits: list[dict] = []
                seen: set[str] = set()
                for title, chunk_text, distance in rows:
                    if title in seen:
                        continue
                    seen.add(title)
                    try:
                        score = 1.0 - float(distance)
                    except (TypeError, ValueError):
                        score = 0.0
                    hits.append(
                        {
                            "title": title,
                            "excerpt": (chunk_text or "")[:300],
                            "score": score,
                        }
                    )
                if hits:
                    return hits
            except Exception:
                log.warning("rag: vector query failed, trying keyword", exc_info=True)
    except Exception:
        pass
    try:
        return await _keyword_fallback(db, query, business_id, limit)
    except Exception:
        return []
