"""Auditoria determinista de ortografia, gramatica y extranjerismos."""

from __future__ import annotations

import os
import re
from typing import Any

# Terminos frecuentes en documentos de QA que no se consideran adaptados.
FOREIGN_TERMS: dict[str, tuple[str, str]] = {
    "backend": ("parte del servidor", "Extranjerismo técnico no adaptado; puede sustituirse por 'parte del servidor'."),
    "backlog": ("lista de trabajo pendiente", "Terminologia de gestion de producto en ingles."),
    "brainstorming": ("lluvia de ideas", "Extranjerismo no adaptado; existe una expresion equivalente en espanol."),
    "deadline": ("fecha limite", "Extranjerismo no adaptado; existe una expresion equivalente en espanol."),
    "deploy": ("despliegue", "Extranjerismo técnico no adaptado; se recomienda 'despliegue'."),
    "feedback": ("retroalimentacion", "Extranjerismo no adaptado; existe una expresion equivalente en espanol."),
    "framework": ("marco de trabajo", "Extranjerismo técnico no adaptado; se recomienda 'marco de trabajo'."),
    "meeting": ("reunion", "Extranjerismo no adaptado; existe una expresion equivalente en espanol."),
    "online": ("en linea", "Extranjerismo no adaptado; existe una expresion equivalente en espanol."),
    "debug": ("depuración", "Extranjerismo técnico no adaptado; se recomienda 'depuración'."),
    "sprint": ("iteracion", "Extranjerismo no adaptado en este contexto; se recomienda 'iteracion'."),
    "startup": ("empresa emergente", "Extranjerismo no adaptado; existe una expresion equivalente en espanol."),
    "team": ("equipo", "Extranjerismo no adaptado; existe una expresion equivalente en espanol."),
    "webinar": ("seminario web", "Extranjerismo no adaptado; existe una expresion equivalente en espanol."),
}

_FOREIGN_PATTERN = re.compile(
    r"\b(?:" + "|".join(map(re.escape, FOREIGN_TERMS)) + r")\b", re.IGNORECASE
)

# Respaldo local para el demo cuando la API publica alcanza su limite. Estas
# reglas son explicitas y auditables; no intentan adivinar palabras nuevas.
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


def _category(match: Any) -> str:
    """Mapea una coincidencia de LanguageTool a una categoria de QA."""
    rule_id = str(_match_attribute(match, "rule_id", "ruleId", "")).upper()
    issue_type = str(_match_attribute(match, "issue_type", "issueType", "")).lower()
    if any(token in rule_id for token in ("FOREIGN", "ENGLISH", "ANGLICISM")):
        return "Extranjerismo no adaptado"
    if issue_type in {"misspelling", "typographical", "spelling"} or "TYPO" in rule_id or "MORFOLOGIK" in rule_id:
        return "Ortografia"
    return "Gramatica / Puntuacion"


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
    """Lee respuestas camelCase y snake_case de distintas versiones del paquete."""
    value = getattr(match, snake_name, None)
    if value is not None:
        return value
    return getattr(match, camel_name, default)


def _foreign_errors(text: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for found in _FOREIGN_PATTERN.finditer(text):
        term = found.group(0)
        replacement, reason = FOREIGN_TERMS[term.lower()]
        errors.append({
            "category": "Extranjerismo no adaptado",
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
            "category": "Ortografia",
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
                "category": "Gramatica / Puntuacion",
                "text": found.group(0),
                "message": reason,
                "suggestions": [replacement],
                "offset": found.start(),
                "length": len(found.group(0)),
                "rule_id": "QA_LOCAL_AGREEMENT",
                "source": "Reglas QA locales",
            })
    return errors


def audit_text(text: str) -> list[dict[str, Any]]:
    """Devuelve hallazgos ordenados por posicion, sin generar texto nuevo."""
    if not text or not text.strip():
        return []

    try:
        import language_tool_python
    except ImportError as exc:
        raise RuntimeError("Instala las dependencias de requirements.txt antes de analizar.") from exc

    # El servidor remoto usa el mismo motor de reglas sin descargar ni iniciar
    # una JVM, por lo que funciona en PythonAnywhere Free.
    use_local = os.getenv("QA_USE_LOCAL_LANGUAGETOOL", "0") == "1"
    remote_server = os.getenv("LANGUAGETOOL_SERVER", "https://api.languagetool.org/")

    matches: list[dict[str, Any]] = []
    try:
        if use_local:
            tool = language_tool_python.LanguageTool("es")
        else:
            tool = language_tool_python.LanguageTool("es", remote_server=remote_server)
        try:
            matches = [_match_to_error(match) for match in tool.check(text)]
        finally:
            close = getattr(tool, "close", None)
            if callable(close):
                close()
    except Exception:
        # El demo sigue siendo util si la API publica esta temporalmente
        # limitada: las reglas QA locales no dependen de red ni de Java.
        matches = []

    errors = matches + _local_rule_errors(text) + _foreign_errors(text)
    unique: dict[tuple[int, int, str], dict[str, Any]] = {}
    for error in errors:
        key = (error["offset"], error["length"], error["category"])
        if key not in unique or unique[key]["source"] != "LanguageTool":
            unique[key] = error
    return sorted(unique.values(), key=lambda item: (item["offset"], item["length"]))
