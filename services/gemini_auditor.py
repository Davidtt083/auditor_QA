"""Auditor de narrativa y localización: Extracción exhaustiva de herramientas, siglas y extranjerismos."""

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
El usuario de esta herramienta es un revisor humano no técnico que NO conoce los términos en inglés, las herramientas de software ni las siglas.

OBJETIVO OBLIGATORIO DE EXHAUSTIVIDAD (NO OMITIR NINGÚN TÉRMINO):
Tu tarea NO es solo buscar errores ortográficos; tu tarea es INVENTARIAR, EXPLICAR Y REVISAR CADA ELEMENTO TÉCNICO Y EDITORIAL DEL TEXTO.
Aunque una palabra ya esté bien escrita (por ejemplo, si 'Inspector' ya tiene mayúscula o 'NPC' ya está en mayúsculas sin 's'), DEBES EXTRAERLA E INCLUIRLA EN 'findings' para que el usuario conozca su significado, su regla y certifique si debe ir en redonda o cursiva.

DEBES EXTRAER OBLIGATORIAMENTE CADA UNO DE LOS SIGUIENTES ELEMENTOS QUE APAREZCAN:
1. HERRAMIENTAS Y ELEMENTOS DE INTERFAZ: Toda pestaña, ventana, panel, componente o herramienta de software (ej: Inspector, Transform, Hierarchy, Tool, Brush, Geometry, SubTool, Dynamesh, Canvas).
   - Categoría: "Herramienta / Elemento de interfaz".
   - Forma recomendada: Con Mayúscula Inicial y en letra REDONDA (is_italic = false).
   - Norma: Para los elementos internos de un programa (pestañas, menús, botones o herramientas específicas), se escribe con mayúscula inicial en redonda.

2. SIGLAS TÉCNICAS O EXTRANJERAS: Toda sigla (ej: NPC, HUD, API, DLC, RPG, QA, UI, IA).
   - Categoría: "Sigla".
   - Forma recomendada: En mayúsculas oficiales y letra REDONDA (is_italic = false).
   - Regla 6: Las siglas se escriben en mayúsculas, en redonda y son invariables en plural en español (los NPC, los HUD, los RPG; nunca con 's' ni ''s'). Desglosa su significado en la descripción.

3. EXTRANJERISMOS CRUDOS EN TEXTO PLANO (Regla 1): Toda palabra extranjera común sin adaptar (ej: asset, health, stamina, quests, gameplay, lore, loot, spawn, briefing).
   - Categoría: "Extranjerismo crudo / Latinismo".
   - En el texto plano carecen de formato, por lo que DEBES MARCARLAS indicando que su norma exige CURSIVA (is_italic = true) y minúscula inicial (ej: *asset*, *health*, *stamina*, *quests*), o sugerir su alternativa patrimonial (recurso, salud, resistencia, misiones).

4. TÉRMINOS GENÉRICOS EN INGLÉS DE VARIAS PALABRAS (Regla 8): Expresiones compuestas (ej: fast travel, battle royale, machine learning, cloud gaming, gameplay loop, free to play).
   - Categoría: "Término genérico en inglés".
   - Forma recomendada: En CURSIVA (is_italic = true) y en minúsculas (*fast travel*, *battle royale*, *machine learning*, *cloud gaming*).

5. MARCAS, PLATAFORMAS, LENGUAJES Y MOTORES (Reglas 4 y 5): Nombres oficiales (ej: Unity, C#, Unreal Engine, ZBrush, PlayStation).
   - Categoría: "Marca / Empresa".
   - Forma recomendada: En letra REDONDA (is_italic = false) respetando su grafía oficial.

6. TÍTULOS DE OBRAS, VIDEOJUEGOS Y ARTE (Regla 7): En CURSIVA (is_italic = true).
7. MÉTODOS Y METODOLOGÍAS (Regla 11): En minúsculas y CURSIVA (is_italic = true) (ej: scrum, kanban, agile).
8. PREFIJOS Y ERRORES ORTOGRÁFICOS (Regla 10 y general): Prefijos sin guion (minifalda, superhéroe) y faltas de tildes o concordancia.

ÁRBOL DE DECISIÓN (Regla 9):
Prioriza: a) Herramientas / Marcas / Nombres propios (Redonda) -> b) Siglas (Redonda) -> c) Obras (Cursiva) -> d) Adaptados (Redonda) -> e) Extranjerismos crudos y términos genéricos (Cursiva).

REGLA DEL CAMPO 'text':
En el campo "text", devuelve ÚNICAMENTE la palabra o frase exacta tal como está en el texto original (ej: "Inspector", "Transform", "Hierarchy", "Unity", "C#", "API", "NPC", "HUD", "asset", "health", "stamina", "fast travel", "battle royale", "machine learning", "cloud gaming", "DLC", "RPG", "quests"). NO incluyas artículos como 'el' o 'los'.

Responde ÚNICAMENTE con un JSON con la estructura:
{
  "findings": [
    {
      "text": "...",
      "category": "...",
      "rule_number": "...",
      "rule_name": "...",
      "is_italic": false,
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

    # Hash renovado para invalidar cualquier respuesta vacía anterior
    hash_texto = hashlib.md5((texto_limpio + "_v_exhaustiva_asistente_v7").encode("utf-8")).hexdigest()
    cache = _cargar_cache()
    if hash_texto in cache:
        return cache[hash_texto]

    api_key = GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Falta la clave GEMINI_API_KEY en el archivo .env o WSGI.")

    client = genai.Client(api_key=api_key)
    prompt = (
        "Realiza la auditoría e inventario exhaustivo del siguiente texto. Extrae CADA herramienta (Inspector, Transform, Hierarchy), "
        "marca (Unity, C#), sigla (API, NPC, HUD, DLC, RPG), extranjerismo (asset, health, stamina, quests) "
        "y término compuesto (fast travel, battle royale, machine learning, cloud gaming):\n\n"
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
    # Ordenar por longitud descendente para que frases como 'machine learning' se ubiquen antes que palabras sueltas
    raw_findings.sort(key=lambda x: len(x.get("text", "")), reverse=True)

    for item in raw_findings:
        palabra = item.get("text", "").strip()
        # Limpiar posibles comillas o asteriscos devueltos por el LLM
        palabra_limpia = re.sub(r"^[\*\"'«“]+|[\*\"'»”]+$", "", palabra).strip()
        if not palabra_limpia:
            continue

        # Si es alfanumérico estricto, usamos delimitadores de palabra para evitar falsos positivos
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