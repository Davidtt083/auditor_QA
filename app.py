"""Aplicación Flask para auditoría de textos y narrativa con Google Gemini."""

from __future__ import annotations

import os
from collections import Counter
from typing import Any

from dotenv import load_dotenv  # <--- 1. IMPORTAR ESTO
load_dotenv()  

from flask import Flask, jsonify, render_template, request

from services.gemini_auditor import auditar_con_gemini

app = Flask(__name__)


def _annotations(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extrae las anotaciones y fichas de los errores detectados."""
    annotations: list[dict[str, Any]] = []
    for error in errors:
        if error.get("lookup"):
            annotations.append({
                "type": "term",
                "text": error["text"],
                "offset": error["offset"],
                "length": error["length"],
                "category": error["category"],
                "lookup": error["lookup"],
            })
    return sorted(annotations, key=lambda item: item["offset"])


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
        return jsonify({"error": "El texto supera el límite de 100.000 caracteres."}), 413

    try:
        errors = auditar_con_gemini(text)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        return jsonify({"error": f"Error inesperado al auditar: {exc}"}), 500

    counts = Counter(error["category"] for error in errors)
    return jsonify({
        "text": text,
        "errors": errors,
        "annotations": _annotations(errors),
        "counts": {
            "Videojuegos": counts.get("Título de videojuego", 0),
            "Personajes / Ficción": counts.get("Personaje / Entidad de ficción", 0) + counts.get("Lugar / Universo de ficción", 0),
            "Jerga gaming": counts.get("Jerga de videojuegos", 0),
            "Ortografia": counts.get("Ortografia", 0),
            "Gramatica / Puntuacion": counts.get("Gramatica / Puntuacion", 0),
            "Extranjerismos": counts.get("Extranjerismo no adaptado", 0),
            "total": len(errors),
        },
    })


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)