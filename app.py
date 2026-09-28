"""Aplicación Flask para auditoría de textos y narrativa con Google Gemini."""

from __future__ import annotations

import os
from collections import Counter
import traceback
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
    except Exception as exc:
        print("\n" + "="*50)
        print("❌ ERROR EN AUDITAR_CON_GEMINI:")
        traceback.print_exc()
        print("="*50 + "\n")
        
        error_str = str(exc).lower()
        # Detectar si el error es por saturación o límites de cuota de Google
        es_saturacion = any(k in error_str for k in [
            "overloaded", "demanda", "503", "429", "resource_exhausted", 
            "unavailable", "rate limit", "quota", "temporarily"
        ])

        if es_saturacion:
            return jsonify({
                "error": "Los servidores de Google Gemini están experimentando alta demanda momentánea. Por favor, espera 1 o 2 minutos y vuelve a pulsar 'Analizar texto'.",
                "is_overloaded": True
            }), 503

        return jsonify({"error": str(exc)}), 500

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