"""Decklist parsing, importing, and bulk-edit reconciliation.

This is the app's "bulky" feature and is covered by tests. It handles the
messy reality of pasted decklists: optional quantities, set codes / collector
numbers, foil markers, and section headers from Moxfield / Archidekt / Arena /
MTGO exports.

Resolution order for each name: existing local Card -> Scryfall batch
(/cards/collection) -> per-name fuzzy fallback. Names that resolve but aren't in
the Vault get a Card row created with ``in_vault=False`` so deck imports never
leak into the Vault.
"""
import re
from collections import OrderedDict
from dataclasses import dataclass, field

from cards.models import Card
from cards import scryfall

# Lines that are section headers, not cards.
_HEADERS = {
    "deck", "commander", "commanders", "sideboard", "companion",
    "maybeboard", "tokens", "about", "main", "mainboard",
}

# Leading "<qty>" or "<qty>x" then the name.
_QTY_RE = re.compile(r"^(\d+)\s*[xX]?\s+(.*)$")
# Trailing foil/etched markers like "*F*".
_FOIL_RE = re.compile(r"\s*\*[A-Za-z]+\*\s*$")
# A set code in parens/brackets plus anything after it (collector number, etc.):
# "(LTC) 263", "[2X2] 117", "(C21)".
_SETCODE_RE = re.compile(r"\s*[\(\[][A-Za-z0-9]{2,6}[\)\]].*$")
# MTGO sideboard prefix.
_SB_RE = re.compile(r"^SB:\s*", re.IGNORECASE)


@dataclass
class ImportReport:
    """Outcome of an import/reconcile for user-facing reporting."""

    imported: int = 0
    created_cards: int = 0
    removed: int = 0
    failures: list = field(default_factory=list)  # list[(name, reason)]
    # Names resolved via fuzzy matching: list[(requested, matched)]. Surfaced as
    # warnings so the user can catch a confidently-wrong typo correction
    # (e.g. "Sol Rng" -> "Oathsworn Giant").
    fuzzy_matches: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.failures and not self.fuzzy_matches


def clean_name(raw):
    """Strip set codes, collector numbers, and foil markers from a card name."""
    name = _FOIL_RE.sub("", raw)
    name = _SETCODE_RE.sub("", name)
    return name.strip()


def parse_decklist(text):
    """Parse pasted text into a list of ``(quantity, name)`` tuples.

    Blank lines, comments (``//`` / ``#``), and section headers are skipped.
    Lines without a leading quantity default to 1.
    """
    parsed = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        line = _SB_RE.sub("", line)
        # Pure section header (e.g. "Deck", "Commander:")?
        if line.rstrip(":").strip().lower() in _HEADERS:
            continue

        match = _QTY_RE.match(line)
        if match:
            qty = int(match.group(1))
            name = clean_name(match.group(2))
        else:
            qty = 1
            name = clean_name(line)
        if name:
            parsed.append((qty, name))
    return parsed


def _aggregate(parsed):
    """Collapse duplicate names, summing quantities. Returns name->(qty, display)."""
    agg = OrderedDict()
    for qty, name in parsed:
        key = name.lower()
        if key in agg:
            q, display = agg[key]
            agg[key] = (q + qty, display)
        else:
            agg[key] = (qty, name)
    return agg


def resolve_cards(names):
    """Resolve display names to Card rows.

    Returns ``(resolved, failures, created, fuzzy_matches)``. ``resolved`` maps
    lowercased name -> Card; ``failures`` is a list of ``(name, reason)``;
    ``fuzzy_matches`` is a list of ``(requested, matched_name)`` for names that
    only resolved via the typo-tolerant fuzzy fallback. Creates missing Card
    rows (``in_vault=False``) for anything Scryfall can match.
    """
    resolved = {}
    failures = []
    fuzzy_matches = []
    created = 0

    # 1) Local matches first (no network).
    pending = []
    for name in names:
        existing = Card.objects.filter(name__iexact=name).first()
        if existing:
            resolved[name.lower()] = existing
        else:
            pending.append(name)

    # 2) Batch the rest through /cards/collection.
    if pending:
        found, not_found = scryfall.lookup_collection(pending)
        for name in pending:
            fields = found.get(name.lower())
            if fields:
                card, was_created = Card.objects.upsert_from_payload(fields)
                created += int(was_created)
                resolved[name.lower()] = card

        # 3) Fuzzy fallback for the exact misses (typos).
        for name in not_found:
            try:
                fields, reason = scryfall.lookup_fuzzy(name)
            except scryfall.ScryfallError:
                fields, reason = None, "error"
            if fields:
                card, was_created = Card.objects.upsert_from_payload(fields)
                created += int(was_created)
                resolved[name.lower()] = card
                # Flag substitutions where the matched name differs from input.
                if fields["name"].lower() != name.lower():
                    fuzzy_matches.append((name, fields["name"]))
            else:
                failures.append((name, reason or "not_found"))

    return resolved, failures, created, fuzzy_matches


def _apply(deck, parsed, *, replace):
    """Shared core for import and reconcile.

    ``replace=True`` makes the deck match the parsed list exactly (removing
    absent cards) while preserving ``is_owned``/``category`` on survivors.
    ``replace=False`` adds/updates only.
    """
    from .models import DeckCard

    agg = _aggregate(parsed)
    resolved, failures, created, fuzzy_matches = resolve_cards(
        [display for _q, display in agg.values()]
    )

    report = ImportReport(
        created_cards=created, failures=failures, fuzzy_matches=fuzzy_matches
    )
    kept_card_ids = set()

    for key, (qty, display) in agg.items():
        card = resolved.get(key)
        if card is None:
            continue  # already recorded as a failure
        entry, _ = DeckCard.objects.update_or_create(
            deck=deck, card=card, defaults={"quantity": qty}
        )
        # update_or_create leaves is_owned/category untouched on existing rows.
        kept_card_ids.add(card.id)
        report.imported += 1

    if replace:
        stale = deck.entries.exclude(card_id__in=kept_card_ids)
        report.removed = stale.count()
        stale.delete()
        # Drop a commander that no longer exists in the deck.
        if deck.commander_id and deck.commander_id not in kept_card_ids:
            deck.commander = None
            deck.save(update_fields=["commander"])

    return report


def import_to_deck(deck, text):
    """Import a pasted decklist into ``deck`` (adds/updates, no removals)."""
    return _apply(deck, parse_decklist(text), replace=False)


def reconcile_deck(deck, text):
    """Replace the deck's contents from edited text, preserving owned/category."""
    return _apply(deck, parse_decklist(text), replace=True)
