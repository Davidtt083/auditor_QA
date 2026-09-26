"""Consulta factual en cascada con cache: glosario, RAE, Wikcionario, Wikipedia.

Reglas del modulo:
  * nunca inventa una definicion;
  * siempre devuelve la fuente y su URL;
  * nunca deja caer la peticion por un fallo de red (timeout corto + fallback).
"""

from __future__ import annotations

import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
GLOSSARY_PATH = BASE_DIR / "glosario.json"
CACHE_PATH = BASE_DIR / "cache_definiciones.json"

TIMEOUT = float(os.getenv("QA_LOOKUP_TIMEOUT", "4"))
CACHE_TTL = int(os.getenv("QA_CACHE_TTL", str(60 * 60 * 24 * 30)))  # 30 dias
USER_AGENT = "QA-Text-Auditor/2.0 (auditor determinista; contacto: davidtt083@github)"

# Busqueda web real (Google Programmable Search Engine).
# Se activa poniendo las dos variables de entorno; sin ellas el auditor
# sigue funcionando con la cascada RAE / Wikcionario / Wikipedia de siempre.
GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")
GOOGLE_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"

# Busqueda web sin API key (DuckDuckGo HTML). Es el metodo por defecto:
# no requiere ninguna variable de entorno. Si mas adelante configuras
# GOOGLE_CSE_API_KEY / GOOGLE_CSE_ID, Google se intenta primero porque
# su JSON es mas estable, y DuckDuckGo queda como respaldo automatico.
DUCKDUCKGO_ENDPOINT = "https://html.duckduckgo.com/html/"

# Dominios que SI se aceptan como fuente de definicion para un tecnicismo o
# extranjerismo. Fuera de esta lista el resultado se descarta: preferimos
# no anotar nada antes que citar una fuente poco confiable para QA.
DOMINIOS_CONFIABLES = (
    "rae.es", "fundeu.es", "wikipedia.org", "wiktionary.org",
    "es.wikipedia.org", "developer.mozilla.org", "docs.microsoft.com",
    "learn.microsoft.com", "aws.amazon.com", "cloud.google.com",
    "iso.org", "itu.int", "w3.org", "owasp.org", "atlassian.com",
    "digitalocean.com", "freecodecamp.org", "geeksforgeeks.org",
    "es.stackoverflow.com", "redhat.com", "ibm.com",
)


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


# ---------------------------------------------------------------------------
# Cache persistente en disco (evita repetir consultas en cada analisis)
# ---------------------------------------------------------------------------

def _load_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    try:
        with CACHE_PATH.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


_CACHE: dict[str, Any] = _load_cache()


def _cache_get(term: str) -> dict[str, Any] | None:
    entry = _CACHE.get(_normalise(term))
    if not entry:
        return None
    if time.time() - entry.get("_ts", 0) > CACHE_TTL:
        return None
    return {k: v for k, v in entry.items() if k != "_ts"}


def _cache_set(term: str, result: dict[str, Any]) -> None:
    _CACHE[_normalise(term)] = {**result, "_ts": time.time()}
    try:
        with CACHE_PATH.open("w", encoding="utf-8") as fh:
            json.dump(_CACHE, fh, ensure_ascii=False, indent=1)
    except OSError:
        pass  # el cache es opcional: si el disco es de solo lectura, seguimos


# ---------------------------------------------------------------------------
# Fuente 1: glosario interno (la mas confiable para terminologia propia)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_glossary() -> dict[str, Any]:
    if not GLOSSARY_PATH.exists():
        return {}
    with GLOSSARY_PATH.open(encoding="utf-8") as glossary_file:
        return json.load(glossary_file)


@lru_cache(maxsize=1)
def _glossary_index() -> dict[str, dict[str, Any]]:
    """Indexa el glosario por clave y por alias, en minusculas."""
    index: dict[str, dict[str, Any]] = {}
    for key, entry in _load_glossary().items():
        claves = {key, entry.get("term", key), *entry.get("alias", [])}
        for clave in claves:
            index[_normalise(str(clave))] = entry
    return index


def terminos_glosario() -> list[str]:
    """Terminos canonicos del glosario, para buscarlos dentro del texto."""
    return [entry.get("term", key) for key, entry in _load_glossary().items()]


def _glossary_lookup(term: str) -> dict[str, Any] | None:
    entry = _glossary_index().get(_normalise(term))
    if not entry:
        return None
    return {
        "term": entry.get("term", term),
        "definition": entry.get("definition", ""),
        "recommended": entry.get("recomendado", ""),
        "source": entry.get("source", "Glosario interno"),
        "source_url": entry.get("source_url", ""),
    }


# ---------------------------------------------------------------------------
# Fuentes remotas
# ---------------------------------------------------------------------------
def _sugerencias_formato_rae(tipo_nombre: str, termino: str) -> dict[str, Any]:
    """Retorna sugerencias de formato segun reglas de RAE para nombres propios."""
    sugerencias = {
        "tipo": tipo_nombre,
        "formatos": [],
    }

    # Videojuegos: generalmente en italicas, nombre original si es internacional
    if "videojuego" in tipo_nombre.lower():
        sugerencias["formatos"] = [
            {
                "formato": "Itálicas",
                "ejemplo": f"*{termino}*",
                "notas": "Títulos de videojuegos en itálicas (como libros o películas)"
            },
            {
                "formato": "Nombre original con mayúsculas",
                "ejemplo": termino,
                "notas": "Si el videojuego es internacional, puede mantenerse el nombre original"
            }
        ]

    # Personajes y lugares: Mayúscula inicial (nombre propio)
    elif any(x in tipo_nombre.lower() for x in ["personaje", "lugar", "ubicacion"]):
        sugerencias["formatos"] = [
            {
                "formato": "Mayúscula inicial",
                "ejemplo": termino.capitalize() if termino else termino,
                "notas": "Nombres propios se escriben con mayúscula inicial"
            }
        ]

    # Otros títulos de obras
    elif "título" in tipo_nombre.lower() or "obra" in tipo_nombre.lower():
        sugerencias["formatos"] = [
            {
                "formato": "Itálicas",
                "ejemplo": f"*{termino}*",
                "notas": "Títulos de obras (libros, series, películas) en itálicas"
            },
            {
                "formato": "Mayúsculas principales (Title Case)",
                "ejemplo": " ".join(w.capitalize() for w in termino.split()),
                "notas": "En inglés, principales palabras se capitalizan"
            }
        ]

    return sugerencias


def _wikipedia_search_nombre_propio(term: str) -> dict[str, Any] | None:
    """Busca en Wikipedia si el termino es un nombre propio conocido.

    Para guiones de videojuegos: detecta titulos, personajes, lugares, enemigos.
    Extrae descripcion completa y detalla qué es exactamente.
    """
    resultado = _mediawiki_extract("es.wikipedia.org", term)
    if not resultado:
        resultado = _mediawiki_extract("en.wikipedia.org", term)
    if not resultado:
        return None

    extract, titulo = resultado
    if not extract or len(extract) < 20:
        return None

    # Detectar tipo de nombre propio con heurísticas mejoradas
    extract_lower = extract.lower()
    
    # Buscar keywords específicas en ORDEN (más específico primero)
    tipo_nombre = "Nombre propio"
    
    if any(w in extract_lower for w in ["personaje", "character", "protagonista", "antagonista", "villain", "hero", "heroe"]):
        tipo_nombre = "Personaje"
    elif any(w in extract_lower for w in ["videojuego", "video game", "juego de ordenador", "juego informatico", "juego digital", "game"]):
        tipo_nombre = "Título de videojuego"
    elif any(w in extract_lower for w in ["serie", "series", "franchise", "saga"]):
        tipo_nombre = "Serie de videojuegos"
    elif any(w in extract_lower for w in ["lugar", "region", "pais", "ciudad", "location", "kingdom", "reino", "world", "mundo"]):
        tipo_nombre = "Lugar / Ubicación"
    elif any(w in extract_lower for w in ["pelicula", "film", "serie", "novela", "libro", "movie", "tv series", "show"]):
        tipo_nombre = "Título de obra"
    
    # Extraer descripcion completa (no solo primera línea)
    # Tomar los primeros 2-3 párrafos o hasta 400 caracteres
    parrafos = extract.split("\n\n")
    descripcion = ""
    for parrafo in parrafos[:2]:
        if descripcion:
            descripcion += "\n\n"
        descripcion += parrafo.strip()
        if len(descripcion) > 300:
            break
    
    # Limpiar descripcion (remover saltos extra)
    descripcion = re.sub(r"\n+", " ", descripcion).strip()
    if len(descripcion) > 500:
        descripcion = descripcion[:500].rsplit(" ", 1)[0] + "..."
    
    return {
        "term": titulo,
        "definition": descripcion,
        "source": "Wikipedia (Nombre propio verificado)",
        "source_url": f"https://es.wikipedia.org/wiki/{quote(titulo)}",
        "es_nombre_propio": True,
        "tipo_nombre": tipo_nombre,
    }

def _sugerencias_formato_rae(tipo_nombre: str, termino: str) -> dict[str, Any]:
    """Retorna sugerencias de formato segun reglas de RAE para nombres propios."""
    sugerencias = {
        "tipo": tipo_nombre,
        "formatos": [],
    }

    # Videojuegos: generalmente en italicas, nombre original si es internacional
    if "videojuego" in tipo_nombre.lower():
        sugerencias["formatos"] = [
            {
                "formato": "Itálicas",
                "ejemplo": f"*{termino}*",
                "notas": "Títulos de videojuegos en itálicas (como libros o películas)"
            },
            {
                "formato": "Nombre original con mayúsculas",
                "ejemplo": termino,
                "notas": "Si el videojuego es internacional, puede mantenerse el nombre original"
            }
        ]

    # Personajes y lugares: Mayúscula inicial (nombre propio)
    elif any(x in tipo_nombre.lower() for x in ["personaje", "lugar", "ubicacion"]):
        sugerencias["formatos"] = [
            {
                "formato": "Mayúscula inicial",
                "ejemplo": termino.capitalize() if termino else termino,
                "notas": "Nombres propios se escriben con mayúscula inicial"
            }
        ]

    # Otros títulos de obras
    elif "título" in tipo_nombre.lower() or "obra" in tipo_nombre.lower():
        sugerencias["formatos"] = [
            {
                "formato": "Itálicas",
                "ejemplo": f"*{termino}*",
                "notas": "Títulos de obras (libros, series, películas) en itálicas"
            },
            {
                "formato": "Mayúsculas principales (Title Case)",
                "ejemplo": " ".join(w.capitalize() for w in termino.split()),
                "notas": "En inglés, principales palabras se capitalizan"
            }
        ]

    return sugerencias


def _wikipedia_search_nombre_propio(term: str) -> dict[str, Any] | None:
    """Busca en Wikipedia si el termino es un nombre propio conocido.

    Para guiones de videojuegos es critico: detecta titulos, personajes, lugares.
    Retorna metadatos sobre el tipo de nombre propio y sugerencias de formato.
    """
    resultado = _mediawiki_extract("es.wikipedia.org", term)
    if not resultado:
        resultado = _mediawiki_extract("en.wikipedia.org", term)
    if not resultado:
        return None

    extract, titulo = resultado
    primeras_lineas = extract.split("\n")[:2]
    descripcion = " ".join(primeras_lineas).strip()
    if len(descripcion) < 15:
        return None

    # Heuristicas simples para detectar tipo de nombre propio
    descripcion_lower = descripcion.lower()
    es_videojuego = any(p in descripcion_lower for p in ("videojuego", "video game", "juego de ordenador", "juego informatico", "juego digital"))
    es_personaje = any(p in descripcion_lower for p in ("personaje", "character", "heroe", "hero", "antagonista"))
    es_lugar = any(p in descripcion_lower for p in ("lugar", "region", "pais", "ciudad", "location", "kingdom", "reino"))
    es_titulo_media = any(p in descripcion_lower for p in ("pelicula", "film", "serie", "novela", "libro", "movie", "tv series", "show"))

    tipo_nombre = "Nombre propio"
    if es_videojuego:
        tipo_nombre = "Título de videojuego"
    elif es_personaje:
        tipo_nombre = "Personaje"
    elif es_lugar:
        tipo_nombre = "Lugar / Ubicación"
    elif es_titulo_media:
        tipo_nombre = "Título de obra"

    return {
        "term": titulo,
        "definition": descripcion,
        "source": "Wikipedia (Nombre propio verificado)",
        "source_url": f"https://es.wikipedia.org/wiki/{quote(titulo)}",
        "es_nombre_propio": True,
        "tipo_nombre": tipo_nombre,
    }



def _dominio_de(url: str) -> str:
    from urllib.parse import urlparse
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _dominio_confiable(url: str) -> bool:
    dominio = _dominio_de(url)
    return any(dominio == d or dominio.endswith("." + d) for d in DOMINIOS_CONFIABLES)


def _resolver_url_ddg(href: str) -> str:
    """DuckDuckGo envuelve los enlaces en un redirector propio; lo desarma."""
    if href.startswith("//"):
        href = "https:" + href
    partes = urlparse(href)
    if partes.netloc.endswith("duckduckgo.com") and partes.path == "/l/":
        destino = parse_qs(partes.query).get("uddg", [""])[0]
        return unquote(destino)
    return href


def _parse_duckduckgo_html(html: str) -> list[tuple[str, str]]:
    """Extrae (url, fragmento) de la pagina de resultados HTML de DuckDuckGo."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    resultados: list[tuple[str, str]] = []
    for bloque in soup.select(".result__body, .web-result"):
        enlace = bloque.select_one(".result__a")
        fragmento = bloque.select_one(".result__snippet")
        if not enlace or not fragmento:
            continue
        href = enlace.get("href", "")
        if not href:
            continue
        url = _resolver_url_ddg(href)
        texto = fragmento.get_text(" ", strip=True)
        if url and texto:
            resultados.append((url, texto))
    return resultados


def _duckduckgo_lookup(term: str, es_extranjerismo: bool = False) -> dict[str, Any] | None:
    """Busqueda web sin API key, via la version HTML de DuckDuckGo.

    Mismo contrato que _web_search_lookup: nunca redacta una definicion,
    solo toma el fragmento que el buscador ya devuelve, y solo de un
    dominio en DOMINIOS_CONFIABLES.
    """
    consulta = f"{term} significado tecnico" if es_extranjerismo else f"{term} definicion"
    try:
        import requests
        response = requests.get(
            DUCKDUCKGO_ENDPOINT,
            params={"q": consulta, "kl": "es-es"},
            timeout=TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "es-ES,es;q=0.9",
            },
        )
        if response.status_code != 200:
            return None
        html = response.text
    except Exception:
        return None

    for url, fragmento in _parse_duckduckgo_html(html):
        if not _dominio_confiable(url):
            continue
        fragmento = re.sub(r"\s+", " ", fragmento).strip()
        if len(fragmento) < 25:
            continue
        if len(fragmento) > 500:
            fragmento = fragmento[:500].rsplit(" ", 1)[0] + "..."
        return {
            "term": term,
            "definition": fragmento,
            "source": f"Busqueda web ({_dominio_de(url)})",
            "source_url": url,
        }
    return None


def _web_search_lookup(term: str, es_extranjerismo: bool = False) -> dict[str, Any] | None:
    """Busca el significado del termino en la web real (Google CSE).

    Solo se usa si GOOGLE_CSE_API_KEY y GOOGLE_CSE_ID estan configuradas.
    Nunca redacta una definicion: toma el fragmento (snippet) que Google
    ya devuelve para el resultado y cita la pagina de origen. Si ningun
    resultado cae en DOMINIOS_CONFIABLES, no se anota nada.
    """
    if not (GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID):
        return None

    consulta = f'{term} significado tecnico' if es_extranjerismo else f'{term} definicion'
    data = _get_json(
        GOOGLE_CSE_ENDPOINT,
        {
            "key": GOOGLE_CSE_API_KEY,
            "cx": GOOGLE_CSE_ID,
            "q": consulta,
            "num": "5",
            "hl": "es",
            "gl": "es",
        },
    )
    if not data:
        return None

    for item in data.get("items", []):
        url = item.get("link", "")
        snippet = (item.get("snippet") or "").replace("\n", " ").strip()
        if not url or not snippet or len(snippet) < 25:
            continue
        if not _dominio_confiable(url):
            continue
        snippet = re.sub(r"\s+", " ", snippet)
        if len(snippet) > 500:
            snippet = snippet[:500].rsplit(" ", 1)[0] + "..."
        return {
            "term": item.get("title", term).split(" - ")[0].split(" | ")[0][:80],
            "definition": snippet,
            "source": f"Busqueda web ({_dominio_de(url)})",
            "source_url": url,
        }
    return None



def _get_json(url: str, params: dict[str, str]) -> dict[str, Any] | None:
    try:
        import requests
        response = requests.get(
            url, params=params, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}
        )
        if response.status_code != 200:
            return None
        return response.json()
    except Exception:  # red caida, proxy bloqueado, JSON invalido
        return None


def _mediawiki_extract(host: str, term: str) -> tuple[str, str] | None:
    data = _get_json(
        f"https://{host}/w/api.php",
        {
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "explaintext": "1",
            "redirects": "1",
            "titles": term,
        },
    )
    if not data:
        return None
    pages = data.get("query", {}).get("pages", {})
    for page_id, page in pages.items():
        if page_id == "-1":
            continue
        extract = (page.get("extract") or "").strip()
        if extract:
            return extract, page.get("title", term)
    return None


def _wikcionario_lookup(term: str) -> dict[str, Any] | None:
    resultado = _mediawiki_extract("es.wiktionary.org", term)
    if not resultado:
        return None
    extract, titulo = resultado
    definicion = _primera_acepcion(extract)
    if not definicion:
        return None
    return {
        "term": titulo,
        "definition": definicion,
        "source": "Wikcionario en espanol",
        "source_url": f"https://es.wiktionary.org/wiki/{quote(titulo)}",
    }


def _wikipedia_lookup(term: str, idioma: str = "es") -> dict[str, Any] | None:
    resultado = _mediawiki_extract(f"{idioma}.wikipedia.org", term)
    if not resultado:
        return None
    extract, titulo = resultado
    definicion = " ".join(extract.split("\n")[0].split())
    if len(definicion) < 20:
        return None
    if len(definicion) > 600:
        definicion = definicion[:600].rsplit(" ", 1)[0] + "..."
    etiqueta = "Wikipedia en espanol" if idioma == "es" else "Wikipedia en ingles"
    return {
        "term": titulo,
        "definition": definicion,
        "source": etiqueta,
        "source_url": f"https://{idioma}.wikipedia.org/wiki/{quote(titulo)}",
    }


def _primera_acepcion(extract: str) -> str:
    """Extrae la primera linea util de un articulo de Wikcionario."""
    for linea in extract.split("\n"):
        limpia = linea.strip()
        if not limpia or limpia.startswith("="):
            continue
        limpia = re.sub(r"^\d+[\.\)]\s*", "", limpia)
        if len(limpia) >= 15:
            return limpia[:400]
    return ""


def _rae_lookup(term: str) -> dict[str, Any] | None:
    """RAE via pyrae. Opcional: en PythonAnywhere free suele estar bloqueado."""
    if os.getenv("QA_USE_RAE", "1") != "1":
        return None
    try:
        from pyrae import dle
        result = dle.search_by_word(word=term)
        definition = _extract_definition(result)
        if definition:
            return {
                "term": term,
                "definition": definition[:400],
                "source": "Real Academia Espanola (DLE)",
                "source_url": f"https://dle.rae.es/{quote(term)}",
            }
    except Exception:
        return None
    return None


def _extract_definition(value: Any, profundidad: int = 0) -> str:
    """Extrae solo texto devuelto por pyrae, sin fabricar una definicion."""
    if profundidad > 6:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("sentence", "definition", "definitions", "meaning", "text"):
            if key in value:
                extracted = _extract_definition(value[key], profundidad + 1)
                if extracted:
                    return extracted
    if isinstance(value, (list, tuple)):
        for item in value:
            extracted = _extract_definition(item, profundidad + 1)
            if extracted:
                return extracted
    for attribute in ("meanings", "definitions", "sentence", "definition", "meaning", "text"):
        if hasattr(value, attribute):
            extracted = _extract_definition(getattr(value, attribute), profundidad + 1)
            if extracted:
                return extracted
    return ""


# ---------------------------------------------------------------------------
# Cascada
# ---------------------------------------------------------------------------

def lookup_term(term: str, es_extranjerismo: bool = False) -> dict[str, Any]:
    """Primera fuente factual disponible, en orden de confiabilidad.

    Si la palabra fue marcada como extranjerismo, la RAE se consulta igual
    (muchos anglicismos ya estan admitidos: 'chat', 'web', 'bit'), pero
    Wikipedia pasa antes que Wikcionario porque describe mejor el tecnicismo.
    """
    cleaned = term.strip()
    if not cleaned:
        return {"term": term, "found": False, "source": "Sin consulta"}

    en_cache = _cache_get(cleaned)
    if en_cache is not None:
        return en_cache

    glosario = _glossary_lookup(cleaned)
    if glosario and glosario.get("definition"):
        final = {**glosario, "found": True}
        _cache_set(cleaned, final)
        return final

    # IMPORTANTE: antes de intentar la cascada de definiciones, verificar si es
    # un nombre propio (titulo, personaje, lugar) en Wikipedia. Esto detiene
    # falsos positivos en textos de videojuegos: "Horizon Zero Dawn" no es una
    # falta ortografica, es un nombre propio verificado.
    nombre_propio = _wikipedia_search_nombre_propio(cleaned)
    if nombre_propio and nombre_propio.get("es_nombre_propio"):
        sugerencias = _sugerencias_formato_rae(nombre_propio["tipo_nombre"], cleaned)
        final = {**nombre_propio, "found": True, "format_suggestions": sugerencias}
        _cache_set(cleaned, final)
        return final

    if es_extranjerismo:
        # Para jerga / tecnicismos, la busqueda web real va primero: es la
        # que mejor sigue el ritmo de terminos nuevos (frameworks, roles,
        # herramientas) que el diccionario y Wikipedia tardan en cubrir.
        # DuckDuckGo no requiere ninguna clave y es el metodo por defecto;
        # si configuras Google CSE, se intenta primero por ser mas estable,
        # y DuckDuckGo queda como respaldo automatico si Google falla.
        fuentes_busqueda = []
        if GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID:
            fuentes_busqueda.append(lambda t: _web_search_lookup(t, es_extranjerismo=True))
        fuentes_busqueda.append(lambda t: _duckduckgo_lookup(t, es_extranjerismo=True))
        cascada = tuple(fuentes_busqueda) + (_rae_lookup, _wikipedia_lookup, _wikcionario_lookup)
    else:
        cascada = (_rae_lookup, _wikcionario_lookup, _wikipedia_lookup)

    result: dict[str, Any] | None = None
    for fuente in cascada:
        result = fuente(cleaned)
        if result and result.get("definition"):
            break
        result = None

    if result is None and es_extranjerismo:
        result = _wikipedia_lookup(cleaned, idioma="en")

    if result:
        final = {**result, "found": True}
    else:
        final = {
            "term": cleaned,
            "found": False,
            "definition": "No se encontro una entrada en las fuentes configuradas.",
            "source": "Sin resultado factual",
            "source_url": "",
        }
    _cache_set(cleaned, final)
    return final
