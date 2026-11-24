"""Database operations for the shared plant catalog."""

from functools import lru_cache
from typing import Any

from sqlalchemy import MetaData, Table, delete, insert, or_, select, update


@lru_cache(maxsize=1)
def _plants_table() -> Table:
    # Import lazily so API startup and non-database routes still work when the
    # deployment has not configured DATABASE_URL.
    from api.database import engine

    return Table("plants", MetaData(), autoload_with=engine)


def _engine():
    from api.database import engine

    return engine


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


def create_plant(values: dict[str, Any]) -> dict[str, Any]:
    table = _plants_table()
    statement = insert(table).values(**values).returning(table)
    with _engine().begin() as connection:
        row = connection.execute(statement).mappings().one()
    return dict(row)


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
