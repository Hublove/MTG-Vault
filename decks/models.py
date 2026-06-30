"""Deck and DeckCard models plus deck-rendering business logic.

Decks are a separate space from the Vault: a ``DeckCard`` references a shared
``Card`` row but tracks deck-specific state (quantity, physical ownership for the
"need to buy" workflow, and a per-deck category for custom grouping).
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse

from cards.constants import OTHER_GROUP, TYPE_GROUP_ORDER, TYPE_LABELS
from cards.models import Card


class Deck(models.Model):
    """A deck the user is building/tracking."""

    class Format(models.TextChoices):
        COMMANDER = "commander", "Commander / EDH"
        STANDARD = "standard", "Standard"
        MODERN = "modern", "Modern"
        PIONEER = "pioneer", "Pioneer"
        PAUPER = "pauper", "Pauper"
        LEGACY = "legacy", "Legacy"
        OTHER = "other", "Other"

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    format = models.CharField(
        max_length=20, choices=Format.choices, default=Format.COMMANDER
    )
    # Manually designated; one of this deck's own cards.
    commander = models.ForeignKey(
        Card, null=True, blank=True, on_delete=models.SET_NULL, related_name="commands_decks"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("decks:detail", args=[self.pk])

    # --- Rendering helpers -------------------------------------------------

    def _entries(self):
        """All DeckCards with their Card prefetched, excluding the commander."""
        qs = self.entries.select_related("card").order_by("card__name")
        if self.commander_id:
            qs = qs.exclude(card_id=self.commander_id)
        return qs

    def grouped_by_type(self):
        """Return ordered ``[(label, [entries])]`` grouped by primary card type.

        Commander is excluded here (shown separately, pinned at the top).
        """
        buckets = {label: [] for _kw, label in TYPE_GROUP_ORDER}
        buckets[OTHER_GROUP] = []
        for entry in self._entries():
            label = TYPE_LABELS.get(entry.card.primary_type, OTHER_GROUP)
            buckets[label].append(entry)
        order = [label for _kw, label in TYPE_GROUP_ORDER] + [OTHER_GROUP]
        return [(label, buckets[label]) for label in order if buckets[label]]

    def grouped_by_category(self):
        """Return ordered ``[(category, [entries])]`` by per-deck category.

        Uncategorized entries are grouped last under "Uncategorized".
        """
        buckets = {}
        for entry in self._entries():
            key = entry.category.strip() or "Uncategorized"
            buckets.setdefault(key, []).append(entry)
        # Named categories alphabetically, "Uncategorized" always last.
        names = sorted(k for k in buckets if k != "Uncategorized")
        if "Uncategorized" in buckets:
            names.append("Uncategorized")
        return [(name, buckets[name]) for name in names]

    @property
    def commander_entry(self):
        if not self.commander_id:
            return None
        return self.entries.select_related("card").filter(card_id=self.commander_id).first()

    def as_text(self):
        """Render the deck as a plain "Qty Name" decklist for export/bulk-edit.

        Commander (if any) is listed first so a round-trip keeps it on top.
        """
        lines = []
        if self.commander_entry:
            ce = self.commander_entry
            lines.append(f"{ce.quantity} {ce.card.name}")
        for entry in self._entries():
            lines.append(f"{entry.quantity} {entry.card.name}")
        return "\n".join(lines)

    # --- Stats -------------------------------------------------------------

    def owned_summary(self):
        """Counts and the USD/CAD cost still required to finish the deck."""
        entries = self.entries.select_related("card")
        total = owned = 0
        need_usd = Decimal("0")
        for e in entries:
            total += e.quantity
            if e.is_owned:
                owned += e.quantity
            elif e.card.price_usd:
                need_usd += e.card.price_usd * e.quantity
        need_cad = round(float(need_usd) * settings.FX_RATE_USD_CAD, 2)
        return {
            "total": total,
            "owned": owned,
            "missing": total - owned,
            "need_usd": need_usd,
            "need_cad": need_cad,
        }


class DeckCard(models.Model):
    """A card slot within a deck: quantity, ownership, and grouping category."""

    deck = models.ForeignKey(Deck, on_delete=models.CASCADE, related_name="entries")
    card = models.ForeignKey(Card, on_delete=models.PROTECT, related_name="deck_entries")
    quantity = models.PositiveIntegerField(default=1)
    # Whether the user physically owns this card *for this deck* (buy-list use).
    is_owned = models.BooleanField(default=False)
    # Optional per-deck grouping label for "custom tagging mode".
    category = models.CharField(max_length=64, blank=True)

    class Meta:
        unique_together = ("deck", "card")
        ordering = ["card__name"]

    def __str__(self):
        return f"{self.quantity}x {self.card.name} in {self.deck}"
