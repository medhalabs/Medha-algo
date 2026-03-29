from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from dhanhq import dhanhq


def get_dhan(request: Request) -> dhanhq:
    return request.app.state.dhan


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_session():
        yield session
