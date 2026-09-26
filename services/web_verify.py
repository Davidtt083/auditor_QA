"""
Verificacion contextual de posibles errores ortograficos.

Objetivo:
    Detectar falsos positivos del corrector, especialmente en textos
    relacionados con videojuegos.

Ejemplos:

    Horizon Zero Dawn
    Ganon
    Hyrule
    crafteo

No utiliza Google APIs.

La busqueda se realiza sobre la pagina HTML publica del buscador y
los resultados se almacenan temporalmente en cache para reducir
peticiones repetidas.

La salida intenta determinar:

    - si parece un videojuego
    - si parece personaje
    - si parece lugar ficticio
    - si parece nombre propio
    - si parece termino de videojuegos
    - significado aproximado
    - escritura sugerida
    - recomendacion tipografica
"""

from __future__ import annotations

import html
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent.parent

CACHE_PATH = BASE_DIR / "cache_verificacion_web.json"

TIMEOUT = float(
    os.getenv(
        "QA_WEB_VERIFY_TIMEOUT",
        "6",
    )
)

CACHE_TTL = int(
    os.getenv(
        "QA_WEB_VERIFY_CACHE_TTL",
        str(60 * 60 * 24 * 30),
    )
)

MAX_TERMS = int(
    os.getenv(
        "QA_WEB_VERIFY_MAX_TERMS",
        "30",
    )
)

MAX_RESULTS = 6

GOOGLE_ENDPOINT = "https://www.google.com/search"

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/153.0 Safari/537.36"
)


# ------------------------------------------------------------
# Dominios relacionados con videojuegos
# ------------------------------------------------------------

GAME_DOMAINS = {
    "steampowered.com",
    "store.steampowered.com",
    "epicgames.com",
    "playstation.com",
    "xbox.com",
    "nintendo.com",
    "ea.com",
    "ubisoft.com",
    "rockstargames.com",
    "blizzard.com",
    "riotgames.com",
    "minecraft.net",
    "ign.com",
    "gamespot.com",
    "metacritic.com",
    "mobygames.com",
    "fandom.com",
    "gamepressure.com",
    "polygon.com",
    "eurogamer.net",
    "gamesradar.com",
    "bandainamcoent.com",
    "square-enix-games.com",
    "bethesda.net",
    "playstation.com",
}


GAME_WORDS = {
    "videojuego",
    "videojuegos",
    "juego",
    "juegos",
    "game",
    "games",
    "videogame",
    "videogames",
    "gaming",
    "personaje",
    "personajes",
    "protagonista",
    "antagonista",
    "saga",
    "franquicia",
    "zelda",
    "nintendo",
    "playstation",
    "xbox",
    "steam",
    "pc",
}


CHARACTER_WORDS = {
    "personaje",
    "personajes",
    "protagonista",
    "antagonista",
    "villano",
    "heroína",
    "héroe",
    "character",
    "characters",
}


PLACE_WORDS = {
    "lugar",
    "lugares",
    "reino",
    "ciudad",
    "región",
    "isla",
    "planeta",
    "continente",
    "mundo",
    "kingdom",
    "city",
    "region",
    "island",
    "planet",
    "world",
}


PROPER_WORDS = {
    "nombre",
    "propio",
    "personaje",
    "persona",
    "marca",
    "empresa",
    "ciudad",
    "reino",
    "lugar",
    "autor",
    "actriz",
    "actor",
    "director",
    "personaje",
}


GAME_TERM_WORDS = {
    "crafteo",
    "crafting",
    "loot",
    "looteo",
    "farmeo",
    "farmeando",
    "respawn",
    "spawn",
    "boss",
    "npc",
    "xp",
    "mana",
    "build",
    "skill",
    "skills",
    "quest",
    "quests",
    "gameplay",
    "jugabilidad",
}


# ------------------------------------------------------------
# Cache
# ------------------------------------------------------------

def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}

    try:
        with CACHE_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
    ):
        return {}


_CACHE = _load_cache()


def _cache_key(term: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        term.strip().lower(),
    )


def _cache_get(term: str):
    key = _cache_key(term)

    entry = _CACHE.get(key)

    if not entry:
        return None

    timestamp = entry.get("_timestamp", 0)

    if (
        time.time() - timestamp
        > CACHE_TTL
    ):
        return None

    return {
        key: value
        for key, value in entry.items()
        if key != "_timestamp"
    }


def _cache_set(
    term: str,
    result: dict,
):
    key = _cache_key(term)

    _CACHE[key] = {
        **result,
        "_timestamp": time.time(),
    }

    try:
        with CACHE_PATH.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                _CACHE,
                file,
                ensure_ascii=False,
                indent=2,
            )

    except OSError:
        pass


# ------------------------------------------------------------
# Utilidades
# ------------------------------------------------------------

def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        return host

    except Exception:
        return ""


def _contains_domain(
    domain: str,
    domains: set[str],
) -> bool:
    return any(
        domain == item
        or domain.endswith("." + item)
        for item in domains
    )


def _clean_text(value: str) -> str:
    value = html.unescape(value or "")

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def _normalise_term(term: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        term.strip().lower(),
    )


def _tokenize(value: str) -> list[str]:
    return re.findall(
        r"[a-záéíóúüñ0-9]+",
        value.lower(),
    )


# ------------------------------------------------------------
# Busqueda Google HTML
# ------------------------------------------------------------

def _google_search(
    query: str,
) -> list[dict]:

    try:
        response = requests.get(
            GOOGLE_ENDPOINT,
            params={
                "q": query,
                "hl": "es",
                "num": MAX_RESULTS,
                "filter": "0",
            },
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "es-MX,es;q=0.9",
            },
            timeout=TIMEOUT,
        )

        response.raise_for_status()

    except requests.RequestException:
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    results = []

    # Google suele utilizar div.MjjYud para los resultados.
    containers = soup.select("div.MjjYud")

    if not containers:
        containers = soup.select(
            "div[data-snhf]"
        )

    for container in containers:

        link = container.select_one(
            "a[href]"
        )

        if not link:
            continue

        href = link.get("href", "")

        if not href.startswith("http"):
            continue

        title_element = (
            container.select_one("h3")
        )

        title = (
            title_element.get_text(
                " ",
                strip=True,
            )
            if title_element
            else link.get_text(
                " ",
                strip=True,
            )
        )

        snippet_element = (
            container.select_one(
                ".VwiC3b"
            )
            or container.select_one(
                ".yXK7lf"
            )
        )

        snippet = (
            snippet_element.get_text(
                " ",
                strip=True,
            )
            if snippet_element
            else container.get_text(
                " ",
                strip=True,
            )
        )

        title = _clean_text(title)
        snippet = _clean_text(snippet)

        if not title:
            continue

        results.append(
            {
                "title": title,
                "url": href,
                "domain": _domain(href),
                "snippet": snippet[:500],
            }
        )

        if len(results) >= MAX_RESULTS:
            break

    return results


# ------------------------------------------------------------
# Clasificacion
# ------------------------------------------------------------

def _score_game(
    term: str,
    results: list[dict],
) -> int:

    normalized = _normalise_term(term)
    tokens = set(
        _tokenize(normalized)
    )

    score = 0

    for result in results:

        title = result["title"].lower()
        snippet = result["snippet"].lower()
        domain = result["domain"]

        text = f"{title} {snippet}"

        if normalized in title:
            score += 8

        if normalized in snippet:
            score += 3

        if _contains_domain(
            domain,
            GAME_DOMAINS,
        ):
            score += 5

        for word in GAME_WORDS:
            if word in text:
                score += 2

        for token in tokens:
            if token in title:
                score += 1

    return score


def _score_character(
    term: str,
    results: list[dict],
) -> int:

    normalized = _normalise_term(term)

    score = 0

    for result in results:

        title = result["title"].lower()
        snippet = result["snippet"].lower()

        text = f"{title} {snippet}"

        if normalized in title:
            score += 3

        for word in CHARACTER_WORDS:
            if word in text:
                score += 3

        if _contains_domain(
            result["domain"],
            GAME_DOMAINS,
        ):
            score += 2

    return score


def _score_place(
    term: str,
    results: list[dict],
) -> int:

    normalized = _normalise_term(term)

    score = 0

    for result in results:

        title = result["title"].lower()
        snippet = result["snippet"].lower()

        text = f"{title} {snippet}"

        if normalized in title:
            score += 3

        for word in PLACE_WORDS:
            if word in text:
                score += 3

        if _contains_domain(
            result["domain"],
            GAME_DOMAINS,
        ):
            score += 2

    return score


def _score_proper_name(
    term: str,
    results: list[dict],
) -> int:

    normalized = _normalise_term(term)

    score = 0

    for result in results:

        title = result["title"].lower()
        snippet = result["snippet"].lower()

        text = f"{title} {snippet}"

        if normalized in title:
            score += 3

        for word in PROPER_WORDS:
            if word in text:
                score += 2

    return score


def _score_game_term(
    term: str,
    results: list[dict],
) -> int:

    normalized = _normalise_term(term)

    score = 0

    if normalized in GAME_TERM_WORDS:
        score += 8

    for result in results:

        title = result["title"].lower()
        snippet = result["snippet"].lower()

        text = f"{title} {snippet}"

        if normalized in text:
            score += 2

        for word in (
            "videojuego",
            "videojuegos",
            "gaming",
            "juego",
            "juegos",
            "video game",
            "games",
        ):
            if word in text:
                score += 2

    return score


# ------------------------------------------------------------
# Escritura y formato
# ------------------------------------------------------------

def _is_all_caps(term: str) -> bool:
    letters = re.sub(
        r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]",
        "",
        term,
    )

    return (
        bool(letters)
        and letters == letters.upper()
    )


def _capitalization(
    term: str,
) -> str:

    if _is_all_caps(term):
        return "Altas"

    return "Altas y bajas"


def _format_recommendation(
    term: str,
    classification: str,
) -> dict:

    capitalization = _capitalization(term)

    if classification == "videojuego":
        return {
            "style": "Cursivas",
            "capitalization": capitalization,
            "label": (
                "Cursivas + "
                + capitalization
            ),
            "reason": (
                "Se trata probablemente "
                "del título de una obra."
            ),
        }

    if classification == "personaje":
        return {
            "style": "Redonda",
            "capitalization": capitalization,
            "label": capitalization,
            "reason": (
                "Es un nombre propio de "
                "personaje."
            ),
        }

    if classification == "lugar_ficticio":
        return {
            "style": "Redonda",
            "capitalization": capitalization,
            "label": capitalization,
            "reason": (
                "Es un nombre propio "
                "de lugar."
            ),
        }

    if classification == "nombre_propio":
        return {
            "style": "Redonda",
            "capitalization": capitalization,
            "label": capitalization,
            "reason": (
                "Se comporta como nombre propio."
            ),
        }

    if classification == "termino_videojuegos":
        return {
            "style": "Redonda",
            "capitalization": capitalization,
            "label": capitalization,
            "reason": (
                "Parece un término de uso "
                "especializado en videojuegos."
            ),
        }

    return {
        "style": "Redonda",
        "capitalization": capitalization,
        "label": capitalization,
        "reason": (
            "No se encontró evidencia "
            "suficiente para aplicar cursivas."
        ),
    }


# ------------------------------------------------------------
# Extraccion de significado
# ------------------------------------------------------------

def _extract_meaning(
    term: str,
    classification: str,
    results: list[dict],
) -> str:

    if not results:
        return ""

    # Preferimos snippets que contengan el término.
    normalized = _normalise_term(term)

    candidates = []

    for result in results:

        combined = (
            result["title"]
            + " "
            + result["snippet"]
        )

        if normalized in combined.lower():
            candidates.append(result)

    if not candidates:
        candidates = results

    best = candidates[0]

    snippet = best.get(
        "snippet",
        "",
    ).strip()

    if not snippet:
        return (
            f"Coincidencia encontrada en "
            f"{best.get('domain', 'la web')}."
        )

    # Limpiar ruido típico.
    snippet = re.sub(
        r"\s+",
        " ",
        snippet,
    )

    return snippet[:360]


# ------------------------------------------------------------
# Sugerencia de escritura
# ------------------------------------------------------------

def _suggested_form(
    term: str,
    results: list[dict],
) -> str:

    if not results:
        return term

    normalized = _normalise_term(term)

    # Buscar coincidencia del término en títulos.
    for result in results:

        title = result["title"]

        if normalized in title.lower():

            match = re.search(
                re.escape(term),
                title,
                flags=re.IGNORECASE,
            )

            if match:
                return match.group(0)

    # Si no podemos determinar una variante concreta,
    # conservamos la escritura observada por el autor.
    return term


# ------------------------------------------------------------
# Verificacion individual
# ------------------------------------------------------------

def verify_term(
    term: str,
) -> dict:

    cached = _cache_get(term)

    if cached:
        cached["from_cache"] = True
        return cached

    clean_term = term.strip()

    if not clean_term:
        return {
            "status": "ignored",
            "term": term,
        }

    # Dos consultas:
    #
    # 1. búsqueda exacta
    # 2. búsqueda contextual relacionada con videojuegos
    #
    # Esto es especialmente importante para:
    # Ganon, Hyrule, Horizon Zero Dawn, etc.

    queries = [
        f'"{clean_term}"',
        f'"{clean_term}" videojuego',
    ]

    results = []

    seen_urls = set()

    for query in queries:

        for result in _google_search(query):

            url = result["url"]

            if url in seen_urls:
                continue

            seen_urls.add(url)
            results.append(result)

    if not results:

        result = {
            "status": "not_found",
            "term": clean_term,
            "found": False,
            "possible_proper_name": False,
            "possible_video_game": False,
            "classification": "sin_confirmar",
            "confidence": "baja",
            "meaning": "",
            "suggested_form": clean_term,
            "formatting": _format_recommendation(
                clean_term,
                "sin_confirmar",
            ),
            "evidence": [],
            "source": (
                "Búsqueda web HTML "
                "(sin API)"
            ),
        }

        _cache_set(
            clean_term,
            result,
        )

        return result

    game_score = _score_game(
        clean_term,
        results,
    )

    character_score = _score_character(
        clean_term,
        results,
    )

    place_score = _score_place(
        clean_term,
        results,
    )

    proper_score = _score_proper_name(
        clean_term,
        results,
    )

    game_term_score = _score_game_term(
        clean_term,
        results,
    )

    # --------------------------------------------------------
    # Clasificacion
    # --------------------------------------------------------

    scores = {
        "videojuego": game_score,
        "personaje": character_score,
        "lugar_ficticio": place_score,
        "nombre_propio": proper_score,
        "termino_videojuegos": game_term_score,
    }

    classification = max(
        scores,
        key=scores.get,
    )

    best_score = scores[classification]

    # Para evitar falsos positivos:
    # exigimos un mínimo de evidencia.
    if best_score < 6:
        classification = "sin_confirmar"
        best_score = 0

    # Si es término explícitamente conocido de videojuegos,
    # permitimos la clasificación aunque Google tenga pocos
    # resultados.
    if (
        game_term_score >= 8
        and game_term_score >= best_score
    ):
        classification = "termino_videojuegos"
        best_score = game_term_score

    if classification == "videojuego":
        confidence = (
            "alta"
            if game_score >= 16
            else "media"
        )

    elif classification in {
        "personaje",
        "lugar_ficticio",
        "nombre_propio",
    }:
        confidence = (
            "alta"
            if best_score >= 14
            else "media"
        )

    elif classification == "termino_videojuegos":
        confidence = (
            "alta"
            if game_term_score >= 12
            else "media"
        )

    else:
        confidence = "baja"

    formatting = _format_recommendation(
        clean_term,
        classification,
    )

    suggested = _suggested_form(
        clean_term,
        results,
    )

    evidence = []

    for result in results[:5]:

        evidence.append(
            {
                "title": result["title"],
                "url": result["url"],
                "domain": result["domain"],
                "snippet": result["snippet"],
            }
        )

    result = {
        "status": "verified",
        "term": clean_term,
        "found": True,

        "possible_proper_name": classification
        in {
            "nombre_propio",
            "personaje",
            "lugar_ficticio",
        },

        "possible_video_game": classification
        == "videojuego",

        "classification": classification,
        "classification_label": {
            "videojuego": "Posible videojuego",
            "personaje": "Posible personaje",
            "lugar_ficticio": "Posible lugar ficticio",
            "nombre_propio": "Posible nombre propio",
            "termino_videojuegos": (
                "Término de videojuegos"
            ),
            "sin_confirmar": (
                "Coincidencia web sin "
                "clasificación suficiente"
            ),
        }.get(
            classification,
            "Sin clasificar",
        ),

        "confidence": confidence,

        "meaning": _extract_meaning(
            clean_term,
            classification,
            results,
        ),

        "suggested_form": suggested,

        "formatting": formatting,

        "scores": scores,

        "evidence": evidence,

        "source": (
            "Google — búsqueda web HTML "
            "(sin API)"
        ),
    }

    _cache_set(
        clean_term,
        result,
    )

    return result


# ------------------------------------------------------------
# Integracion con auditor
# ------------------------------------------------------------

def _should_verify(
    error: dict,
) -> bool:

    category = error.get(
        "category",
        "",
    )

    return category in {
        "Ortografia",
        "Gramatica / Puntuacion",
    }


def verify_errors(
    errors: list[dict],
) -> list[dict]:

    candidatos = [
        error
        for error in errors
        if _should_verify(error)
    ]

    # Evitar consultas duplicadas.
    terms = []

    seen = set()

    for error in candidatos:

        term = error.get(
            "text",
            "",
        ).strip()

        key = _cache_key(term)

        if (
            not term
            or key in seen
        ):
            continue

        seen.add(key)
        terms.append(term)

    terms = terms[:MAX_TERMS]

    if not terms:
        return errors

    results = {}

    # Varias consultas en paralelo para que un guion
    # razonablemente grande no tarde demasiado.
    with ThreadPoolExecutor(
        max_workers=5
    ) as executor:

        futures = {
            executor.submit(
                verify_term,
                term,
            ): term
            for term in terms
        }

        for future in as_completed(futures):

            term = futures[future]

            try:
                results[
                    _cache_key(term)
                ] = future.result()

            except Exception as exc:

                results[
                    _cache_key(term)
                ] = {
                    "status": "error",
                    "term": term,
                    "found": False,
                    "classification": (
                        "sin_confirmar"
                    ),
                    "confidence": "baja",
                    "meaning": "",
                    "suggested_form": term,
                    "formatting": {
                        "style": "Redonda",
                        "capitalization": (
                            "Altas y bajas"
                        ),
                        "label": (
                            "Altas y bajas"
                        ),
                        "reason": (
                            "No se pudo verificar "
                            "el término."
                        ),
                    },
                    "evidence": [],
                    "error": str(exc),
                    "source": (
                        "Verificación web"
                    ),
                }

    # --------------------------------------------------------
    # Adjuntar resultados a cada error.
    # --------------------------------------------------------

    for error in errors:

        if not _should_verify(error):
            continue

        term = error.get(
            "text",
            "",
        ).strip()

        verification = results.get(
            _cache_key(term)
        )

        if not verification:
            continue

        error["web_verification"] = verification

        # ----------------------------------------------------
        # Agregar la recomendacion a la lista de sugerencias.
        # ----------------------------------------------------

        confidence = verification.get(
            "confidence"
        )

        suggested = verification.get(
            "suggested_form"
        )

        classification = verification.get(
            "classification"
        )

        if (
            confidence in {
                "media",
                "alta",
            }
            and classification
            != "sin_confirmar"
        ):

            suggestions = list(
                error.get(
                    "suggestions",
                    [],
                )
                or []
            )

            formatting = verification.get(
                "formatting",
                {},
            )

            label = formatting.get(
                "label",
                "",
            )

            if suggested:
                if label:
                    web_suggestion = (
                        f"{suggested} "
                        f"({label})"
                    )
                else:
                    web_suggestion = suggested

                # Evitar duplicados.
                if web_suggestion not in suggestions:
                    suggestions.insert(
                        0,
                        web_suggestion,
                    )

            error["suggestions"] = suggestions

    return errors