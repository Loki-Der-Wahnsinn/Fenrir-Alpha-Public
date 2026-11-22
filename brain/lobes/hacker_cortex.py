from .agent_base import Agent


def init_hacker_cortex(core) -> dict:
    """Initializes execution, review, and repair agents."""
    return {
        "NewsScout": Agent(
            "NewsScout",
            "Technischer Recherche-Agent",
            "Recherchiere technische Dokumentationen und Architekturkonzepte.",
            core,
            model_name=core.coder_model,
            keep_alive="10m",
        ),
        "Evoluer": Agent(
            "Evoluer",
            "Modul-Implementierer",
            "Implementiere geplante Python-Module objektorientiert und gib vollstaendiges JSON mit syntaktisch korrektem Python-Code im Feld 'code' zurueck.",
            core,
            model_name=core.coder_model,
            keep_alive="10m",
        ),
        "Guardian": Agent(
            "Guardian",
            "Integritaets-Waechter",
            "Pruefe generierten Code auf Syntax- und Sicherheitsfehler. Antworte kurz mit APPROVE oder Ablehnungsgrund.",
            core,
            model_name="scout",
            keep_alive="10m",
        ),
        "Debugger": Agent(
            "Debugger",
            "Fehler-Kompensator",
            "Analysiere Fehlermeldungen aus der lokalen Sandbox und korrigiere den Python-Code.",
            core,
            model_name="scout",
            keep_alive="10m",
        ),
        "DreamerNode": Agent(
            "DreamerNode",
            "Konzept-Synthetisierer",
            "Formuliere kompakte technische Hypothesen fuer kuenftige Verbesserungszyklen.",
            core,
            model_name=core.coder_model,
            keep_alive="10m",
        ),
        "OperatorNode": Agent(
            "OperatorNode",
            "Execution Coordinator",
            "Generiere JSON-Payloads fuer 'execute_skill', um bereits gepruefte Skills innerhalb des Workspace auszufuehren.",
            core,
            model_name=core.coder_model,
            keep_alive="10m",
        ),
    }
