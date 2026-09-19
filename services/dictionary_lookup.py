"""Consulta factual en cascada: glosario local, RAE y Wikipedia."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

BASE_DIR = Path(__file__).resolve().parent.parent
GLOSSARY_PATH = BASE_DIR / "glosario.json"


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


@lru_cache(maxsize=1)
def _load_glossary() -> dict[str, Any]:
    if not GLOSSARY_PATH.exists():
        return {}
    with GLOSSARY_PATH.open(encoding="utf-8") as glossary_file:
        return json.load(glossary_file)


def _glossary_lookup(term: str) -> dict[str, Any] | None:
    key = _normalise(term)
    for glossary_key, entry in _load_glossary().items():
        if _normalise(glossary_key) == key:
            return {
                "term": entry.get("term", term),
                "definition": entry.get("definition", ""),
                "source": entry.get("source", "Glosario local"),
                "source_url": entry.get("source_url", ""),
            }
    return None


def _rae_lookup(term: str) -> dict[str, Any] | None:
    try:
        from pyrae import RAE
        rae = RAE()
        search = getattr(rae, "search", None) or getattr(rae, "buscar", None)
        if not callable(search):
            return None
        result = search(term)
        definition = _extract_definition(result)
        if definition:
            return {
                "term": term,
                "definition": definition,
                "source": "Real Academia Espanola (DLE)",
                "source_url": f"https://dle.rae.es/{quote(term)}",
            }
    except (ImportError, OSError, RuntimeError, TimeoutError, ValueError):
        return None
    return None


def _extract_definition(value: Any) -> str:
    """Extrae solo texto devuelto por pyrae, sin fabricar una definicion."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("definition", "definitions", "meaning", "text"):
            if key in value:
                extracted = _extract_definition(value[key])
                if extracted:
                    return extracted
    if isinstance(value, (list, tuple)):
        for item in value:
            extracted = _extract_definition(item)
            if extracted:
                return extracted
    for attribute in ("definition", "definitions", "meaning", "text"):
        if hasattr(value, attribute):
            extracted = _extract_definition(getattr(value, attribute))
            if extracted:
                return extracted
    return ""


def _wikipedia_lookup(term: str) -> dict[str, Any] | None:
    try:
        import wikipediaapi
        wiki = wikipediaapi.Wikipedia(
            user_agent="QA-Text-Auditor/1.0 (local deterministic tool)",
            language="es",
        )
        page = wiki.page(term)
        if page.exists() and page.summary.strip():
            return {
                "term": term,
                "definition": page.summary.strip(),
                "source": "Wikipedia en espanol",
                "source_url": page.fullurl,
            }
    except (ImportError, OSError, RuntimeError, TimeoutError, ValueError):
        return None
    return None


def lookup_term(term: str) -> dict[str, Any]:
    """Busca un termino y devuelve la primera fuente factual disponible."""
    cleaned = term.strip()
    if not cleaned:
        return {"term": term, "found": False, "source": "Sin consulta"}
    result = _glossary_lookup(cleaned) or _rae_lookup(cleaned) or _wikipedia_lookup(cleaned)
    if result:
        return {**result, "found": True}
    return {
        "term": cleaned,
        "found": False,
        "definition": "No se encontro una entrada en las fuentes configuradas.",
        "source": "Sin resultado factual",
        "source_url": "",
    }
