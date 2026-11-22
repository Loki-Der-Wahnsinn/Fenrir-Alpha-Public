from .agent_base import Agent


def init_frontal_cortex(core) -> dict:
    """Initializes planning-layer agents."""
    return {
        "ReflexionNode": Agent(
            "ReflexionNode",
            "Fehler- und Prompt-Analyst",
            "Analysiere Fehler (Friction-Reports) des Systems und schlage klarere Arbeitsanweisungen vor.",
            core,
            model_name=core.master_model,
            keep_alive="10m",
        ),
        "SelfArchitect": Agent(
            "SelfArchitect",
            "System-Architekt",
            "Analysiere bestehende Module und plane Verbesserungen oder die Nutzung gepruefter Skills. Markiere Skill-Ausfuehrungen mit [ACTION_REQUIRED].",
            core,
            model_name=core.master_model,
            keep_alive="10m",
        ),
        "GarbageCollector": Agent(
            "GarbageCollector",
            "Struktur-Archivar",
            "Analysiere aeltere Skills, erkenne Redundanzen und schlage Konsolidierungen vor.",
            core,
            model_name=core.master_model,
            keep_alive="10m",
        ),
        "ForesightNode": Agent(
            "ForesightNode",
            "Kapazitaets-Planer",
            "Beobachte die aktuelle Systemauslastung und schlage passende naechste Arbeitspakete vor.",
            core,
            model_name=core.master_model,
            keep_alive="10m",
        ),
    }
