import asyncio

from fastapi import APIRouter, Query

from app.yahoo_apis import service

router = APIRouter()


@router.get("", summary="Search Yahoo Finance symbols / names")
async def search_yahoo(
    q: str = Query(..., min_length=1, description="Search text"),
    max_results: int = Query(25, ge=1, le=100),
):
    return await asyncio.to_thread(service.search_symbols, q, max_results=max_results)
