import logging
from duckduckgo_search import DDGS

logger = logging.getLogger("lulu.search")


async def search_web(query: str, max_results: int = 5) -> str:
    """Searches DuckDuckGo and returns a formatted summary of results.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return.

    Returns:
        A formatted string with search results ready to inject as LLM context.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return "No se encontraron resultados para esa búsqueda."

        formatted = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "Sin título")
            body = r.get("body", "")
            url = r.get("href", "")
            formatted.append(f"{i}. **{title}**\n   {body}\n   Fuente: {url}")

        return "\n\n".join(formatted)

    except Exception as e:
        logger.error(f"Web search error: {e}")
        return f"Error al buscar: {e}"
