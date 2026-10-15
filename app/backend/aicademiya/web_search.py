"""Tavily search for public-topic grounding; never receives a workspace or model key."""
from urllib.parse import urlsplit

import httpx
from .service_settings import effective_search_settings

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search public web sources for current facts, requested external evidence or missing course context. Use public-topic keywords only; never include personal details, credentials or private course text.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "A concise public-topic query, 1–400 characters.", "minLength": 1, "maxLength": 400}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}
MAX_SEARCHES = 2
MAX_RESULTS = 5


class SearchFailure(Exception):
    pass


def search_status(conn=None):
    settings = effective_search_settings(conn)
    return {"enabled": settings["enabled"], "configured": bool(settings["api_key"]), "provider": "tavily"}


def safe_web_url(value):
    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value)
        return url.scheme in {"https", "http"} and bool(url.hostname) and not url.username and not url.password
    except ValueError:
        return False


class TavilySearch:
    def __init__(self, transport=None):
        self.transport = transport

    def search(self, query, *, api_key=None):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 400:
            raise SearchFailure("Web search requires a query of 1–400 characters.")
        # App callers pass their effective DB/environment snapshot explicitly.
        # None preserves the standalone probe/adapter's environment fallback.
        key = effective_search_settings()["api_key"] if api_key is None else api_key
        if not key:
            raise SearchFailure("Web search is enabled but TAVILY_API_KEY is not configured.")
        try:
            with httpx.Client(timeout=httpx.Timeout(25, connect=10), transport=self.transport,
                              follow_redirects=False) as client:
                response = client.post("https://api.tavily.com/search", headers={"Authorization": "Bearer " + key},
                                       json={"query": query.strip(), "topic": "general", "search_depth": "basic",
                                             "auto_parameters": False, "max_results": MAX_RESULTS,
                                             "include_answer": False, "include_raw_content": False,
                                             "include_images": False, "include_usage": True})
            if response.status_code != 200:
                # Do not echo provider bodies/headers (they may contain secrets).
                raise SearchFailure(f"Tavily search returned HTTP {response.status_code}. Check search credentials/quota and retry; your work remains saved.")
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                raise ValueError("invalid results")
            results = []
            seen = set()
            for row in data["results"]:
                if not isinstance(row, dict) or not safe_web_url(row.get("url")) or row["url"] in seen:
                    continue
                if not isinstance(row.get("content"), str) or not row["content"].strip():
                    continue
                seen.add(row["url"])
                results.append({"title": str(row.get("title") or row["url"])[:300],
                                "url": row["url"], "content": row["content"][:1800]})
                if len(results) == MAX_RESULTS:
                    break
            return {"query": query.strip(), "results": results, "usage": data.get("usage")}
        except httpx.TimeoutException:
            raise SearchFailure("Tavily search timed out. Your work remains saved; retry later.") from None
        except httpx.RequestError:
            raise SearchFailure("Cannot reach Tavily search. Your work remains saved; check the network.") from None
        except (ValueError, TypeError, KeyError):
            raise SearchFailure("Tavily returned an invalid search response. Your work remains saved.") from None


def web_citations(sources):
    """Always retain retrieved links; never depend on the model remembering citations."""
    return [{"source_label": f"[{s['id']}] {s['title']}", "url": s["url"],
             "text": s["content"], "kind": "web"}
            for s in sources]
