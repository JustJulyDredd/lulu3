import logging
from duckduckgo_search import DDGS

logger = logging.getLogger("lulu.search")


async def search_web(query: str, max_results: int = 5) -> str:
    """Busca en DuckDuckGo y devuelve un resumen formateado de los resultados.

    Args:
        query: La cadena de búsqueda.
        max_results: Número máximo de resultados a devolver.

    Returns:
        Una cadena formateada con los resultados lista para usar como contexto en el LLM.
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
        logger.error(f"Error de búsqueda web: {e}")
        return f"Error al buscar: {e}"
