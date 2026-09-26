"""Auditor lingüístico y de narrativa de videojuegos usando Gemini 3.8 Flash e Interactions API."""

from __future__ import annotations

import json
import os
import re
from typing import Any
from google import genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Modelo oficial actual de Google
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-3.8-flash")

SYSTEM_INSTRUCTION = """
Eres un auditor experto de control de calidad lingüística (QA), especializado en narrativa y localización de videojuegos para el mercado hispanohablante.
El auditor humano que lee tu reporte NO tiene conocimientos de videojuegos.

Analiza el texto suministrado y detecta los elementos en estas 7 categorías exactas:
1. "Título de videojuego": Títulos de obras y sagas completos (ej: "Horizon Zero Dawn", "The Legend of Zelda: Breath of the Wild"). NO los fragmentes en palabras sueltas.
2. "Personaje / Entidad de ficción": Nombres de personajes ficticios (ej: "Aloy", "Ganon", "Mario", "Sephiroth").
3. "Lugar / Universo de ficción": Mundos, reinos, regiones o planetas ficticios (ej: "Hyrule", "Midgar", "Azeroth").
4. "Jerga de videojuegos": Mecánicas, términos técnicos del medio o adaptaciones de la comunidad (ej: "crafteo", "farmeo", "lore", "gameplay", "spawn", "build").
5. "Ortografia": Faltas de ortografía o tildes reales en español (ej: "consitente" -> "consistente", "tendra" -> "tendrá"). NUNCA marques un personaje o videojuego como falta ortográfica.
6. "Gramatica / Puntuacion": Errores de concordancia, sintaxis o puntuación.
7. "Extranjerismo no adaptado": Términos generales ajenos al español no exclusivos de videojuegos (ej: "meeting", "feedback", "backend").

Para CADA elemento devuelve:
- "text": Fragmento textual EXACTO tal como aparece en el texto.
- "category": Una de las 7 categorías anteriores.
- "description": Explicación enciclopédica clara (ej. juego: desarrolladora, año y temática; personaje: rol e historia; jerga: definición).
- "rae_rule": Norma ortotipográfica según RAE / FundéuRAE:
    * Videojuegos: Deben escribirse en CURSIVA (itálica). En español solo la primera palabra y nombres propios llevan mayúscula (*Horizon zero dawn*); si se conserva el título original en inglés con mayúsculas, siempre en CURSIVA (*Horizon Zero Dawn*), nunca en redonda sin comillas.
    * Personajes y lugares: Nombres propios que van en LETRA REDONDA (sin cursivas ni comillas) con mayúscula inicial.
    * Jerga/préstamos: Si es extranjerismo crudo (ej: gameplay) en cursiva o sustituto patrimonial (jugabilidad); si es adaptación flexiva (crafteo), explicar si se admite en la jerga o sugerir alternativa formal (fabricación).
- "recommended": La sustitución recomendada o grafía correcta con cursiva (ej: "*Horizon Zero Dawn*", "Aloy", "fabricación / creación", "consistente").
- "source": Fuente consultada (ej: "RAE / Ortografía académica", "FundéuRAE", "Wikipedia").
- "source_url": Enlace web de referencia (si existe, o cadena vacía).

DEBES responder ÚNICAMENTE con un JSON con la estructura:
{
  "findings": [
    {
      "text": "...",
      "category": "...",
      "description": "...",
      "rae_rule": "...",
      "recommended": "...",
      "source": "...",
      "source_url": "..."
    }
  ]
}
"""


def _extraer_texto_interaccion(interaction: Any) -> str:
    """Extrae el texto de salida del nuevo formato Interactions API de Gemini."""
    if hasattr(interaction, "output_text") and interaction.output_text:
        return interaction.output_text
    if hasattr(interaction, "steps") and interaction.steps:
        ultimo = interaction.steps[-1]
        if hasattr(ultimo, "text") and ultimo.text:
            return ultimo.text
        if hasattr(ultimo, "content") and ultimo.content:
            parte = ultimo.content[0]
            if hasattr(parte, "text"):
                return parte.text
            return str(parte)
    return str(interaction)


def auditar_con_gemini(text: str) -> list[dict[str, Any]]:
    """Envía el texto a Gemini 3.8 Flash usando client.interactions.create."""
    if not text.strip():
        return []

    api_key = GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Falta la variable de entorno GEMINI_API_KEY en tu archivo .env.")

    client = genai.Client(api_key=api_key)

    prompt = f"Analiza exhaustivamente el siguiente texto:\n\n\"\"\"\n{text}\n\"\"\""

    # Llamada con la nueva Interactions API requerida por Gemini 3.8 Flash
    interaction = client.interactions.create(
        model=GEMINI_MODEL,
        input=prompt,
        system_instruction=SYSTEM_INSTRUCTION,
        response_format={"type": "text", "mime_type": "application/json"},
        generation_config={
            "max_output_tokens": 16384,
            "thinking_level": "low",  # 'low' brinda respuestas rápidas y estructuradas
        },
    )

    raw_text = _extraer_texto_interaccion(interaction).strip()

    # Limpiar bloques markdown si vinieran incluidos (```json ... ```)
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text)

    # Extraer el JSON
    match_json = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if match_json:
        raw_text = match_json.group(0)

    try:
        data = json.loads(raw_text)
        raw_findings = data.get("findings", [])
    except Exception as exc:
        raise RuntimeError(f"Error procesando respuesta JSON de Gemini: {exc}") from exc

    # Mapear los hallazgos a los offsets del texto original
    errores: list[dict[str, Any]] = []
    tramos_ocupados: list[tuple[int, int]] = []

    # Ordenar por longitud descendente para que títulos largos se capturen primero
    raw_findings.sort(key=lambda x: len(x.get("text", "")), reverse=True)

    for item in raw_findings:
        palabra = item.get("text", "").strip()
        if not palabra:
            continue

        patron = re.compile(re.escape(palabra), re.IGNORECASE)
        for m in patron.finditer(text):
            ini, fin = m.start(), m.end()

            # Evitar solapamientos
            if any(ini < ocup_fin and fin > ocup_ini for ocup_ini, ocup_fin in tramos_ocupados):
                continue

            tramos_ocupados.append((ini, fin))

            cat = item.get("category", "Ortografia")
            desc = item.get("description", "")
            rae = item.get("rae_rule", "")
            recom = item.get("recommended", "")

            errores.append({
                "category": cat,
                "text": text[ini:fin],
                "message": f"{desc} | {rae}",
                "suggestions": [recom] if recom else [],
                "offset": ini,
                "length": fin - ini,
                "rule_id": f"GEMINI_{cat.upper().replace(' ', '_')}",
                "source": item.get("source", "Auditoría Gemini 3.8"),
                "lookup": {
                    "term": palabra,
                    "category": cat,
                    "definition": desc,
                    "rae_rule": rae,
                    "recommended": recom,
                    "source": item.get("source", "Análisis Gemini 3.8"),
                    "source_url": item.get("source_url", ""),
                    "found": True,
                },
            })

    return sorted(errores, key=lambda x: x["offset"])