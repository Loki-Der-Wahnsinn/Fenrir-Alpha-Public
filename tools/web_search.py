import json
import os
import urllib.parse
from typing import Any, Dict
import requests
from .base_tool import BaseTool

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None


class WebSearchTool(BaseTool):
    def __init__(self, workspace_root: str = None):
        self.workspace_root = workspace_root or os.getcwd()

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Searches public web sources via DuckDuckGo."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
            },
            "required": ["query"],
        }

    def execute(self, query: str, **kwargs) -> Any:
        cache_file = os.path.join(self.workspace_root, "memory", "web_search_history.json")
        history = []
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []

        if query in history:
            return f"Fehler: Suchanfrage '{query}' wurde bereits im aktuellen Cache ausgefuehrt."

        history.append(query)
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(history[-200:], f)
        except Exception:
            pass

        if DDGS is not None:
            try:
                with DDGS(timeout=15) as ddgs:
                    results = list(ddgs.text(query, max_results=8))
                    if results:
                        formatted = []
                        for r in results:
                            formatted.append(f"Titel: {r['title']}\nLink: {r['href']}\nSnippet: {r['body']}\n---")
                        return "\n".join(formatted)[:6000]
            except Exception:
                pass

        browse_url = os.environ.get("FENRIR_BROWSE_URL", "").strip()
        if browse_url:
            try:
                url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                resp = requests.post(browse_url, json={"url": url}, timeout=45)
                if resp.status_code == 200:
                    return resp.json().get("text", "")[:5000] or "Keine Ergebnisse gefunden."
            except Exception as e:
                return f"Fehler bei Web-Suche: {e}"

        return "Keine Ergebnisse gefunden (DuckDuckGo nicht verfuegbar oder leer)."
