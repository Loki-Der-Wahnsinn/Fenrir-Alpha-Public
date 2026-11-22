import urllib.parse
import urllib.request
from typing import Any, Dict
from .base_tool import BaseTool


class WebScraperTool(BaseTool):
    @property
    def name(self) -> str:
        return "web_scrape"

    @property
    def description(self) -> str:
        return "Fetches an HTTP/HTTPS web page and extracts plain text."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "HTTP or HTTPS target URL."},
            },
            "required": ["url"],
        }

    def execute(self, url: str, **kwargs) -> Any:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return "Fehler: Nur http/https URLs sind erlaubt."
        try:
            from bs4 import BeautifulSoup

            req = urllib.request.Request(url, headers={"User-Agent": "Fenrir-Research/1.0"})
            html = urllib.request.urlopen(req, timeout=15).read()
            soup = BeautifulSoup(html, "html.parser")
            for script in soup(["script", "style"]):
                script.extract()
            return soup.get_text(separator=" ", strip=True)[:20000]
        except Exception as e:
            return f"Fehler beim Web-Scraping: {str(e)}"
