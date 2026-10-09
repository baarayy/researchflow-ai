"""Create/upgrade LangGraph's checkpoint tables (they are managed by the library, not Alembic)."""

import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import get_settings


async def main() -> None:
    async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as saver:
        await saver.setup()
    print("LangGraph checkpoint tables are up to date.")


if __name__ == "__main__":
    asyncio.run(main())
