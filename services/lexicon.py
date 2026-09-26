"""Clasificacion morfologica: que palabras son ajenas al espanol.

Este modulo NO consulta red y NO inventa texto. Solo decide, con reglas
explicitas y auditables, si una palabra desconocida se comporta como voz
castellana o como extranjerismo/tecnicismo.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# 1. Zonas del texto que nunca deben auditarse (codigo, URLs, siglas, rutas)
# ---------------------------------------------------------------------------

_ZONAS = re.compile(
    r"""
      https?://\S+                              # URLs
    | www\.\S+
    | [\w.+-]+@[\w-]+\.[\w.]{2,}                # correos
    | `[^`]+`                                   # codigo entre acentos graves
    | "[^"\n]{1,40}\.(?:py|js|json|html|css|md|csv|sql|ya?ml|txt|log)"
    | <[^>\n]{1,60}>                            # etiquetas / placeholders
    | \b[\w.-]+\.(?:py|js|json|html|css|md|csv|sql|ya?ml|txt|log)\b
    | \b[A-Za-z][A-Za-z0-9]*(?:[_-][A-Za-z0-9]+)+\b   # snake_case, kebab-case
    | \b[a-z]+(?:[A-Z][a-z0-9]+)+\b             # camelCase
    | \b[A-Z]{2,}[0-9]*\b                       # siglas: API, HTTP, JSON, SQL
    | \bv?\d+(?:\.\d+)+\b                       # versiones: 3.1.2, v2.0
    | \b\d+\s?(?:px|ms|kb|mb|gb|tb|fps|hz)\b    # unidades tecnicas
    """,
    re.VERBOSE,
)


def zonas_protegidas(texto: str) -> list[tuple[int, int]]:
    """Devuelve los tramos (inicio, fin) que el auditor debe ignorar."""
    return [(m.start(), m.end()) for m in _ZONAS.finditer(texto)]


def esta_protegido(offset: int, length: int, zonas: list[tuple[int, int]]) -> bool:
    fin = offset + length
    return any(offset < z_fin and fin > z_ini for z_ini, z_fin in zonas)


# ---------------------------------------------------------------------------
# 2. Senales morfologicas
# ---------------------------------------------------------------------------

# Consonantes admitidas como final de palabra patrimonial espanola.
_FINALES_ES = set("dlnrszjx")

# Palabras espanolas que dispararian falsos positivos por sus reglas.
EXCEPCIONES_ES = {
    "rey", "ley", "hoy", "buey", "convoy", "soy", "voy", "doy", "estoy", "muy",
    "kilo", "kilometro", "kiwi", "koala", "kiosco", "whisky", "web", "club",
    "album", "curriculum", "referendum", "tandem", "modem", "chef", "bistec",
    "coche", "noche", "leche", "chico", "chica", "mucho", "ocho", "hecho",
    "derecho", "techo", "fecha", "ficha", "lucha", "escuchar", "chocolate",
}

# +puntos = mas probable que sea extranjerismo/tecnicismo.
_REGLAS_EXTRANJERAS: tuple[tuple[re.Pattern[str], int, str], ...] = (
    (re.compile(r"ings?$", re.I), 4, "terminacion -ing, propia del ingles"),
    (re.compile(r"(ware|script|board|byte|point|proof|less|ness|ship|room|line|time)$", re.I),
     4, "formante final ingles"),
    (re.compile(r"^(sc|sh|sk|sl|sm|sn|sp|st|sw)", re.I), 3,
     "grupo consonantico inicial ajeno al espanol (el espanol antepone e-)"),
    (re.compile(r"(ck|th|ph|wh|kn|gh|tch|dg|sh)", re.I), 3, "digrafo ajeno al espanol"),
    (re.compile(r"(oo|ee)", re.I), 1, "vocal doble atipica en espanol"),
    (re.compile(r"[kw]", re.I), 1, "uso de k o w, raro en voces patrimoniales"),
    (re.compile(r"y$", re.I), 2, "termina en -y"),
)

# -puntos = senal clara de palabra espanola.
_SENALES_ES: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"[\u00e1\u00e9\u00ed\u00f3\u00fa\u00fc\u00f1]", re.I), 5),
    (re.compile(r"(cion|sion|dad|tad|mente|miento|anza|eza|ismo|ista|ero|era|"
                r"ario|aria|able|ible|oso|osa|ura|encia|ancia)$", re.I), 4),
    (re.compile(r"(ar|er|ir|ado|ada|ando|iendo|amos|aron|aba|ido|ida)$", re.I), 2),
)

_CH_ES = re.compile(r"ch", re.I)


def sin_tildes(palabra: str) -> str:
    descompuesta = unicodedata.normalize("NFD", palabra)
    return "".join(c for c in descompuesta if unicodedata.category(c) != "Mn")


def puntaje_extranjero(palabra: str) -> tuple[int, list[str]]:
    """Puntua una palabra. Positivo alto => se comporta como voz extranjera."""
    limpia = palabra.strip(" .,;:()[]\"'\u00ab\u00bb\u00bf?\u00a1!")
    if not limpia or len(limpia) < 3:
        return 0, []
    if sin_tildes(limpia.lower()) in EXCEPCIONES_ES:
        return 0, []

    puntos = 0
    razones: list[str] = []

    for patron, peso, razon in _REGLAS_EXTRANJERAS:
        if patron.search(limpia):
            # 'ch' es digrafo espanol legitimo: no castigar sh/ck por su culpa.
            if razon.startswith("digrafo") and not re.search(
                r"(ck|th|ph|wh|kn|gh|tch|dg|sh)", _CH_ES.sub("", limpia), re.I
            ):
                continue
            puntos += peso
            razones.append(razon)

    final = limpia[-1].lower()
    if final.isalpha() and final not in "aeiou" and final not in _FINALES_ES:
        puntos += 3
        razones.append(f"termina en -{final}, final no admitido en espanol")

    for patron, peso in _SENALES_ES:
        if peso and patron.search(limpia):
            puntos -= peso

    return puntos, razones


def es_probable_extranjerismo(palabra: str, umbral: int = 3) -> tuple[bool, list[str]]:
    puntos, razones = puntaje_extranjero(palabra)
    return puntos >= umbral, razones
