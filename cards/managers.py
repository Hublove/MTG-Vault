"""Custom managers/querysets for cards.

Business logic for turning Scryfall payloads into local ``Card`` rows lives here
(fat models / skinny views), including the all-important rule that a price/data
refresh must never clobber user-applied tags or a card's Vault membership.
"""
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .constants import COLOR_ORDER


class CardQuerySet(models.QuerySet):
    def in_vault(self):
        """Cards the user has deliberately added to their Vault collection."""
        return self.filter(in_vault=True)

    def recently_added(self):
        """Vault cards, newest first (the Vault's default ordering)."""
        return self.in_vault().order_by("-added_to_vault_at", "-id")

    def commanders(self):
        """The commander list: cards that lead a deck OR are suggested-as-commander.

        ``commands_decks`` is the reverse of ``Deck.commander``; ``suggested_cards``
        is the reverse of ``Card.suggested_commanders``. A card qualifies (and gets
        a commander page) if either is non-empty.
        """
        return self.filter(
            Q(commands_decks__isnull=False) | Q(suggested_cards__isnull=False)
        ).distinct()

    def by_tags(self, slugs, match="any"):
        """Filter Vault cards by tag slugs.

        ``match="any"`` (default) returns cards having ANY of the tags (OR);
        ``match="all"`` returns cards having EVERY tag (AND). Empty selection
        leaves the queryset unchanged. Callers rely on the view's trailing
        ``.distinct()`` to de-duplicate OR matches.
        """
        slugs = [s for s in slugs if s]
        if not slugs:
            return self
        if match == "all":
            qs = self
            for slug in slugs:
                qs = qs.filter(tags__slug=slug)
            return qs
        return self.filter(tags__slug__in=slugs)

    def by_color_identity(self, colors, op):
        """Filter by color identity using MTG set-comparison operators.

        ``colors`` is an iterable of WUBRG letters (set S); ``op`` is one of
        ``eq``/``lte``/``lt``/``gte``/``gt``. Matching is per-letter against the
        concatenated ``color_identity`` string (order-independent; colorless is
        the empty string). Built from two primitives:
          - ``within``  : card has no color outside S (so C ⊆ S).
          - ``has_all`` : card has every color in S (so C ⊇ S).
        Subset operators (lte/lt) include colorless, since ∅ ⊆ any S.
        """
        selected = {c for c in colors if c in COLOR_ORDER}
        outside = [c for c in COLOR_ORDER if c not in selected]

        within = Q()
        for x in outside:
            within &= ~Q(color_identity__contains=x)
        has_all = Q()
        for x in selected:
            has_all &= Q(color_identity__contains=x)

        by_op = {
            "eq": within & has_all,
            "lte": within,
            "lt": within & ~has_all,
            "gte": has_all,
            "gt": has_all & ~within,
        }
        return self.filter(by_op.get(op, within))


class CardManager(models.Manager.from_queryset(CardQuerySet)):
    # Fields that come from Scryfall and may be refreshed. Deliberately EXCLUDES
    # ``in_vault`` / ``added_to_vault_at`` and tags so a sync never resets them.
    SCRYFALL_FIELDS = (
        "oracle_id",
        "scryfall_id",
        "set_code",
        "set_name",
        "collector_number",
        "type_line",
        "primary_type",
        "colors",
        "color_identity",
        "rarity",
        "mana_value",
        "image_uri",
        "scryfall_uri",
        "price_usd",
        "price_usd_foil",
    )

    def upsert_from_payload(self, payload, *, add_to_vault=False):
        """Create or update a Card from a parsed Scryfall payload dict.

        ``payload`` is the dict produced by ``scryfall.extract_card_fields``.
        Matching is by unique card name. Existing tags and Vault status are
        preserved; only Scryfall-sourced fields and the price timestamp change.
        Returns ``(card, created)``.
        """
        name = payload["name"]
        # Only set fields actually present so model defaults apply on create and
        # a partial payload never overwrites a column with NULL.
        defaults = {f: payload[f] for f in self.SCRYFALL_FIELDS if f in payload}
        defaults["last_price_update"] = timezone.now()

        card, created = self.update_or_create(name=name, defaults=defaults)
        if add_to_vault and not card.in_vault:
            card.add_to_vault()
        return card, created
