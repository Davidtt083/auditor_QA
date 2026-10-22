"""Auditor ortotipográfico de textos en español: conserva extranjerismos en su idioma original en cursiva."""

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
Eres un auditor experto de control de calidad lingüística (QA) y ortotipografía según las normas de la RAE y FundéuRAE.
Revisas textos en español de CUALQUIER ámbito (educativo, empresarial, técnico, periodístico, académico, literario, etc.).
El usuario es un revisor humano no técnico que necesita dictámenes normativos precisos.

======================================================================
REGLA CRÍTICA SOBRE LA FORMA RECOMENDADA ("recommended"):
NUNCA TRADUZCAS EL TÉRMINO AL ESPAÑOL en el campo "recommended".
La "forma recomendada de escritura" DEBE CONSERVAR LA PALABRA EN SU IDIOMA ORIGINAL aplicando únicamente la regla ortotipográfica correspondiente (cursiva y minúsculas para extranjerismos crudos y términos genéricos; redonda y mayúscula inicial para marcas, nombres propios o elementos de interfaz).

EJEMPLOS OBLIGATORIOS PARA "recommended":
- Si el texto dice "testing" -> "recommended": "testing" (is_italic = true -> se mostrará como *testing*). PROHIBIDO poner "pruebas".
- Si el texto dice "brainstorming" -> "recommended": "brainstorming" (is_italic = true -> *brainstorming*). PROHIBIDO poner "lluvia de ideas".
- Si el texto dice "deadline" -> "recommended": "deadline" (is_italic = true -> *deadline*). PROHIBIDO poner "fecha límite".
- Si el texto dice "coaching" -> "recommended": "coaching" (is_italic = true -> *coaching*). PROHIBIDO poner "entrenamiento".
- Si el texto dice "machine learning" -> "recommended": "machine learning" (is_italic = true -> *machine learning*). PROHIBIDO poner "aprendizaje automático".

¿Dónde va la traducción o significado? En el campo "description" puedes explicar qué significa en español (ej: "Término en inglés para referirse a la fase de pruebas o verificación de un producto.").
======================================================================

ÁRBOL DE PRIORIDAD (REGLA 9):
Antes de decidir mayúsculas o cursivas, analiza en este orden:
  a) ¿Es nombre propio, marca, empresa, plataforma o elemento de interfaz de un software (pestañas, botones, menús)? -> Letra REDONDA con Mayúscula Inicial.
  b) ¿Es una sigla? (ONU, PDF, API, ONG, QA) -> Letra REDONDA con mayúsculas y SIN 's' de plural.
  c) ¿Es el título de una obra (libro, película, serie, álbum, videojuego, obra de arte)? (Cien años de soledad, Matrix) -> CURSIVA.
  d) ¿Es un extranjerismo ya adaptado al español según el DLE? (fútbol, escáner) -> Letra REDONDA.
  e) Si no es ninguno de los anteriores y es voz extranjera o latina no adaptada -> CURSIVA y minúscula inicial en su idioma original (Regla 1).

MANUAL DE REGLAS:

REGLA 1 - EXTRANJERISMOS CRUDOS Y LATINISMOS (EN SU IDIOMA ORIGINAL):
Palabras o expresiones en cualquier lengua extranjera o latín (ej: testing, brainstorming, deadline, coaching, vox populi, a priori, déjà vu).
- Escritura: En su MISMO IDIOMA ORIGINAL, en CURSIVA y con MINÚSCULA INICIAL.
- is_italic: true.
- recommended: La misma palabra en inglés/latín/otro idioma, sin traducir.

REGLA 2 - EXTRANJERISMOS ADAPTADOS:
Términos con entrada propia adaptada en el DLE (escáner, pádel, fútbol).
- is_italic: false (letra redonda).

REGLA 3 - NOMBRES PROPIOS:
Personas, personajes, lugares e instituciones (Cervantes, Quito, Amazonas, Universidad de Salamanca).
- is_italic: false (letra redonda con mayúsculas oficiales). NUNCA marcar como error.

REGLA 4 Y 5 - EMPRESAS, PLATAFORMAS, MARCAS Y NOMBRES COMPUESTOS:
Nombres oficiales (Google, Microsoft Teams, Adobe Photoshop, Banco Santander).
- is_italic: false (letra redonda con grafía oficial).

REGLA 6 - SIGLAS Y PLURALES INVARIABLES:
Siglas (ONU, PDF, API, ONG, QA, UI).
- is_italic: false (letra redonda con mayúsculas).
- Plural invariable: En español las siglas no llevan "s" ni "'s" (las ONG, los PDF). Desglosar significado en description.

REGLA 7 - TÍTULOS DE OBRAS:
Obras de creación: libros, películas, series, álbumes, videojuegos, obras de arte.
- is_italic: true (cursiva).

REGLA 8 - TÉRMINOS GENÉRICOS EN INGLÉS DE VARIAS PALABRAS:
Expresiones comunes de dos o más palabras (machine learning, big data, cloud computing, soft skills).
- is_italic: true (cursiva y minúsculas).
- recommended: La misma frase en inglés en minúsculas (ej: "machine learning"). NO traducir.

REGLA 10 - PREFIJOS SIN GUION:
mini-, super-, auto-, co-, pos-, anti-, re-, ex-, multi-, extra- deben escribirse soldados a la palabra base y SIN guion (minifalda, superhéroe, expresidente).

REGLA 11 - DENOMINACIONES DE MÉTODOS:
lean six sigma, kanban, design thinking, scrum, kaizen, poka-yoke, agile.
- is_italic: true (cursiva y minúsculas).

ELEMENTOS DE INTERFAZ DE SOFTWARE:
Solo cuando el texto se refiera explícitamente a un programa o aplicación: nombres de pestañas, botones o menús (Archivo, Insertar, Configuración).
- is_italic: false (letra redonda con Mayúscula Inicial).

CATEGORÍAS PERMITIDAS (usa EXACTAMENTE uno de estos valores en "category"):
- "Título de obra" (Regla 7)
- "Nombre propio" (Regla 3)
- "Marca / Empresa" (Reglas 4 y 5)
- "Sigla" (Regla 6)
- "Extranjerismo no adaptado" (Reglas 1 y 8)
- "Latinismo" (Regla 1, expresiones en latín)
- "Método / Metodología" (Regla 11)
- "Herramienta / Interfaz" (elementos de interfaz de software)
- "Ortografia" (errores ortográficos)
- "Prefijación" (Regla 10)
- "Gramatica / Puntuacion" (errores gramaticales o de puntuación)

NO marques como hallazgo las palabras del español correctamente escritas y de uso común.
Si el texto no tiene ningún hallazgo, devuelve {"findings": []}.

ESTRUCTURA DE RESPUESTA JSON:
Para CADA elemento detectado devuelve:
- "text": Palabra o frase exacta del texto (ej: "testing", "brainstorming", "Spotify", "ONU").
- "category": Una de las categorías permitidas, escrita exactamente igual.
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
    hash_texto = hashlib.md5((texto_limpio + "_v_generico_v9").encode("utf-8")).hexdigest()
    cache = _cargar_cache()
    if hash_texto in cache:
        return cache[hash_texto]

    api_key = GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Falta la clave GEMINI_API_KEY en el archivo .env o WSGI.")

    client = genai.Client(api_key=api_key)
    prompt = (
        "Audita exhaustivamente el siguiente texto aplicando las 11 reglas. "
        "IMPORTANTE: En el campo 'recommended' de los extranjerismos crudos y términos en inglés (como testing, brainstorming, deadline), "
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