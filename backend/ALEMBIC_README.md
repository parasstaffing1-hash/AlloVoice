# Alembic — VoiceField backend

Async Alembic setup. `env.py` reads `DATABASE_URL` from
`app.core.config.get_settings()` (strips `?...` query params, same as
`app/core/database.py`) and uses `Base.metadata` from `app.models.models`.
`alembic.ini`'s `sqlalchemy.url` is a placeholder — `env.py` overrides it.

Baseline: `0001_baseline` is an **empty no-op** revision. The live Aiven DB
already had all tables (via `create_all`); it was recorded with
`alembic stamp head`, which only writes the `alembic_version` row and does
not create/alter/drop any tables.

## Autogenerate a revision (future model changes)

```powershell
cd D:\Voice\backend
alembic revision --autogenerate -m "describe change"
# review the generated file under alembic\versions\, then:
alembic upgrade head
```

## Upgrade / check state

```powershell
alembic current    # show applied revision (expect 0001_baseline ...)
alembic history    # show revision chain
alembic upgrade head
```

## Rule going forward

**Always migrate — never rely on `create_all` for schema changes.**
`app/core/database.py::init_db()` (`Base.metadata.create_all`) is for
fresh local dev DBs only. Every model change must go through a reviewed
`alembic revision --autogenerate` + `alembic upgrade head`.
