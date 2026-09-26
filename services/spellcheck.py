"""Auditoria determinista de ortografia, gramatica, extranjerismos y narrativa de videojuegos."""

from __future__ import annotations

import os
import re
from typing import Any

from services.lexicon import (
    es_probable_extranjerismo,
    esta_protegido,
    sin_tildes,
    zonas_protegidas,
)

# Categorias reconocidas por el sistema
CAT_VIDEOJUEGO = "Título de videojuego"
CAT_PERSONAJE = "Personaje / Entidad de ficción"
CAT_JERGA_GAMER = "Jerga de videojuegos"
CAT_ORTOGRAFIA = "Ortografia"
CAT_GRAMATICA = "Gramatica / Puntuacion"
CAT_EXTRANJERISMO = "Extranjerismo no adaptado"
CAT_TECNICISMO = "Tecnicismo"

# Prioridad al deduplicar solapamientos (gana el número más alto)
_PRIORIDAD = {
    CAT_VIDEOJUEGO: 10,
    CAT_PERSONAJE: 9,
    CAT_JERGA_GAMER: 8,
    CAT_TECNICISMO: 4,
    CAT_EXTRANJERISMO: 3,
    CAT_ORTOGRAFIA: 2,
    CAT_GRAMATICA: 1,
}

# Términos frecuentes en documentos de QA
FOREIGN_TERMS: dict[str, tuple[str, str]] = {
    "backend": ("parte del servidor", "Extranjerismo técnico no adaptado; puede sustituirse por 'parte del servidor'."),
    "backlog": ("lista de trabajo pendiente", "Terminología de gestión de producto en inglés."),
    "brainstorming": ("lluvia de ideas", "Extranjerismo no adaptado; existe una expresión equivalente en español."),
    "deadline": ("fecha límite", "Extranjerismo no adaptado; existe una expresión equivalente en español."),
    "deploy": ("despliegue", "Extranjerismo técnico no adaptado; se recomienda 'despliegue'."),
    "feedback": ("retroalimentación", "Extranjerismo no adaptado; existe una expresión equivalente en español."),
    "framework": ("marco de trabajo", "Extranjerismo técnico no adaptado; se recomienda 'marco de trabajo'."),
    "meeting": ("reunión", "Extranjerismo no adaptado; existe una expresión equivalente en español."),
    "online": ("en línea", "Extranjerismo no adaptado; existe una expresión equivalente en español."),
    "debug": ("depuración", "Extranjerismo técnico no adaptado; se recomienda 'depuración'."),
    "sprint": ("iteración", "Extranjerismo no adaptado en este contexto; se recomienda 'iteración'."),
    "startup": ("empresa emergente", "Extranjerismo no adaptado; existe una expresión equivalente en español."),
    "team": ("equipo", "Extranjerismo no adaptado; existe una expresión equivalente en español."),
    "webinar": ("seminario web", "Extranjerismo no adaptado; existe una expresión equivalente en español."),
}

_FOREIGN_PATTERN = re.compile(
    r"\b(?:" + "|".join(map(re.escape, FOREIGN_TERMS)) + r")\b", re.IGNORECASE
)

LOCAL_SPELLING: dict[str, tuple[str, str]] = {
    "analisis": ("análisis", "Falta la tilde en una palabra esdrújula."),
    "consitente": ("consistente", "La palabra está mal escrita."),
    "consitentes": ("consistentes", "La palabra está mal escrita."),
    "correcion": ("corrección", "Falta la tilde en la palabra."),
    "espaniol": ("español", "La palabra está mal escrita."),
    "ortografico": ("ortográfico", "Falta la tilde en la palabra."),
    "parrafo": ("párrafo", "Falta la tilde en la palabra."),
    "sofware": ("software", "La palabra está mal escrita."),
    "tecnolojia": ("tecnología", "La palabra está mal escrita."),
    "tendra": ("tendrá", "Falta la tilde en la forma verbal."),
    "herror": ("error", "La palabra está mal escrita."),
}

_LOCAL_SPELLING_PATTERN = re.compile(
    r"\b(?:" + "|".join(map(re.escape, LOCAL_SPELLING)) + r")\b", re.IGNORECASE
)

_LOCAL_GRAMMAR_RULES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (
        re.compile(r"\bLos resultado\b", re.IGNORECASE),
        "Los resultados",
        "El sustantivo debe concordar en número con el determinante plural.",
    ),
    (
        re.compile(r"\bLas resultado\b", re.IGNORECASE),
        "Los resultados",
        "La concordancia nominal requiere revisar género y número.",
    ),
)

TECHNICAL_TERMS: set[str] = {
    "algoritmo", "API", "base de datos", "ciberseguridad", "depuracion",
    "inteligencia artificial", "servidor", "software", "hardware", "navegador",
    "repositorio", "interfaz", "protocolo", "endpoint", "framework", "commit",
    "contenedor", "microservicio", "criptografia", "latencia", "middleware",
}


def _category(match: Any) -> str:
    rule_id = str(_match_attribute(match, "rule_id", "ruleId", "")).upper()
    issue_type = str(_match_attribute(match, "issue_type", "issueType", "")).lower()
    if any(token in rule_id for token in ("FOREIGN", "ENGLISH", "ANGLICISM")):
        return CAT_EXTRANJERISMO
    if issue_type in {"misspelling", "typographical", "spelling"} or "TYPO" in rule_id or "MORFOLOGIK" in rule_id:
        return CAT_ORTOGRAFIA
    return CAT_GRAMATICA


def _match_to_error(match: Any) -> dict[str, Any]:
    replacements = list(_match_attribute(match, "replacements", "replacements", []) or [])
    return {
        "category": _category(match),
        "text": str(_match_attribute(match, "matched_text", "matchedText", "")),
        "message": str(_match_attribute(match, "message", "message", "Regla incumplida.")),
        "suggestions": replacements[:5],
        "offset": int(_match_attribute(match, "offset", "offset", 0)),
        "length": int(_match_attribute(match, "error_length", "errorLength", 0)),
        "rule_id": str(_match_attribute(match, "rule_id", "ruleId", "")),
        "source": "LanguageTool",
    }


def _match_attribute(match: Any, snake_name: str, camel_name: str, default: Any) -> Any:
    value = getattr(match, snake_name, None)
    return value if value is not None else getattr(match, camel_name, default)


def _foreign_errors(text: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for found in _FOREIGN_PATTERN.finditer(text):
        term = found.group(0)
        replacement, reason = FOREIGN_TERMS[term.lower()]
        errors.append({
            "category": CAT_EXTRANJERISMO,
            "text": term,
            "message": reason,
            "suggestions": [replacement],
            "offset": found.start(),
            "length": len(term),
            "rule_id": "QA_FOREIGN_TERM",
            "source": "Regla QA determinista",
        })
    return errors


def _local_rule_errors(text: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for found in _LOCAL_SPELLING_PATTERN.finditer(text):
        term = found.group(0)
        replacement, reason = LOCAL_SPELLING[term.lower()]
        errors.append({
            "category": CAT_ORTOGRAFIA,
            "text": term,
            "message": reason,
            "suggestions": [replacement],
            "offset": found.start(),
            "length": len(term),
            "rule_id": "QA_LOCAL_SPELLING",
            "source": "Reglas QA locales",
        })
    for pattern, replacement, reason in _LOCAL_GRAMMAR_RULES:
        for found in pattern.finditer(text):
            errors.append({
                "category": CAT_GRAMATICA,
                "text": found.group(0),
                "message": reason,
                "suggestions": [replacement],
                "offset": found.start(),
                "length": len(found.group(0)),
                "rule_id": "QA_LOCAL_AGREEMENT",
                "source": "Reglas QA locales",
            })
    return errors


def _terminos_registrados() -> set[str]:
    from services.dictionary_lookup import terminos_glosario
    registrados = {sin_tildes(t.lower()) for t in terminos_glosario()}
    registrados |= {sin_tildes(t.lower()) for t in TECHNICAL_TERMS}
    return registrados


def _reclasificar(error: dict[str, Any], registrados: set[str]) -> dict[str, Any] | None:
    if error["category"] != CAT_ORTOGRAFIA:
        return error
    palabra = error["text"].strip()
    clave = sin_tildes(palabra.lower())
    if clave in registrados:
        error.update({
            "category": CAT_TECNICISMO,
            "message": "Tecnicismo registrado. Se documenta, no se corrige.",
            "suggestions": [],
            "rule_id": "QA_TECNICISMO_REGISTRADO",
            "source": "Glosario QA",
        })
        return error
    es_extranjero, razones = es_probable_extranjerismo(palabra)
    if es_extranjero:
        error.update({
            "category": CAT_EXTRANJERISMO,
            "message": "Voz no adaptada al español: " + "; ".join(razones) + ".",
            "suggestions": [],
            "rule_id": "QA_EXTRANJERISMO_MORFOLOGICO",
            "source": "Análisis morfológico QA",
        })
        return error
    if not error.get("suggestions"):
        return None
    return error


_PALABRA = re.compile(r"\b[A-Za-z\u00c0-\u017f]{3,}\b")


def _extranjerismos_morfologicos(
    text: str, zonas: list[tuple[int, int]], registrados: set[str]
) -> list[dict[str, Any]]:
    hallazgos: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for found in _PALABRA.finditer(text):
        palabra = found.group(0)
        clave = sin_tildes(palabra.lower())
        if clave in FOREIGN_TERMS or clave in LOCAL_SPELLING:
            continue
        if esta_protegido(found.start(), len(palabra), zonas):
            continue
        es_extranjero, razones = es_probable_extranjerismo(palabra)
        if not es_extranjero:
            continue
        categoria = CAT_TECNICISMO if clave in registrados else CAT_EXTRANJERISMO
        hallazgos.append({
            "category": categoria,
            "text": palabra,
            "message": "Voz no adaptada al español: " + "; ".join(razones) + ".",
            "suggestions": [],
            "offset": found.start(),
            "length": len(palabra),
            "rule_id": "QA_EXTRANJERISMO_MORFOLOGICO",
            "source": "Análisis morfológico QA",
        })
        vistos.add(clave)
    return hallazgos


def audit_text(text: str) -> list[dict[str, Any]]:
    """Audita el texto protegiendo primero entidades de videojuegos y personajes."""
    if not text or not text.strip():
        return []

    zonas = zonas_protegidas(text)
    registrados = _terminos_registrados()

    # 1. Deteccion de videojuegos, personajes y jerga gaming
    hallazgos_gaming: list[dict[str, Any]] = []
    try:
        from services.game_entities import analizar_entidades_y_jerga
        hallazgos_gaming = analizar_entidades_y_jerga(text)
    except ImportError:
        hallazgos_gaming = []

    # Proteger los tramos de las entidades para que LanguageTool no las fragmente
    zonas_ampliadas = list(zonas)
    for ent in hallazgos_gaming:
        zonas_ampliadas.append((ent["offset"], ent["offset"] + ent["length"]))

    matches: list[dict[str, Any]] = []
    try:
        import language_tool_python
        use_local = os.getenv("QA_USE_LOCAL_LANGUAGETOOL", "0") == "1"
        remote_server = os.getenv("LANGUAGETOOL_SERVER", "https://api.languagetool.org/")
        tool = language_tool_python.LanguageTool("es") if use_local else language_tool_python.LanguageTool("es", remote_server=remote_server)
        try:
            matches = [_match_to_error(m) for m in tool.check(text)]
        finally:
            close = getattr(tool, "close", None)
            if callable(close):
                close()
    except Exception:
        matches = []

    # Omitir lo que caiga en zonas protegidas o dentro de títulos de videojuegos
    matches = [m for m in matches if not esta_protegido(m["offset"], m["length"], zonas_ampliadas)]

    revisados: list[dict[str, Any]] = []
    for match in matches:
        resultado = _reclasificar(match, registrados)
        if resultado is not None:
            revisados.append(resultado)

    propios = [
        e for e in (_local_rule_errors(text)
                    + _foreign_errors(text)
                    + _extranjerismos_morfologicos(text, zonas_ampliadas, registrados))
        if not esta_protegido(e["offset"], e["length"], zonas_ampliadas)
    ]

    todos = hallazgos_gaming + revisados + propios
    return _dedup_por_solapamiento(todos)


def _dedup_por_solapamiento(errores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordenados = sorted(
        errores,
        key=lambda e: (-_PRIORIDAD.get(e["category"], 0), e["offset"], -e["length"]),
    )
    finales: list[dict[str, Any]] = []
    for error in ordenados:
        ini, fin = error["offset"], error["offset"] + error["length"]
        if any(ini < f and fin > i for i, f in ((x["offset"], x["offset"] + x["length"]) for x in finales)):
            continue
        finales.append(error)
    return sorted(finales, key=lambda e: (e["offset"], e["length"]))