import httpx

base_url = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies.json"

async def fetch_currency_codes() -> dict[str, str]:
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(base_url)
        r.raise_for_status()
        print(r.json())
    return r.json()

if __name__ == "__main__":
    import asyncio
    asyncio.run(fetch_currency_codes())