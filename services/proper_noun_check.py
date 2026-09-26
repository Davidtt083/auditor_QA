"""Verificacion de nombres propios y titulos de videojuego antes de
reportar una falta de ortografia.

Pensado para guiones de la materia "Narrativas para videojuegos": un
nombre inventado (personaje, lugar, facción) o el titulo de un juego
citado en el guion no debe marcarse como error sin antes comprobar si
existe como tal en fuentes externas. Este modulo NUNCA decide por su
cuenta que algo esta bien escrito: solo adjunta evidencia (fuente, url,
fragmento) para que quien revisa decida con mas contexto.

Tambien resuelve el formato tipografico recomendado por la RAE:
  * cursiva              -> titulos de obras (videojuegos, peliculas, libros)
  * mayuscula_inicial    -> nombre propio de una sola palabra
  * altas_y_bajas        -> nombre propio compuesto (varias palabras)
  * todo_en_altas        -> siglas (NPC, RPG, HUD...)
"""

from __future__ import annotations

import os
import re
from typing import Any

from services.dictionary_lookup import (
    DUCKDUCKGO_ENDPOINT,
    GOOGLE_CSE_API_KEY,
    GOOGLE_CSE_ENDPOINT,
    GOOGLE_CSE_ID,
    TIMEOUT,
    USER_AGENT,
    _dominio_de,
    _get_json,
    _parse_duckduckgo_html,
)

# ---------------------------------------------------------------------------
# Formato tipografico recomendado (Ortografia de la lengua espanola, RAE)
# ---------------------------------------------------------------------------

ETIQUETA_FORMATO = {
    "cursiva": "cursiva",
    "mayuscula_inicial": "mayúscula inicial",
    "altas_y_bajas": "Altas y Bajas (mayúscula en cada palabra significativa)",
    "todo_en_altas": "TODO EN ALTAS (sigla)",
}

REGLA_RAE = {
    "cursiva": (
        "Los titulos de obras (videojuegos, peliculas, libros, canciones) "
        "se escriben en cursiva; si no hay cursiva disponible, entre comillas."
    ),
    "mayuscula_inicial": (
        "Los nombres propios (de persona, personaje o lugar) se escriben "
        "con mayuscula inicial y el resto en minuscula."
    ),
    "altas_y_bajas": (
        "En nombres propios compuestos por varias palabras se escribe con "
        "mayuscula inicial cada palabra significativa (no los articulos ni "
        "preposiciones internos), igual que en topónimos y antropónimos compuestos."
    ),
    "todo_en_altas": (
        "Las siglas se escriben enteramente en mayuscula y sin puntos "
        "(Ortografia de la lengua espanola, RAE)."
    ),
}

# ---------------------------------------------------------------------------
# Señales para clasificar el tipo de hallazgo
# ---------------------------------------------------------------------------

DOMINIOS_VIDEOJUEGO = (
    "store.steampowered.com", "mobygames.com", "metacritic.com", "ign.com",
    "vandal.elespanol.com", "3djuegos.com", "gamespot.com", "eurogamer.es",
    "hobbyconsolas.com", "meristation.as.com", "nintendo.com",
    "playstation.com", "xbox.com", "epicgames.com", "gog.com", "gamefaqs.gamespot.com",
)
DOMINIOS_PERSONAJE = ("fandom.com", "wikia.org")

_SENALES_VIDEOJUEGO = re.compile(
    r"\bvideojuego(s)?\b|\bvideo game\b|"
    r"\bjuego de (accion|aventura|rol|disparos|plataformas|estrategia)\b|"
    r"\bdesarrollado por\b.{0,30}\b(studios?|games?)\b",
    re.IGNORECASE,
)
_SENALES_PERSONAJE = re.compile(
    r"\bpersonaje(s)?\b|\bprotagonista\b|\bantagonista\b|\bcharacter\b|"
    r"\bavatar\b|\bNPC\b|\bvillano\b|\bheroe\b|\bheroína\b",
    re.IGNORECASE,
)
_SENALES_LUGAR = re.compile(
    r"\b(reino|ciudad|planeta|mundo|region|continente|mapa|escenario)\b.{0,25}"
    r"\b(ficticio|del videojuego|del juego|de la saga)\b",
    re.IGNORECASE,
)

_SIGLA = re.compile(r"^[A-ZÑ]{2,6}$")


# ---------------------------------------------------------------------------
# Busqueda (reutiliza Google CSE si esta configurado; si no, DuckDuckGo)
# ---------------------------------------------------------------------------

def _buscar_snippets(term: str) -> list[tuple[str, str, str]]:
    """(titulo, fragmento, url) de los primeros resultados. No filtra por
    dominio de confianza: aqui interesa detectar la señal, no citarla."""
    consulta = f'"{term}" videojuego OR personaje OR juego'

    if GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID:
        data = _get_json(
            GOOGLE_CSE_ENDPOINT,
            {
                "key": GOOGLE_CSE_API_KEY, "cx": GOOGLE_CSE_ID,
                "q": consulta, "num": "5", "hl": "es", "gl": "es",
            },
        )
        if data and data.get("items"):
            return [
                (item.get("title", ""), item.get("snippet", "") or "", item.get("link", ""))
                for item in data["items"]
            ]

    try:
        import requests
        response = requests.get(
            DUCKDUCKGO_ENDPOINT,
            params={"q": consulta, "kl": "es-es"},
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "es-ES,es;q=0.9"},
        )
        if response.status_code == 200:
            return [("", fragmento, url) for url, fragmento in _parse_duckduckgo_html(response.text)]
    except Exception:
        pass
    return []


def _sigla_info(palabra: str) -> dict[str, Any] | None:
    """Deteccion barata (sin red): siglas tipicas de guion de videojuego."""
    if not _SIGLA.match(palabra):
        return None
    return {
        "coincide": True,
        "tipo": "sigla",
        "fuente": "Regla ortografica (sin busqueda web)",
        "url": "",
        "fragmento": "",
        "formato_recomendado": "todo_en_altas",
        "regla_rae": REGLA_RAE["todo_en_altas"],
    }


def verificar_nombre_propio(palabra: str) -> dict[str, Any] | None:
    """Busca evidencia de que `palabra` es un nombre propio o titulo de
    videojuego. Devuelve None si no hay señal clara: en ese caso el
    llamador debe seguir tratandolo como posible falta de ortografia."""
    palabra_limpia = palabra.strip(" .,;:()[]\"'«»¿?¡!")
    if len(palabra_limpia) < 3:
        return None

    sigla = _sigla_info(palabra_limpia)
    if sigla:
        return sigla

    resultados = _buscar_snippets(palabra_limpia)
    tiene_varias_palabras = " " in palabra_limpia

    for titulo, fragmento, url in resultados:
        texto = f"{titulo} {fragmento}"
        if not re.search(re.escape(palabra_limpia), texto, re.IGNORECASE):
            continue  # el resultado ni siquiera menciona la palabra
        dominio = _dominio_de(url) if url else ""
        en_dominio_juego = any(dominio == d or dominio.endswith("." + d) for d in DOMINIOS_VIDEOJUEGO)
        en_dominio_personaje = any(dominio == d or dominio.endswith("." + d) for d in DOMINIOS_PERSONAJE)

        # El dominio (fandom = wiki de personajes/lore; tienda o prensa de
        # videojuegos = ficha de titulo) es una señal mas fiable que una
        # palabra suelta en el fragmento, asi que se evalua primero.
        if en_dominio_personaje:
            formato = "altas_y_bajas" if tiene_varias_palabras else "mayuscula_inicial"
            return {
                "coincide": True, "tipo": "personaje o entidad del guion",
                "fuente": dominio, "url": url, "fragmento": fragmento[:220],
                "formato_recomendado": formato, "regla_rae": REGLA_RAE[formato],
            }
        if en_dominio_juego:
            return {
                "coincide": True, "tipo": "titulo de videojuego",
                "fuente": dominio, "url": url, "fragmento": fragmento[:220],
                "formato_recomendado": "cursiva", "regla_rae": REGLA_RAE["cursiva"],
            }
        if _SENALES_LUGAR.search(texto):
            formato = "altas_y_bajas" if tiene_varias_palabras else "mayuscula_inicial"
            return {
                "coincide": True, "tipo": "lugar ficticio",
                "fuente": dominio or "busqueda web", "url": url, "fragmento": fragmento[:220],
                "formato_recomendado": formato, "regla_rae": REGLA_RAE[formato],
            }
        if _SENALES_PERSONAJE.search(texto):
            formato = "altas_y_bajas" if tiene_varias_palabras else "mayuscula_inicial"
            return {
                "coincide": True, "tipo": "personaje",
                "fuente": dominio or "busqueda web", "url": url, "fragmento": fragmento[:220],
                "formato_recomendado": formato, "regla_rae": REGLA_RAE[formato],
            }
        if _SENALES_VIDEOJUEGO.search(texto):
            return {
                "coincide": True, "tipo": "titulo de videojuego",
                "fuente": dominio or "busqueda web", "url": url, "fragmento": fragmento[:220],
                "formato_recomendado": "cursiva", "regla_rae": REGLA_RAE["cursiva"],
            }
    return None
