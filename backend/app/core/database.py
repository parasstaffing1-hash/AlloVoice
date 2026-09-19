from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from app.core.config import get_settings
import os as _os
import ssl as _ssl

settings = get_settings()


def _connect_args(url: str) -> dict:
    # Managed Postgres (Aiven): TLS required. Default (like Aiven's own
    # examples with sslmode=require) = encrypted, no CA verification.
    # Drop your project ca.pem next to .env (or set PG_CA_PATH) to
    # upgrade to verify-ca automatically.
    if "aivencloud.com" not in url and "sslmode=require" not in url:
        return {}
    ca = _os.getenv("PG_CA_PATH", "")
    if not ca:
        _here = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))), "ca.pem")
        if _os.path.exists(_here):
            ca = _here
    if ca and _os.path.exists(ca):
        ctx = _ssl.create_default_context(cafile=ca)
        ctx.check_hostname = False  # verify-ca semantics
        return {"ssl": ctx}
    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE  # sslmode=require semantics
    return {"ssl": ctx}


# Strip libpq-style query params (e.g. ?sslmode=require); asyncpg takes ssl via connect_args.
_clean_url = settings.DATABASE_URL.split("?")[0]
_engine_kwargs: dict = {"echo": False, "connect_args": _connect_args(settings.DATABASE_URL)}
if _os.getenv("TESTING") == "1":
    # TestClient runs each test on a fresh event loop; pooled asyncpg
    # connections stay bound to the first loop ("Event loop is closed" /
    # "another operation is in progress"). NullPool = fresh conn per use.
    _engine_kwargs["poolclass"] = NullPool
engine = create_async_engine(_clean_url, **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
