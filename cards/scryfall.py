"""Thin Scryfall API client + payload parsing.

This module performs HTTP and maps raw Scryfall card JSON into the flat dict of
fields our ``Card`` model stores. It deliberately imports nothing from
``models`` so the model layer can depend on it without a cycle.

Scryfall etiquette honored here:
- A descriptive ``User-Agent`` and explicit ``Accept`` header on every request.
- ~100ms throttle between requests.
- Bulk price work uses the downloadable bulk file, not the per-card API.
"""
import time
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings

API_BASE = "https://api.scryfall.com"
_REQUEST_INTERVAL = 0.1  # seconds; Scryfall asks for 50-100ms between requests.
_last_request_at = 0.0


class ScryfallError(Exception):
    """Raised when Scryfall returns an error or unexpected response."""


def _headers():
    return {
        "User-Agent": settings.SCRYFALL_USER_AGENT,
        "Accept": "application/json",
    }


def _throttle():
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < _REQUEST_INTERVAL:
        time.sleep(_REQUEST_INTERVAL - elapsed)
    _last_request_at = time.monotonic()


def _get(path, **params):
    _throttle()
    resp = requests.get(f"{API_BASE}{path}", params=params, headers=_headers(), timeout=20)
    return resp


def _post(path, json):
    _throttle()
    resp = requests.post(f"{API_BASE}{path}", json=json, headers=_headers(), timeout=30)
    return resp


# --- Payload parsing -------------------------------------------------------

def _to_decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def _image_uri(payload):
    """Front-face normal image, handling double-faced cards."""
    images = payload.get("image_uris")
    if images:
        return images.get("normal") or images.get("large") or ""
    faces = payload.get("card_faces") or []
    if faces and faces[0].get("image_uris"):
        face_images = faces[0]["image_uris"]
        return face_images.get("normal") or face_images.get("large") or ""
    return ""


def _image_uri_back(payload):
    """Back-face normal image for double-faced cards, else "".

    Only true double-faced layouts (transform, modal_dfc, …) carry per-face
    images under ``card_faces[1]``. Cards with a single top-level ``image_uris``
    — including split/adventure cards whose faces share one image — have no
    distinct back face and return "".
    """
    if payload.get("image_uris"):
        return ""
    faces = payload.get("card_faces") or []
    if len(faces) > 1 and faces[1].get("image_uris"):
        face_images = faces[1]["image_uris"]
        return face_images.get("normal") or face_images.get("large") or ""
    return ""


def extract_card_fields(payload):
    """Map a raw Scryfall card object into our Card field dict.

    Imports nothing from the ORM; the manager applies these to a row.
    """
    from .constants import primary_type_for  # local import avoids any cycle

    prices = payload.get("prices") or {}
    type_line = payload.get("type_line", "") or ""
    return {
        "name": payload["name"],
        "oracle_id": payload.get("oracle_id", "") or "",
        "scryfall_id": payload.get("id", "") or "",
        "set_code": (payload.get("set") or "").upper(),
        "set_name": payload.get("set_name", "") or "",
        "collector_number": payload.get("collector_number", "") or "",
        "type_line": type_line,
        "primary_type": primary_type_for(type_line),
        "colors": "".join(payload.get("colors") or []),
        "color_identity": "".join(payload.get("color_identity") or []),
        "rarity": payload.get("rarity", "") or "",
        "mana_value": payload.get("cmc", 0) or 0,
        "image_uri": _image_uri(payload),
        "image_uri_back": _image_uri_back(payload),
        "layout": payload.get("layout", "") or "",
        "scryfall_uri": payload.get("scryfall_uri", "") or "",
        "price_usd": _to_decimal(prices.get("usd")),
        "price_usd_foil": _to_decimal(prices.get("usd_foil")),
    }


# --- Live lookups ----------------------------------------------------------

def lookup_exact(name):
    """Exact name lookup. Returns a parsed field dict or None if not found."""
    resp = _get("/cards/named", exact=name)
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise ScryfallError(f"Scryfall {resp.status_code} for '{name}'")
    return extract_card_fields(resp.json())


def lookup_fuzzy(name):
    """Fuzzy name lookup (typo tolerant).

    Returns (fields, None) on a unique match, (None, reason) otherwise where
    reason is "not_found" or "ambiguous".
    """
    resp = _get("/cards/named", fuzzy=name)
    if resp.status_code == 200:
        return extract_card_fields(resp.json()), None
    if resp.status_code == 404:
        # Scryfall returns 404 for both "no match" and "too ambiguous"; the
        # details string distinguishes them.
        details = (resp.json() or {}).get("details", "").lower()
        reason = "ambiguous" if "didn't match" not in details and "too many" in details else "not_found"
        return None, reason
    raise ScryfallError(f"Scryfall {resp.status_code} for fuzzy '{name}'")


def lookup_collection(names):
    """Resolve many names at once via /cards/collection (batched <=75).

    Returns ``(found, not_found)`` where ``found`` is a dict mapping the
    requested name (lowercased) to a parsed field dict, and ``not_found`` is the
    list of requested names Scryfall couldn't match exactly.
    """
    found = {}
    not_found = []
    unique = list(dict.fromkeys(names))  # de-dupe, preserve order
    for i in range(0, len(unique), 75):
        batch = unique[i:i + 75]
        identifiers = [{"name": n} for n in batch]
        resp = _post("/cards/collection", json={"identifiers": identifiers})
        if resp.status_code != 200:
            raise ScryfallError(f"Scryfall collection error {resp.status_code}")
        data = resp.json()
        for obj in data.get("data", []):
            fields = extract_card_fields(obj)
            found[fields["name"].lower()] = fields
        for miss in data.get("not_found", []):
            not_found.append(miss.get("name", ""))
    return found, not_found


def search_cards(query, commanders=False):
    """Full-text search via /cards/search, one result per unique card name.

    Returns ``(results, truncated)`` where ``results`` is a list of parsed field
    dicts (first page only, Scryfall returns <=175) and ``truncated`` is True
    when Scryfall reports more total matches than this first page contains.
    A 404 ("no cards found") yields an empty, non-truncated result.

    When ``commanders`` is true, restrict to legal commanders via ``is:commander``.
    """
    q = f"{query} is:commander" if commanders else query
    resp = _get("/cards/search", q=q, unique="cards")
    if resp.status_code == 404:
        return [], False
    if resp.status_code != 200:
        raise ScryfallError(f"Scryfall search error {resp.status_code} for '{query}'")
    data = resp.json()
    results = [extract_card_fields(obj) for obj in data.get("data", [])]
    truncated = bool(data.get("has_more")) or data.get("total_cards", 0) > len(results)
    return results, truncated


def lookup_by_id(scryfall_id):
    """Fetch one card by its Scryfall id. Returns a parsed field dict or None."""
    resp = _get(f"/cards/{scryfall_id}")
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise ScryfallError(f"Scryfall {resp.status_code} for id '{scryfall_id}'")
    return extract_card_fields(resp.json())


def extract_gallery_fields(payload):
    """``extract_card_fields`` plus the fields the Full Art gallery displays.

    These live only on the API payload (the Card model stores neither), so the
    gallery reads them straight from Scryfall. ``is_double_faced`` is a model
    property, so it's precomputed here — the gallery feeds plain dicts to
    ``_card_art.html``, which looks it up like any other attribute.
    """
    fields = extract_card_fields(payload)
    fields["released_at"] = payload.get("released_at", "") or ""
    fields["edhrec_rank"] = payload.get("edhrec_rank")  # int, or None if unranked
    fields["is_double_faced"] = bool(fields["image_uri_back"])
    return fields


def search_full_art(name="", set_code="", order="released", direction="desc", page=1,
                    exclude_lands=False, exclude_unpriced=False):
    """Full-art printings via /cards/search, one result per printing.

    Unlike ``search_cards`` this uses ``unique="prints"`` — the gallery is about
    printings, so every full-art version of a card is its own tile.

    ``exclude_lands`` appends ``-t:land``, which drops anything with the Land
    type — full-art basics (the bulk of the gallery), but also nonbasic lands
    and the land backs of dual-faced cards. ``exclude_unpriced`` appends
    ``usd>0``, dropping printings Scryfall has no USD price for (unreleased sets
    especially). A foil-only printing still matches on its ``usd_foil`` price
    even though ``price_usd`` is None, so callers displaying a price should fall
    back to the foil one.

    Returns ``(results, total_cards, has_more)``. A 404 ("no cards found") is the
    normal empty result, e.g. a name with no full-art printing.
    """
    parts = ["is:full"]
    if exclude_lands:
        parts.append("-t:land")
    if exclude_unpriced:
        parts.append("usd>0")
    if set_code:
        parts.append(f"e:{set_code}")
    if name:
        # Strip embedded quotes so a name can't break out of the quoted phrase
        # and inject extra Scryfall query operators.
        parts.append('"%s"' % name.replace('"', ""))
    resp = _get("/cards/search", q=" ".join(parts), unique="prints",
                order=order, dir=direction, page=page)
    if resp.status_code == 404:
        return [], 0, False
    if resp.status_code != 200:
        raise ScryfallError(f"Scryfall search error {resp.status_code}")
    data = resp.json()
    results = [extract_gallery_fields(obj) for obj in data.get("data", [])]
    return results, data.get("total_cards", 0), bool(data.get("has_more"))


def list_sets():
    """All non-digital Scryfall sets as ``(code, name)`` pairs, newest first.

    Backs the gallery's set filter. Digital-only sets are excluded — they have no
    physical full-art printings worth browsing.
    """
    resp = _get("/sets")
    if resp.status_code != 200:
        raise ScryfallError(f"Scryfall sets error {resp.status_code}")
    sets = [s for s in resp.json().get("data", []) if not s.get("digital")]
    sets.sort(key=lambda s: s.get("released_at") or "", reverse=True)
    return [(s["code"], s["name"]) for s in sets]


# --- Bulk data -------------------------------------------------------------

def bulk_oracle_download_uri():
    """Resolve the current 'Oracle Cards' bulk-data download URL."""
    resp = _get("/bulk-data")
    if resp.status_code != 200:
        raise ScryfallError(f"Scryfall bulk-data index error {resp.status_code}")
    for entry in resp.json().get("data", []):
        if entry.get("type") == "oracle_cards":
            return entry["download_uri"]
    raise ScryfallError("oracle_cards bulk entry not found")


def download_bulk_to(path):
    """Stream the Oracle Cards bulk file to ``path``. Returns the path."""
    uri = bulk_oracle_download_uri()
    _throttle()
    with requests.get(uri, headers=_headers(), stream=True, timeout=120) as resp:
        if resp.status_code != 200:
            raise ScryfallError(f"Bulk download failed {resp.status_code}")
        with open(path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    return path


def iter_bulk_cards(path):
    """Yield raw card objects from a downloaded bulk JSON file (streamed).

    The bulk file is a single top-level JSON array; ``ijson`` streams it so we
    never hold the whole ~100MB document in memory.
    """
    import ijson

    with open(path, "rb") as fh:
        yield from ijson.items(fh, "item")
