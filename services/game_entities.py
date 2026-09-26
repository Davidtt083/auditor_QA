"""Detección y clasificación factual de videojuegos, personajes y jerga lúdica."""

from __future__ import annotations

import re
from typing import Any
from services.dictionary_lookup import _get_json, _mediawiki_extract, _cache_get, _cache_set

# Jerga gamer común, adaptaciones y préstamos lúdicos
GAMING_JARGON: dict[str, dict[str, str]] = {
    "crafteo": {
        "term": "crafteo",
        "category": "Jerga de videojuegos",
        "definition": "Acción de fabricar, crear o sintetizar objetos, armas o herramientas a partir de materias primas recolectadas.",
        "recommended": "fabricación, creación, elaboración",
        "rae_rule": "Adaptación morfológica del inglés 'crafting'. Según Fundéu y la RAE, se recomienda usar los términos patrimoniales 'fabricación' o 'creación'. En redacción temática se admite en redonda sin cursiva al tener desinencia verbal y flexión española.",
        "source": "Glosario técnico de localización de videojuegos"
    },
    "craftear": {
        "term": "craftear",
        "category": "Jerga de videojuegos",
        "definition": "Fabricar o sintetizar objetos y equipamiento dentro del entorno del juego.",
        "recommended": "fabricar, forjar, crear",
        "rae_rule": "Préstamo adaptado morfológicamente. Recomendada alternativa patrimonial en textos formales.",
        "source": "Glosario técnico de localización de videojuegos"
    },
    "farmeo": {
        "term": "farmeo",
        "category": "Jerga de videojuegos",
        "definition": "Realizar acciones repetitivas para conseguir experiencia, dinero o recursos.",
        "recommended": "recolección repetitiva, cosecha de recursos",
        "rae_rule": "Adaptación coloquial de 'farming'. En redonda con flexión española; en estilo formal preferir 'recolección'.",
        "source": "Glosario técnico de localización de videojuegos"
    },
    "lootear": {
        "term": "lootear",
        "category": "Jerga de videojuegos",
        "definition": "Recoger el botín dejado por enemigos o cofres.",
        "recommended": "recoger botín, despojar",
        "rae_rule": "Verbo híbrido (del inglés 'loot'). Se aconseja 'recoger botín' o 'saquear'.",
        "source": "Glosario técnico de localización de videojuegos"
    },
    "lore": {
        "term": "lore",
        "category": "Jerga de videojuegos",
        "definition": "Conjunto de historias, mitología, trasfondo y tradiciones que componen el universo de una obra de ficción.",
        "recommended": "trasfondo, historia interna, mitología",
        "rae_rule": "Anglicismo crudo. Debe escribirse en cursiva (*lore*) según la RAE o sustituirse por 'trasfondo'.",
        "source": "FundéuRAE"
    },
    "gameplay": {
        "term": "gameplay",
        "category": "Jerga de videojuegos",
        "definition": "Mecánicas, dinámicas y experiencia directa que experimenta el jugador al interactuar con el juego.",
        "recommended": "jugabilidad",
        "rae_rule": "Extranjerismo innecesario. La RAE y Fundéu recomiendan el término en español 'jugabilidad'. Si se usa el anglicismo, debe ir en cursiva (*gameplay*).",
        "source": "RAE / FundéuRAE"
    },
    "spawn": {
        "term": "spawn",
        "category": "Jerga de videojuegos",
        "definition": "Aparición o reaparición de un personaje, enemigo u objeto en un punto del mapa.",
        "recommended": "aparición, punto de reaparición",
        "rae_rule": "Extranjerismo crudo; debe escribirse en cursiva (*spawn*) según la norma ortográfica de la RAE.",
        "source": "Glosario técnico de localización de videojuegos"
    }
}

# Patrón para identificar candidatos a nombres propios o títulos compuestos:
# Coincide con secuencias como "Horizon Zero Dawn", "The Legend of Zelda: Breath of the Wild", "Aloy", "Hyrule", etc.
_PROPER_NOUN_SEQ = re.compile(
    r"\b[A-ZÁÉÍÓÚÑ][a-zA-Z0-9áéíóúñ]*(?::?\s+(?:[A-ZÁÉÍÓÚÑ][a-zA-Z0-9áéíóúñ]*|of|the|and|de|del|la|los|las|y|in|on|at|for|to|a|an)\b)*",
    re.UNICODE
)

def _extraer_metadatos_videojuego(extract: str) -> dict[str, str]:
    """Extrae de manera determinista productora, desarrolladora y año si existen."""
    meta = {}
    
    # Búsqueda de desarrollador / editor
    m_dev = re.search(r"(?:desarrollado por|developed by)\s+([A-ZÁÉÍÓÚ][\w\s&]+?)(?=[,\.]|\s+(?:y|and|publicado|published))", extract, re.I)
    if m_dev:
        meta["desarrolladora"] = m_dev.group(1).strip()
        
    m_pub = re.search(r"(?:publicado por|distribuido por|published by)\s+([A-ZÁÉÍÓÚ][\w\s&]+?)(?=[,\.]|\s+(?:en|para|for|on))", extract, re.I)
    if m_pub:
        meta["productora"] = m_pub.group(1).strip()
        
    m_year = re.search(r"\b(19[89]\d|20[0-2]\d)\b", extract)
    if m_year:
        meta["año"] = m_year.group(1)
        
    return meta

def consultar_entidad_wikipedia(termino: str) -> dict[str, Any] | None:
    """Consulta Wikipedia (español e inglés) para saber si es videojuego o personaje."""
    cached = _cache_get(f"entity:{termino.lower()}")
    if cached:
        return cached

    for lang in ("es", "en"):
        res = _mediawiki_extract(f"{lang}.wikipedia.org", termino)
        if not res:
            continue
        extract, title = res
        primera_frase = extract.split(".")[0].lower() if extract else ""
        
        # Palabras clave de videojuegos
        es_juego = any(k in primera_frase for k in [
            "videojuego", "video game", "action-adventure game", "role-playing game",
            "juego de rol", "saga de videojuegos", "franquicia de videojuegos", "juego de acción"
        ])
        
        # Palabras clave de personajes o mundos de ficción
        es_personaje = any(k in primera_frase for k in [
            "personaje de", "character in", "protagonista", "protagonist", "antagonista",
            "fictional character", "villano", "antagonist", "personaje ficticio"
        ])
        
        es_lugar_ficcion = any(k in primera_frase for k in [
            "mundo ficticio", "reino ficticio", "fictional kingdom", "fictional world", "fictional land"
        ])
        
        if es_juego:
            meta = _extraer_metadatos_videojuego(extract)
            detalles_prod = []
            if "desarrolladora" in meta:
                detalles_prod.append(f"Desarrolladora: {meta['desarrolladora']}")
            if "productora" in meta:
                detalles_prod.append(f"Distribuidora/Editora: {meta['productora']}")
            if "año" in meta:
                detalles_prod.append(f"Año: {meta['año']}")
            datos_extra = (" (" + " · ".join(detalles_prod) + ")") if detalles_prod else ""
            
            data = {
                "term": title,
                "category": "Título de videojuego",
                "definition": f"Videojuego.{datos_extra} {extract[:350]}...",
                "metadata": meta,
                "rae_rule": (
                    "Según la Ortografía de la RAE y FundéuRAE: los títulos de videojuegos se escriben en CURSIVA (itálica). "
                    "En español solo la primera palabra y los nombres propios llevan mayúscula (*Horizon zero dawn*); "
                    "si se mantiene la grafía internacional en inglés con mayúsculas iniciales (*Horizon Zero Dawn*), "
                    "también debe escribirse siempre en CURSIVA (nunca en redonda sin comillas)."
                ),
                "source": f"Wikipedia en {lang}",
                "source_url": f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "found": True
            }
            _cache_set(f"entity:{termino.lower()}", data)
            return data

        if es_personaje:
            data = {
                "term": title,
                "category": "Personaje de ficción",
                "definition": f"Personaje de ficción. {extract[:300]}...",
                "metadata": {},
                "rae_rule": (
                    "Según la RAE: los nombres propios de personajes ficticios o mitológicos se escriben en LETRA REDONDA "
                    "(sin cursiva ni comillas) y con mayúscula inicial: «Aloy», «Ganon». "
                    "No constituyen faltas de ortografía ni extranjerismos."
                ),
                "source": f"Wikipedia en {lang}",
                "source_url": f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "found": True
            }
            _cache_set(f"entity:{termino.lower()}", data)
            return data

        if es_lugar_ficcion:
            data = {
                "term": title,
                "category": "Lugar / Universo de ficción",
                "definition": f"Lugar o elemento del universo de ficción. {extract[:300]}...",
                "metadata": {},
                "rae_rule": (
                    "Según la RAE: los nombres de comarcas, continentes, reinos o planetas ficticios se escriben con "
                    "mayúscula inicial y en letra redonda: «Hyrule», «Azeroth»."
                ),
                "source": f"Wikipedia en {lang}",
                "source_url": f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "found": True
            }
            _cache_set(f"entity:{termino.lower()}", data)
            return data

    return None

def analizar_entidades_y_jerga(text: str) -> list[dict[str, Any]]:
    """Localiza títulos de videojuegos, personajes y jerga dentro del texto."""
    hallazgos: list[dict[str, Any]] = []
    
    # 1. Jerga gamer preconfigurada
    for termino, info in GAMING_JARGON.items():
        patron = re.compile(r"\b" + re.escape(termino) + r"\b", re.I)
        for m in patron.finditer(text):
            hallazgos.append({
                "category": info["category"],
                "text": m.group(0),
                "message": f"{info['definition']} | {info['rae_rule']}",
                "suggestions": [info["recommended"]] if info.get("recommended") else [],
                "offset": m.start(),
                "length": len(m.group(0)),
                "rule_id": "QA_GAMING_JARGON",
                "source": info["source"],
                "lookup": {
                    "term": info["term"],
                    "category": info["category"],
                    "definition": info["definition"],
                    "recommended": info.get("recommended", ""),
                    "rae_rule": info["rae_rule"],
                    "source": info["source"],
                    "found": True
                }
            })

    # 2. Candidatos a Títulos y Nombres Propios
    candidatos: list[tuple[int, int, str]] = []
    for match in _PROPER_NOUN_SEQ.finditer(text):
        candidato = match.group(0).strip(" :")
        # Ignorar palabras sueltas al inicio de frase que sean artículos o verbos comunes
        if len(candidato) < 3 or candidato.lower() in {"el", "la", "los", "las", "considera", "donde", "para", "importante"}:
            continue
        candidatos.append((match.start(), len(candidato), candidato))

    # Ordenar priorizando frases más largas primero para capturar títulos completos
    candidatos.sort(key=lambda x: len(x[2]), reverse=True)
    
    tramos_tomados: list[tuple[int, int]] = [(h["offset"], h["offset"] + h["length"]) for h in hallazgos]

    for offset, length, termino in candidatos:
        fin = offset + length
        # Si ya está contenido en un hallazgo más largo, omitir
        if any(offset >= t_ini and fin <= t_fin for t_ini, t_fin in tramos_tomados):
            continue

        entidad = consultar_entidad_wikipedia(termino)
        if entidad:
            tramos_tomados.append((offset, fin))
            hallazgos.append({
                "category": entidad["category"],
                "text": termino,
                "message": f"{entidad['category']}: {entidad['definition']}",
                "suggestions": [f"*{termino}*"] if entidad["category"] == "Título de videojuego" else [],
                "offset": offset,
                "length": length,
                "rule_id": "QA_GAMING_ENTITY",
                "source": entidad["source"],
                "lookup": entidad
            })

    return sorted(hallazgos, key=lambda x: x["offset"])