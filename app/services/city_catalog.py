"""Local city catalog: large offline city/settlement lookup."""

from __future__ import annotations

import gzip
import re
import sqlite3
from shutil import copyfileobj
from pathlib import Path

from app.services.ru_admin1_display import ru_admin1_geo_filter_value, ru_admin1_label_for_catalog

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "geo" / "city_catalog.sqlite3"
_CATALOG_GZ_PATH = Path(__file__).resolve().parent.parent / "data" / "geo" / "city_catalog.sqlite3.gz"

# Former USSR for prioritization in ambiguous matches.
_POST_SOVIET_ISO2 = {
    "RU", "UA", "BY", "KZ", "UZ", "KG", "TJ", "TM", "AZ", "AM", "GE", "MD", "LT", "LV", "EE",
}

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")

# GeoNames в SQLite: name_lc часто латиница; кирилический префикс «улья» не матчит «ulyanovsk» без транслита.
_RU_TO_LATIN: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def _latin_from_cyrillic_query(q: str) -> str:
    """Транслит нижнего регистра: только кириллица и уже латинские буквы/цифры."""
    s = (q or "").strip().lower()
    if not s or not _CYRILLIC_RE.search(s):
        return ""
    parts: list[str] = []
    for ch in s:
        cl = ch.lower()
        if cl in _RU_TO_LATIN:
            parts.append(_RU_TO_LATIN[cl])
        elif "a" <= cl <= "z" or cl.isdigit() or ch in ".- ":
            parts.append(ch)
    return "".join(parts).strip()
# Буквы, типичные для укр./бел. написаний, но не для стандартного русского: не показывать для RU из каталога GeoNames.
_NON_STANDARD_RU_CYRILLIC = frozenset("іІїЇєЄґҐўЎ")


def _has_nonstandard_ru_cyrillic(s: str) -> bool:
    return any(ch in _NON_STANDARD_RU_CYRILLIC for ch in s)


# Только типичные русские буквы в топониме (без белорусских ў, сербских љ и т. п.).
_RU_TOPONYM_CHARS_RE = re.compile(r"^[А-Яа-яЁё\-\s]+$")


def _is_plain_russian_toponym(s: str) -> bool:
    t = (s or "").strip()
    return bool(t and _RU_TOPONYM_CHARS_RE.fullmatch(t))


def _normalize_name_for_match(s: str) -> str:
    return re.sub(r"[^а-яё0-9]+", "", (s or "").lower())


def _row_matches_city_query(row: sqlite3.Row, q: str, latin_q: str) -> bool:
    """Совпадение запроса с названием строки каталога (кириллица и транслит)."""
    if not q:
        return False
    nl = str(row["name_lc"] or "")
    al = str(row["asciiname_lc"] or "")
    als = str(row["aliases_lc"] or "")
    if nl.startswith(q) or q in nl or al.startswith(q) or q in al or q in als:
        return True
    if latin_q:
        lq = latin_q.lower()
        if al.startswith(lq) or lq in al or lq in nl or lq in als:
            return True
    return False


def _pick_ru_name(name: str, aliases: str, query: str = "") -> str:
    """Для РФ: отдаём русскую форму и приоритет точному совпадению с запросом пользователя."""
    alias_items = [a.strip() for a in (aliases or "").split(",") if a.strip()]
    primary = (name or "").strip()
    q_norm = _normalize_name_for_match(query)
    candidates = [primary, *alias_items]
    cyr_candidates = [c for c in candidates if c and _CYRILLIC_RE.search(c)]

    if q_norm and cyr_candidates:
        def _score(candidate: str) -> tuple[int, int, int, int, int]:
            cand_norm = _normalize_name_for_match(candidate)
            exact = int(cand_norm == q_norm)
            prefix = int(cand_norm.startswith(q_norm))
            contains = int(q_norm in cand_norm)
            clean_ru = int(not _has_nonstandard_ru_cyrillic(candidate))
            short_pref = -len(cand_norm)
            return (exact, prefix, contains, clean_ru, short_pref)

        matched = [
            c
            for c in cyr_candidates
            if _normalize_name_for_match(c).startswith(q_norm) or q_norm in _normalize_name_for_match(c)
        ]
        pool = matched if matched else list(cyr_candidates)
        lens = [len(_normalize_name_for_match(c)) for c in pool]
        max_ln = max(lens) if lens else 0
        # Короткий префикс: не брать усечённые исторические формы («Ульск»), если в том же GeoNames есть длинное совпадение.
        if len(q_norm) <= 3 and max_ln >= 8:
            pool = [c for c in pool if len(_normalize_name_for_match(c)) >= 6]
        plain = [
            c
            for c in pool
            if _is_plain_russian_toponym(c)
            and " " not in c
            and "'" not in c
            and "ʼ" not in c
        ]
        if plain:
            pool = plain
        if len(q_norm) <= 3 and len(pool) >= 2:
            # Длиннее обычно полное название; «Ульяновськ» и усечённые формы отсекаем по лишнему мягкому перед «ск».
            def _pick_short_query_name(candidates: list[str]) -> str:
                cands = sorted(
                    candidates,
                    key=lambda c: (-len(_normalize_name_for_match(c)), c),
                )
                for cand in cands:
                    cn = _normalize_name_for_match(cand)
                    # Украинизированные окончания (-овськ) и лишний мягкий в «…новськ».
                    if len(cn) >= 10 and re.search(r"нськ$|овськ$", cn):
                        continue
                    return cand
                return cands[0]

            return _pick_short_query_name(pool)

        best = max(pool, key=_score)
        sc_best = _score(best)
        if sc_best[0] == 1:
            return best
        if sc_best[1] or sc_best[2]:
            return best

    if primary and _CYRILLIC_RE.search(primary) and not _has_nonstandard_ru_cyrillic(primary):
        return primary
    for item in alias_items:
        if _CYRILLIC_RE.search(item) and not _has_nonstandard_ru_cyrillic(item):
            return item
    if primary and _CYRILLIC_RE.search(primary):
        return primary
    for item in alias_items:
        if _CYRILLIC_RE.search(item):
            return item
    return primary or name


def city_catalog_exists() -> bool:
    return _CATALOG_PATH.is_file()


def _ensure_catalog_ready() -> None:
    """
    Keep repository-friendly compressed catalog in git.
    On first access unpack city_catalog.sqlite3 from city_catalog.sqlite3.gz.
    """
    if _CATALOG_PATH.is_file():
        return
    if not _CATALOG_GZ_PATH.is_file():
        return
    _CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(_CATALOG_GZ_PATH, "rb") as src, _CATALOG_PATH.open("wb") as dst:
        copyfileobj(src, dst)


def _connect() -> sqlite3.Connection | None:
    _ensure_catalog_ready()
    if not city_catalog_exists():
        return None
    conn = sqlite3.connect(str(_CATALOG_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def list_city_catalog_regions(country_iso2: str | None) -> list[str]:
    """Список областей (admin1) из локального каталога для страны."""
    cc = (country_iso2 or "").strip().upper()
    if len(cc) != 2:
        return []
    conn = _connect()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT TRIM(admin1_name) AS a
            FROM cities
            WHERE country_code = ?
              AND TRIM(COALESCE(admin1_name, '')) != ''
            ORDER BY a COLLATE NOCASE
            LIMIT 500
            """,
            (cc,),
        ).fetchall()
    finally:
        conn.close()
    raw_labels: list[str] = []
    seen_geo: set[str] = set()
    for row in rows:
        s = str(row["a"] or "").strip()
        if not s or s in seen_geo:
            continue
        seen_geo.add(s)
        raw_labels.append(s)
    if cc == "RU":
        out_ru: list[str] = []
        seen_ru: set[str] = set()
        for geo in raw_labels:
            lab = ru_admin1_label_for_catalog(geo)
            if lab not in seen_ru:
                seen_ru.add(lab)
                out_ru.append(lab)
        return sorted(out_ru, key=lambda x: x.casefold())
    return sorted(raw_labels, key=lambda x: x.casefold())


def search_city_catalog(
    query: str,
    limit: int = 10,
    country_iso2: str | None = None,
    admin1_name: str | None = None,
) -> list[dict]:
    """Search local catalog with simple ranking and post-soviet boost."""
    q = (query or "").strip().lower()
    if len(q) < 1:
        return []
    query_is_cyrillic = bool(_CYRILLIC_RE.search(q))
    cc_filter = (country_iso2 or "").strip().upper()
    conn = _connect()
    if conn is None:
        return []
    try:
        # Prefix + contains on normalized names and aliases.
        like_any = f"%{q}%"
        like_prefix = f"{q}%"
        latin_q = _latin_from_cyrillic_query(q)
        latin_prefix = f"{latin_q}%" if latin_q else ""
        latin_any = f"%{latin_q}%" if latin_q else ""
        sql = """
            SELECT
                geonameid, name, name_lc, asciiname, country_code, admin1_name, population, lat, lon, aliases
            FROM cities
            WHERE (name_lc LIKE ? OR asciiname_lc LIKE ? OR aliases_lc LIKE ?
               OR name_lc LIKE ? OR asciiname_lc LIKE ? OR aliases_lc LIKE ?
            """
        params: list[str] = [
            like_prefix,
            like_prefix,
            like_prefix,
            like_any,
            like_any,
            like_any,
        ]
        if latin_q:
            sql += """
               OR name_lc LIKE ? OR asciiname_lc LIKE ? OR aliases_lc LIKE ?
               OR name_lc LIKE ? OR asciiname_lc LIKE ? OR aliases_lc LIKE ?
            """
            params.extend(
                [
                    latin_prefix,
                    latin_prefix,
                    latin_prefix,
                    latin_any,
                    latin_any,
                    latin_any,
                ]
            )
        sql += ")"
        if len(cc_filter) == 2:
            sql += " AND country_code = ?"
            params.append(cc_filter)
        adm_raw = (admin1_name or "").strip()
        adm_sql = ru_admin1_geo_filter_value(adm_raw) if len(cc_filter) == 2 and cc_filter == "RU" and adm_raw else adm_raw
        if adm_sql:
            sql += " AND admin1_name = ?"
            params.append(adm_sql)
        row_cap = 90 if adm_sql else 100
        sql += f"""
            ORDER BY population DESC
            LIMIT {row_cap}
            """
        rows = list(conn.execute(sql, tuple(params)).fetchall())
        # Крупнейшие города области могут не попасть в LIMIT текстового запроса: добираем топ по населению.
        if adm_sql and cc_filter == "RU" and q:
            top_sql = """
                SELECT
                    geonameid, name, name_lc, asciiname, asciiname_lc, country_code, admin1_name,
                    population, lat, lon, aliases, aliases_lc
                FROM cities
                WHERE country_code = ? AND admin1_name = ?
                ORDER BY population DESC
                LIMIT 45
            """
            top_rows = conn.execute(top_sql, (cc_filter, adm_sql)).fetchall()
            seen_gid = {int(r["geonameid"]) for r in rows}
            for tr in top_rows:
                gid = int(tr["geonameid"])
                if gid in seen_gid:
                    continue
                if _row_matches_city_query(tr, q, latin_q):
                    rows.append(tr)
                    seen_gid.add(gid)
    finally:
        conn.close()

    by_key: dict[tuple[str, str, str], sqlite3.Row] = {}
    for row in rows:
        key = (
            str(row["name_lc"] or "").strip(),
            str(row["admin1_name"] or "").strip(),
            str(row["country_code"] or "").upper(),
        )
        prev = by_key.get(key)
        if prev is None or int(row["population"] or 0) > int(prev["population"] or 0):
            by_key[key] = row

    region_filter = bool(adm_sql)
    ordered_rows = sorted(by_key.values(), key=lambda r: int(r["population"] or 0), reverse=True)

    def _row_to_item(row: sqlite3.Row) -> dict:
        name = str(row["name"] or "").strip()
        aliases_raw = str(row["aliases"] or "")
        country_code = str(row["country_code"] or "").upper()
        row_admin1 = str(row["admin1_name"] or "").strip()
        if country_code == "RU":
            ru_name = _pick_ru_name(name, aliases_raw, query=q)
            display = f"{ru_name}, Россия"
        else:
            display = f"{name}, {country_code}" if not row_admin1 else f"{name}, {row_admin1}, {country_code}"
        pop = int(row["population"] or 0)
        return {
            "display_name": display,
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "country_code": country_code,
            "geonameid": int(row["geonameid"]),
            "population": pop,
        }

    if region_filter:
        out_rf: list[dict] = []
        seen_rf: set[int] = set()
        for row in ordered_rows:
            gid = int(row["geonameid"])
            if gid in seen_rf:
                continue
            seen_rf.add(gid)
            out_rf.append(_row_to_item(row))
            if len(out_rf) >= limit:
                break
        return out_rf

    scored: list[tuple[tuple[int, int, int, int, int, int], dict]] = []
    for row in ordered_rows:
        name = str(row["name"] or "").strip()
        aliases_raw = str(row["aliases"] or "")
        country_code = str(row["country_code"] or "").upper()
        row_admin1 = str(row["admin1_name"] or "").strip()
        if country_code == "RU":
            ru_name = _pick_ru_name(name, aliases_raw, query=q)
            display = f"{ru_name}, Россия"
        else:
            display = f"{name}, {country_code}" if not row_admin1 else f"{name}, {row_admin1}, {country_code}"
        name_lc = name.lower()
        aliases_lc = aliases_raw.lower()
        prefix_match = int(name_lc.startswith(q) or aliases_lc.startswith(q))
        exact_match = int(name_lc == q or q in [a.strip() for a in aliases_lc.split(",") if a.strip()])
        ru_prefix_match = int(query_is_cyrillic and country_code == "RU" and str(display).lower().startswith(q))
        contains_match = int((q in name_lc) or (q in aliases_lc))
        post_soviet = int(country_code in _POST_SOVIET_ISO2)
        pop = int(row["population"] or 0)
        item = {
            "display_name": display,
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "country_code": country_code,
            "geonameid": int(row["geonameid"]),
            "population": pop,
        }
        scored.append(
            (
                (exact_match, ru_prefix_match, prefix_match, post_soviet, contains_match, pop),
                item,
            )
        )

    scored.sort(key=lambda x: x[0], reverse=True)
    out_nr: list[dict] = []
    seen_gid: set[int] = set()
    for _, item in scored:
        gid = int(item["geonameid"])
        if gid in seen_gid:
            continue
        seen_gid.add(gid)
        out_nr.append(item)
        if len(out_nr) >= limit:
            break
    return out_nr


def resolve_city_catalog(city: str) -> tuple[float, float] | None:
    """Resolve city by exact-ish match from local catalog."""
    q = (city or "").strip().lower()
    if not q:
        return None
    conn = _connect()
    if conn is None:
        return None
    try:
        row = conn.execute(
            """
            SELECT lat, lon
            FROM cities
            WHERE name_lc = ? OR asciiname_lc = ? OR aliases_lc LIKE ?
            ORDER BY population DESC
            LIMIT 1
            """,
            (q, q, f"%{q}%"),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return (float(row["lat"]), float(row["lon"]))
