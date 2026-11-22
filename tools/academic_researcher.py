import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict
from .base_tool import BaseTool


class AcademicResearcherTool(BaseTool):
    @property
    def name(self) -> str:
        return "academic_researcher"

    @property
    def description(self) -> str:
        return "Searches ArXiv papers and retrieves abstracts."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "ArXiv search query."},
                "max_results": {"type": "integer", "description": "Maximum results (default 3)."},
            },
            "required": ["query"],
        }

    def execute(self, query: str, max_results: int = 3, **kwargs) -> Any:
        try:
            url = (
                "https://export.arxiv.org/api/query?search_query=all:"
                f"{urllib.parse.quote(query)}&start=0&max_results={int(max_results)}"
            )
            response = urllib.request.urlopen(url, timeout=10).read()
            root = ET.fromstring(response)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            papers = []
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns).text.strip()
                summary = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
                published = entry.find("atom:published", ns).text
                link = entry.find("atom:id", ns).text
                papers.append(f"Titel: {title}\nPubliziert: {published}\nLink: {link}\nAbstract: {summary}\n")
            if not papers:
                return "Keine akademischen Publikationen gefunden."
            return "Wissenschaftliche Ergebnisse:\n\n" + "\n---\n".join(papers)
        except Exception as e:
            return f"Fehler beim Durchsuchen akademischer Datenbanken: {str(e)}"
