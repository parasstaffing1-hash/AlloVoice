from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.core.database import get_db
from app.models.models import KnowledgeBaseArticle, Business, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


@router.post("/")
async def create_article(
    title: str,
    content: str,
    category: str = None,
    tags: list[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    slug = title.lower().replace(" ", "-").replace("'", "")
    article = KnowledgeBaseArticle(
        business_id=business.id,
        title=title,
        slug=slug,
        content=content,
        category=category,
        tags=tags or [],
        is_published=True,
    )
    db.add(article)
    await db.commit()
    await db.refresh(article)
    return {"id": str(article.id), "slug": slug}


@router.get("/")
async def list_articles(
    category: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Business).where(Business.owner_id == current_user.id))
    business = result.scalar_one_or_none()
    if not business:
        return []

    query = select(KnowledgeBaseArticle).where(
        KnowledgeBaseArticle.business_id == business.id,
        KnowledgeBaseArticle.is_published == True,
    )
    if category:
        query = query.where(KnowledgeBaseArticle.category == category)

    articles_result = await db.execute(query.order_by(KnowledgeBaseArticle.title))
    return [
        {
            "id": str(a.id),
            "title": a.title,
            "slug": a.slug,
            "category": a.category,
            "tags": a.tags,
            "view_count": a.view_count,
        }
        for a in articles_result.scalars().all()
    ]


@router.get("/{slug}")
async def get_article(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(KnowledgeBaseArticle).where(
            KnowledgeBaseArticle.slug == slug,
            KnowledgeBaseArticle.is_published == True,
        )
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    article.view_count += 1
    await db.commit()

    return {
        "id": str(article.id),
        "title": article.title,
        "content": article.content,
        "category": article.category,
        "tags": article.tags,
        "view_count": article.view_count,
        "helpful_count": article.helpful_count,
    }


@router.post("/{article_id}/helpful")
async def mark_helpful(
    article_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(KnowledgeBaseArticle).where(KnowledgeBaseArticle.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    article.helpful_count += 1
    await db.commit()
    return {"helpful_count": article.helpful_count}
