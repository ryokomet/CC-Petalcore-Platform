"""Database operations for the shared plant catalog."""

from functools import lru_cache
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    LargeBinary,
    MetaData,
    String,
    Table,
    delete,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.exc import SQLAlchemyError


@lru_cache(maxsize=1)
def _plants_table() -> Table:
    # Import lazily so API startup and non-database routes still work when the
    # deployment has not configured DATABASE_URL.
    from api.database import engine

    return Table("plants", MetaData(), autoload_with=engine)


def _engine():
    from api.database import engine

    return engine


@lru_cache(maxsize=1)
def _plant_images_table() -> Table:
    plants = _plants_table()
    return Table(
        "plant_images",
        plants.metadata,
        Column(
            "plant_id",
            plants.c.id.type,
            ForeignKey(plants.c.id, ondelete="CASCADE"),
            primary_key=True,
        ),
        Column("content_type", String(40), nullable=False),
        Column("image_data", LargeBinary, nullable=False),
        Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        extend_existing=True,
    )


def _ensure_plant_images_table() -> Table:
    table = _plant_images_table()
    table.create(_engine(), checkfirst=True)
    return table


def list_plants() -> list[dict[str, Any]]:
    table = _plants_table()
    statement = select(table).order_by(table.c.id)
    with _engine().connect() as connection:
        return [dict(row) for row in connection.execute(statement).mappings().all()]


def find_plant(plant_id: int) -> dict[str, Any] | None:
    table = _plants_table()
    statement = select(table).where(table.c.id == plant_id)
    with _engine().connect() as connection:
        row = connection.execute(statement).mappings().first()
    return dict(row) if row is not None else None


def search_plants(query: str) -> list[dict[str, Any]]:
    table = _plants_table()
    pattern = f"%{query}%"
    statement = (
        select(table)
        .where(
            or_(
                table.c.common_name.ilike(pattern),
                table.c.scientific_name.ilike(pattern),
            )
        )
        .order_by(table.c.id)
    )
    with _engine().connect() as connection:
        return [dict(row) for row in connection.execute(statement).mappings().all()]


def create_plants_with_images(
    records: list[tuple[dict[str, Any], bytes]],
) -> list[dict[str, Any]]:
    table = _plants_table()
    image_table = _ensure_plant_images_table()
    created: list[dict[str, Any]] = []
    with _engine().begin() as connection:
        for values, image_data in records:
            statement = insert(table).values(**values).returning(table)
            row = dict(connection.execute(statement).mappings().one())
            connection.execute(
                insert(image_table).values(
                    plant_id=row["id"],
                    content_type="image/jpeg",
                    image_data=image_data,
                )
            )
            created.append(row)
    return created


def get_plant_image(plant_id: int) -> tuple[bytes, str] | None:
    image_table = _plant_images_table()
    engine = _engine()
    from sqlalchemy import inspect

    if not inspect(engine).has_table("plant_images"):
        return None
    statement = select(image_table.c.image_data, image_table.c.content_type).where(
        image_table.c.plant_id == plant_id
    )
    with engine.connect() as connection:
        try:
            row = connection.execute(statement).first()
        except SQLAlchemyError as exc:
            original = getattr(exc, "orig", None)
            sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
            if sqlstate == "42P01":
                return None
            raise
    if row is None:
        return None
    return bytes(row.image_data), row.content_type


def replace_plant_image(plant_id: int, image_data: bytes) -> bool:
    plants = _plants_table()
    image_table = _ensure_plant_images_table()
    image_upsert = postgres_insert(image_table).values(
        plant_id=plant_id,
        content_type="image/jpeg",
        image_data=image_data,
        updated_at=func.now(),
    )
    statement = image_upsert.on_conflict_do_update(
        index_elements=[image_table.c.plant_id],
        set_={
            "content_type": image_upsert.excluded.content_type,
            "image_data": image_upsert.excluded.image_data,
            "updated_at": func.now(),
        },
    )
    with _engine().begin() as connection:
        exists = connection.execute(
            select(plants.c.id).where(plants.c.id == plant_id)
        ).first()
        if exists is None:
            return False
        connection.execute(statement)
    return True


def replace_plant(plant_id: int, values: dict[str, Any]) -> dict[str, Any] | None:
    table = _plants_table()
    statement = (
        update(table)
        .where(table.c.id == plant_id)
        .values(**values)
        .returning(table)
    )
    with _engine().begin() as connection:
        row = connection.execute(statement).mappings().first()
    return dict(row) if row is not None else None


def remove_plant(plant_id: int) -> int | None:
    table = _plants_table()
    statement = delete(table).where(table.c.id == plant_id).returning(table.c.id)
    with _engine().begin() as connection:
        return connection.execute(statement).scalar_one_or_none()
