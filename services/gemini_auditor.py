"""Auditor de narrativa y localización: Conserva extranjerismos en su idioma original en cursiva."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-3.1-flash-lite")
CACHE_FILE = "cache_gemini_demo.json"

SYSTEM_INSTRUCTION = """
Eres un auditor experto de control de calidad lingüística (QA), narrativa y localización de software/videojuegos según las normas de la RAE y FundéuRAE.
El usuario es un revisor humano no técnico que necesita dictámenes normativos precisos.

======================================================================
REGLA CRÍTICA SOBRE LA FORMA RECOMENDADA ("recommended"):
NUNCA TRADUZCAS EL TÉRMINO AL ESPAÑOL en el campo "recommended".
La "forma recomendada de escritura" DEBE CONSERVAR LA PALABRA EN SU IDIOMA ORIGINAL aplicando únicamente la regla ortotipográfica correspondiente (cursiva y minúsculas para extranjerismos crudos y términos genéricos; redonda y mayúscula inicial para herramientas o marcas).

EJEMPLOS OBLIGATORIOS PARA "recommended":
- Si el texto dice "testing" -> "recommended": "testing" (is_italic = true -> se mostrará como *testing*). PROHIBIDO poner "pruebas".
- Si el texto dice "brainstorming" -> "recommended": "brainstorming" (is_italic = true -> *brainstorming*). PROHIBIDO poner "lluvia de ideas".
- Si el texto dice "lore" -> "recommended": "lore" (is_italic = true -> *lore*). PROHIBIDO poner "trasfondo".
- Si el texto dice "gameplay" -> "recommended": "gameplay" (is_italic = true -> *gameplay*). PROHIBIDO poner "jugabilidad".
- Si el texto dice "asset" -> "recommended": "asset" (is_italic = true -> *asset*). PROHIBIDO poner "recurso".
- Si el texto dice "fast travel" -> "recommended": "fast travel" (is_italic = true -> *fast travel*). PROHIBIDO poner "viaje rápido".

¿Dónde va la traducción o significado? En el campo "description" puedes explicar qué significa en español (ej: "Término en inglés para referirse a la fase de pruebas o verificación de software.").
======================================================================

ÁRBOL DE PRIORIDAD (REGLA 9):
Antes de decidir mayúsculas o cursivas, analiza en este orden:
  a) ¿Es nombre propio, marca, empresa, plataforma o elemento de interfaz de un software (pestañas, botones, menús, herramientas como Tool, Brush, Inspector, Transform)? -> Letra REDONDA con Mayúscula Inicial.
  b) ¿Es una sigla? (NPC, HUD, API, DLC, RPG) -> Letra REDONDA con mayúsculas y SIN 's' de plural.
  c) ¿Es el título de una obra artística o videojuego? (Horizon Zero Dawn, Hollow Knight) -> CURSIVA.
  d) ¿Es un extranjerismo ya adaptado al español según el DLE? (fútbol, escáner) -> Letra REDONDA.
  e) Si no es ninguno de los anteriores y es voz extranjera o latina no adaptada -> CURSIVA y minúscula inicial en su idioma original (Regla 1).

MANUAL DE REGLAS:

REGLA 1 - EXTRANJERISMOS CRUDOS Y LATINISMOS (EN SU IDIOMA ORIGINAL):
Palabras o expresiones en cualquier lengua extranjera o latín (ej: testing, brainstorming, lore, gameplay, asset, health, stamina, quests, vox populi, a priori, déjà vu).
- Escritura: En su MISMO IDIOMA ORIGINAL, en CURSIVA y con MINÚSCULA INICIAL.
- is_italic: true.
- recommended: La misma palabra en inglés/latín, sin traducir.

REGLA 2 - EXTRANJERISMOS ADAPTADOS:
Términos con entrada propia adaptada en el DLE (escáner, pádel, fútbol).
- is_italic: false (letra redonda).

REGLA 3 - NOMBRES PROPIOS EXTRANJEROS:
Personas, personajes de ficción o lugares (Aloy, Ganon, Kratos, Hyrule, Midgar).
- is_italic: false (letra redonda con mayúsculas oficiales). NUNCA marcar como error.

REGLA 4 Y 5 - EMPRESAS, PLATAFORMAS, MARCAS Y NOMBRES COMPUESTOS:
Nombres oficiales (PlayStation, Nintendo, Unity, C#, ZBrush, Decimation Master, Sony Interactive Entertainment).
- is_italic: false (letra redonda con grafía oficial).

REGLA 6 - SIGLAS EXTRANJERAS Y PLURALES INVARIABLES:
Siglas (NPC, HUD, API, DLC, RPG, QA, UI).
- is_italic: false (letra redonda con mayúsculas).
- Plural invariable: En español las siglas no llevan "s" ni "'s" (los NPC, los HUD). Desglosar significado en description.

REGLA 7 - TÍTULOS DE VIDEOJUEGOS Y OBRAS ARTÍSTICAS:
Obras de creación, videojuegos, libros, películas, álbumes.
- is_italic: true (cursiva).

REGLA 8 - TÉRMINOS GENÉRICOS EN INGLÉS DE VARIAS PALABRAS:
Expresiones comunes de dos o más palabras (fast travel, battle royale, machine learning, cloud gaming, gameplay loop).
- is_italic: true (cursiva y minúsculas).
- recommended: La misma frase en inglés en minúsculas (ej: "fast travel"). NO traducir.

REGLA 10 - PREFIJOS SIN GUION:
mini-, super-, auto-, co-, pos-, anti-, re-, ex-, multi-, extra- deben escribirse soldados a la palabra base y SIN guion (minifalda, superhéroe, expresidente).

REGLA 11 - DENOMINACIONES DE MÉTODOS:
lean six sigma, kanban, design thinking, scrum, kaizen, poka-yoke, agile.
- is_italic: true (cursiva y minúsculas).

ELEMENTOS DE SOFTWARE Y HERRAMIENTAS:
Inspector, Transform, Hierarchy, Tool, Brush, Geometry, SubTool.
- is_italic: false (letra redonda con Mayúscula Inicial).

ESTRUCTURA DE RESPUESTA JSON:
Para CADA elemento detectado devuelve:
- "text": Palabra o frase exacta del texto (ej: "testing", "brainstorming", "lore", "gameplay", "Inspector", "NPC").
- "category": Categoría correspondiente.
- "rule_number": Número de regla aplicada.
- "rule_name": Nombre de la regla.
- "is_italic": true o false.
- "recommended": La palabra EN SU IDIOMA ORIGINAL (sin traducir) con la tipografía y mayúsculas adecuadas.
- "description": Explicación enciclopédica clara de qué significa en español.
- "rae_rule": Justificación de la norma RAE/Fundéu.
- "source": Fuente citada.
- "source_url": Enlace web (o cadena vacía).

Responde ÚNICAMENTE con un JSON con la estructura:
{
  "findings": [
    {
      "text": "...",
      "category": "...",
      "rule_number": "...",
      "rule_name": "...",
      "is_italic": true,
      "recommended": "...",
      "description": "...",
      "rae_rule": "...",
      "source": "...",
      "source_url": "..."
    }
  ]
}
"""


def _cargar_cache() -> dict[str, Any]:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _guardar_cache(cache: dict[str, Any]) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _extraer_texto_interaccion(interaction: Any) -> str:
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
    texto_limpio = text.strip()
    if not texto_limpio:
        return []

    # Clave de versión renovada para invalidar respuestas con traducciones previas
    hash_texto = hashlib.md5((texto_limpio + "_v_sin_traducir_extranjerismos_v8").encode("utf-8")).hexdigest()
    cache = _cargar_cache()
    if hash_texto in cache:
        return cache[hash_texto]

    api_key = GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Falta la clave GEMINI_API_KEY en el archivo .env o WSGI.")

    client = genai.Client(api_key=api_key)
    prompt = (
        "Audita exhaustivamente el siguiente texto aplicando las 11 reglas. "
        "IMPORTANTE: En el campo 'recommended' de los extranjerismos crudos y términos en inglés (como testing, brainstorming, lore, gameplay), "
        "CONSERVA LA PALABRA EN INGLÉS EN MINÚSCULA Y CURSIVA; PROHIBIDO TRADUCIRLA en 'recommended'. La traducción va únicamente en 'description':\n\n"
        f'"""\n{texto_limpio}\n"""'
    )

    max_intentos = 3
    for intento in range(1, max_intentos + 1):
        try:
            interaction = client.interactions.create(
                model=GEMINI_MODEL,
                input=prompt,
                system_instruction=SYSTEM_INSTRUCTION,
                response_format={"type": "text", "mime_type": "application/json"},
                generation_config={
                    "max_output_tokens": 16384,
                    "thinking_level": "low",
                },
            )
            raw_text = _extraer_texto_interaccion(interaction).strip()
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text)

            match_json = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if match_json:
                raw_text = match_json.group(0)

            data = json.loads(raw_text)
            raw_findings = data.get("findings", [])
            break
        except Exception as exc:
            error_str = str(exc).lower()
            if any(k in error_str for k in ["overloaded", "demanda", "503", "429", "resource_exhausted"]):
                if intento < max_intentos:
                    time.sleep(intento * 2)
                    continue
            raise RuntimeError(f"El servicio de IA experimentó alta demanda: {exc}")

    errores: list[dict[str, Any]] = []
    tramos_ocupados: list[tuple[int, int]] = []
    raw_findings.sort(key=lambda x: len(x.get("text", "")), reverse=True)

    for item in raw_findings:
        palabra = item.get("text", "").strip()
        palabra_limpia = re.sub(r"^[\*\"'«“]+|[\*\"'»”]+$", "", palabra).strip()
        if not palabra_limpia:
            continue

        if re.match(r"^[A-Za-z0-9áéíóúÁÉÍÓÚñÑ]+$", palabra_limpia):
            patron = re.compile(r"(?<![\wáéíóúÁÉÍÓÚñÑ])" + re.escape(palabra_limpia) + r"(?![\wáéíóúÁÉÍÓÚñÑ])", re.IGNORECASE)
        else:
            patron = re.compile(re.escape(palabra_limpia), re.IGNORECASE)

        for m in patron.finditer(text):
            ini, fin = m.start(), m.end()
            if any(ini < ocup_fin and fin > ocup_ini for ocup_ini, ocup_fin in tramos_ocupados):
                continue

            tramos_ocupados.append((ini, fin))
            cat = item.get("category", "Ortografia")
            desc = item.get("description", "")
            rae = item.get("rae_rule", "")
            recom = item.get("recommended", palabra_limpia)
            is_italic = bool(item.get("is_italic", False))
            rule_name = item.get("rule_name", item.get("rule_number", "Norma editorial"))

            errores.append({
                "category": cat,
                "text": text[ini:fin],
                "message": f"{desc} | {rae}",
                "suggestions": [recom] if recom else [],
                "offset": ini,
                "length": fin - ini,
                "rule_id": f"GEMINI_{cat.upper().replace(' ', '_')}",
                "source": item.get("source", "Auditoría RAE/Gemini"),
                "lookup": {
                    "term": palabra_limpia,
                    "category": cat,
                    "rule_name": rule_name,
                    "is_italic": is_italic,
                    "definition": desc,
                    "rae_rule": rae,
                    "recommended": recom,
                    "source": item.get("source", "Manual RAE / FundéuRAE"),
                    "source_url": item.get("source_url", ""),
                    "found": True,
                },
            })

    resultado_final = sorted(errores, key=lambda x: x["offset"])
    cache[hash_texto] = resultado_final
    _guardar_cache(cache)

    return resultado_final