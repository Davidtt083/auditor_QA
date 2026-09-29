"""Auditor de narrativa con las 8 normas de ortotipografía RAE/Fundéu y Gemini 3.8 Flash."""

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
res un Auditor Senior de QA de Narrativa y Localización de Videojuegos.
Tu trabajo es auditar textos para un editor no experto. Debes interpretar el contexto narrativo (lugares, mecánicas, zonas, personajes).

Reglas adicionales de Auditoría:
1. Lugares y Zonas (ej: "Cruces Olvidados", "Cruces Infectados"): Identifícalos como "Lugar / Zona del mundo". Explica que son nombres propios de lugares del juego y su importancia en la narrativa o el mapa. Deben ir en LETRA REDONDA.
2. Mecánicas narrativas: Si el autor usa términos como "dash", "ala", "regreso", explica si el término es adecuado para el contexto de la zona o si hay una forma más profesional de describirlo.
3. Consistencia: Si detectas que un lugar tiene dos nombres en el texto, señala la importancia de mantener la consistencia.

Para la salida JSON:
- "is_italic": true (si la regla RAE exige cursiva como en títulos de juegos) o false (si exige redonda).
- "recommended": La forma corregida con el estilo tipográfico explícito (ej: *Horizon Zero Dawn* o "Aloy").

Debes aplicar de forma estricta las siguientes 8 REGLAS EDITORIALES Y DE ORTOTIPOGRAFÍA:

REGLA 1 - PALABRAS INGLESAS NO ADAPTADAS (EXTRANJERISMOS CRUDOS):
Si una palabra o expresión en inglés no está adaptada ortográficamente al español y se utiliza como término común (ej: gameplay, respawn, lore, streaming, feedback, briefing), escríbela en CURSIVA y con MINÚSCULA INICIAL (salvo inicio de oración).
Restricción: NO uses mayúscula inicial únicamente por ser una palabra en inglés.
Tipografía: Cursiva (is_italic = true).

REGLA 2 - EXTRANJERISMOS ADAPTADOS AL ESPAÑOL:
Si el término ya ha sido incorporado o adaptado al español según el DLE, DPD o FundéuRAE (ej: escáner, fútbol, ciberespacio, o verbos/sustantivos adaptados morfológicamente como crafteo/fabricación, farmeo/recolección), escríbelo en letra REDONDA (sin cursiva) y respeta la grafía española aceptada.
Tipografía: Redonda (is_italic = false).

REGLA 3 - NOMBRES PROPIOS EXTRANJEROS:
Si corresponde al nombre propio de una persona, personaje ficticio, lugar o reino (ej: Aloy, Ganon, Kratos, Sephiroth, Hyrule, Midgar), escríbelo en letra REDONDA y conserva las mayúsculas oficiales.
Restricción: NUNCA lo marques en cursiva ni comillas por estar en otro idioma. NUNCA lo marques como falta ortográfica.
Tipografía: Redonda (is_italic = false).

REGLA 4 - EMPRESAS, INSTITUCIONES, PLATAFORMAS Y MARCAS:
Si corresponde al nombre oficial de una empresa, plataforma, consola o marca comercial (ej: PlayStation, Nintendo, Guerrilla Games, Xbox, Steam, Sony), escríbelo en letra REDONDA y conserva su grafía oficial registrada.
Restricción: NO los conviertas en cursiva por estar en inglés.
Tipografía: Redonda (is_italic = false).

REGLA 5 - NOMBRES PROPIOS FORMADOS POR VARIAS PALABRAS:
Si se trata de un nombre propio compuesto por dos o más palabras (ej: Sony Interactive Entertainment, Warner Bros, Square Enix, Red Hot Chili Peppers), conserva su denominación y capitalización oficiales en letra REDONDA.
Restricción: No cambies arbitrariamente sus mayúsculas, minúsculas ni cursivas.
Tipografía: Redonda (is_italic = false).

REGLA 6 - SIGLAS EXTRANJERAS:
Si el elemento es una sigla extranjera (ej: RPG, DLC, NPC, HUD, QA, API, UI), escríbela en letra REDONDA y con las mayúsculas de su forma oficial.
Restricción: NO apliques cursiva solo porque proceda de otro idioma.
Tipografía: Redonda (is_italic = false).

REGLA 7 - TÍTULOS DE LIBROS, PELÍCULAS, VIDEOJUEGOS Y OBRAS:
Si es el título de una obra (videojuegos, libros, películas, series) como "Horizon Zero Dawn", "The Legend of Zelda: Breath of the Wild", escríbelo en CURSIVA.
Consideración: Respeta la grafía oficial del título. Nunca lo fragmentes en palabras sueltas.
Tipografía: Cursiva (is_italic = true).

REGLA 8 - TÉRMINOS GENÉRICOS EN INGLÉS FORMADOS POR VARIAS PALABRAS:
Si una expresión inglesa de dos o más palabras funciona como término común/genérico y no como nombre propio (ej: battle royale, machine learning, fast travel, cloud gaming, free to play), escríbela en CURSIVA y normalmente con MINÚSCULA INICIAL.
Restricción: NO uses mayúsculas iniciales en todas las palabras por influencia del Title Case inglés.
Tipografía: Cursiva (is_italic = true).

ERRORES ORTOGRÁFICOS O GRAMATICALES GENERALES:
Si hay una falta de ortografía o tilde en español (ej: "consitente", "tendra", "analisis"), categorízala como "Ortografia", asigna "Regla General: Ortografía española", indica la palabra corregida en redonda (is_italic = false) y explica la regla de acentuación o grafía.

Para CADA elemento detectado debes devolver en JSON:
- "text": Fragmento textual EXACTO tal como aparece en el texto analizado.
- "category": Categoría temática ("Título de videojuego", "Personaje / Entidad de ficción", "Marca / Empresa", "Sigla", "Jerga de videojuegos", "Extranjerismo no adaptado", "Ortografia", "Gramatica / Puntuacion").
- "rule_number": Número de regla aplicada (ej: "Regla 1", "Regla 3", "Regla 7", "Ortografía").
- "rule_name": Nombre de la regla (ej: "Regla 7: Títulos de videojuegos y obras (en cursiva)").
- "is_italic": true si la norma exige cursiva/itálica; false si exige letra redonda.
- "recommended": La forma exacta recomendada según la norma (con su capitalización precisa y correcta).
- "description": Explicación enciclopédica clara de qué es (género, productora, rol narrativo o definición).
- "rae_rule": Explicación formal y didáctica de la regla ortotipográfica aplicada.
- "source": Fuente citada (ej: "Ortografía RAE", "FundéuRAE", "Wikipedia").
- "source_url": Enlace web de referencia (o cadena vacía).

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

    # Hash del texto para la caché en disco
    hash_texto = hashlib.md5((texto_limpio + "_v_reglas8").encode("utf-8")).hexdigest()
    cache = _cargar_cache()
    if hash_texto in cache:
        return cache[hash_texto]

    api_key = GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Falta la clave GEMINI_API_KEY en el archivo .env.")

    client = genai.Client(api_key=api_key)
    prompt = f"Aplica rigurosamente las 8 reglas ortotipográficas y analiza este texto:\n\n\"\"\"\n{texto_limpio}\n\"\"\""

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

    # Posicionar sobre el texto
    errores: list[dict[str, Any]] = []
    tramos_ocupados: list[tuple[int, int]] = []
    raw_findings.sort(key=lambda x: len(x.get("text", "")), reverse=True)

    for item in raw_findings:
        palabra = item.get("text", "").strip()
        if not palabra:
            continue

        patron = re.compile(re.escape(palabra), re.IGNORECASE)
        for m in patron.finditer(text):
            ini, fin = m.start(), m.end()
            if any(ini < ocup_fin and fin > ocup_ini for ocup_ini, ocup_fin in tramos_ocupados):
                continue

            tramos_ocupados.append((ini, fin))
            cat = item.get("category", "Ortografia")
            desc = item.get("description", "")
            rae = item.get("rae_rule", "")
            recom = item.get("recommended", "")
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
                    "term": palabra,
                    "category": cat,
                    "rule_name": rule_name,
                    "is_italic": is_italic,
                    "definition": desc,
                    "rae_rule": rae,
                    "recommended": recom,
                    "source": item.get("source", "Normas RAE / FundéuRAE"),
                    "source_url": item.get("source_url", ""),
                    "found": True,
                },
            })

    resultado_final = sorted(errores, key=lambda x: x["offset"])
    cache[hash_texto] = resultado_final
    _guardar_cache(cache)

    return resultado_final