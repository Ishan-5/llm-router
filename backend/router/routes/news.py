import logging
import httpx
from fastapi import APIRouter
from router.config import TAVILY_API_KEY

router = APIRouter()
log = logging.getLogger("routewise.news")


@router.get("/news/headlines")
async def news_headlines():
    """Fetch live headlines from Tavily so the frontend suggestion chip stays realtime."""
    if not TAVILY_API_KEY:
        return {"headlines": []}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": "top news today",
                    "topic": "news",
                    "days": 1,
                    "max_results": 5,
                    "include_answer": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            headlines = [
                {"title": r.get("title", ""), "url": r.get("url", "")}
                for r in results
                if r.get("title")
            ]
            return {"headlines": headlines[:5]}
    except Exception as e:
        log.warning("Tavily headlines fetch failed: %s", e)
        return {"headlines": []}
