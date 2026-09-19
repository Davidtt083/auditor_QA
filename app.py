"""Aplicacion Flask para auditoria determinista de textos."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from services.dictionary_lookup import lookup_term
from services.spellcheck import FOREIGN_TERMS, audit_text

app = Flask(__name__)

TECHNICAL_TERMS = {
    "API",
    "algoritmo",
    "base de datos",
    "ciberseguridad",
    "depuración",
    "frontend",
    "inteligencia artificial",
    "software",
    "servidor",
}


def _candidate_terms(text: str, errors: list[dict[str, Any]]) -> list[str]:
    terms = {error["text"] for error in errors if error["category"] == "Extranjerismo no adaptado"}
    terms.update(TECHNICAL_TERMS)
    terms.update(FOREIGN_TERMS)
    glossary_path = Path(__file__).with_name("glosario.json")
    if glossary_path.exists():
        import json
        with glossary_path.open(encoding="utf-8") as glossary_file:
            terms.update(entry.get("term", key) for key, entry in json.load(glossary_file).items())
    # Solo palabras marcadas por reglas o glosario se consultan externamente.
    return sorted(term for term in terms if term and re.search(r"\w", term))


def _annotations(text: str, errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    for term in _candidate_terms(text, errors):
        result = lookup_term(term)
        for match in re.finditer(re.escape(term), text, flags=re.IGNORECASE):
            annotations.append({
                "type": "term",
                "text": match.group(0),
                "offset": match.start(),
                "length": len(match.group(0)),
                "lookup": result,
            })
    return annotations


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/analyze")
def analyze():
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "")
    if not isinstance(text, str):
        return jsonify({"error": "El campo 'text' debe ser una cadena."}), 400
    if len(text) > 100_000:
        return jsonify({"error": "El texto supera el limite de 100.000 caracteres."}), 413

    try:
        errors = audit_text(text)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    counts = Counter(error["category"] for error in errors)
    return jsonify({
        "text": text,
        "errors": errors,
        "annotations": _annotations(text, errors),
        "counts": {
            "Ortografia": counts.get("Ortografia", 0),
            "Gramatica / Puntuacion": counts.get("Gramatica / Puntuacion", 0),
            "Extranjerismo no adaptado": counts.get("Extranjerismo no adaptado", 0),
            "total": len(errors),
        },
    })


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
