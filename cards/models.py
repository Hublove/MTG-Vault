"""Data models for cards, tags, and the Vault collection.

Design notes:
- A ``Card`` row holds Scryfall data for one *unique oracle card* (one row per
  name, not per printing). Rows are created on demand either when added to the
  Vault or when referenced by a deck import.
- The Vault and decks are two separate spaces that share this table. Vault
  membership is the explicit ``in_vault`` flag; deck references never set it.
"""
from urllib.parse import quote_plus

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from .constants import COLOR_ORDER, TYPE_LABELS, primary_type_for, random_tag_color
from .managers import CardManager


class TagManager(models.Manager):
    def get_or_create_from_csv(self, text):
        """Resolve comma-separated tag names to Tag rows, creating new ones.

        Each entry is trimmed; blanks are skipped. Matching/creation is by
        ``slug`` so "Green Ramp" and "green ramp" resolve to the same tag.
        Newly created tags get a random palette color. Returns the list of Tags
        (existing reused, new ones created).
        """
        tags = []
        for raw in (text or "").split(","):
            label = raw.strip()
            if not label:
                continue
            tag, _ = self.get_or_create(
                slug=slugify(label),
                defaults={"name": label, "color": random_tag_color()},
            )
            tags.append(tag)
        return tags


class Tag(models.Model):
    """A user-defined label applied to Vault cards (e.g. "green ramp")."""

    name = models.CharField(max_length=64, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)
    # Hex accent color for the tag chip (see cards.constants.TAG_PALETTE).
    color = models.CharField(max_length=7, blank=True, default="#64748b")

    objects = TagManager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f"{reverse('cards:vault')}?tag={self.slug}"


class Card(models.Model):
    """A unique MTG card plus its current Scryfall data and Vault status."""

    name = models.CharField(max_length=255, unique=True, db_index=True)

    # Scryfall identity / printing data (single representative printing).
    oracle_id = models.CharField(max_length=64, blank=True, db_index=True)
    scryfall_id = models.CharField(max_length=64, blank=True)
    set_code = models.CharField(max_length=16, blank=True, db_index=True)
    set_name = models.CharField(max_length=128, blank=True)
    # Printing collector number (may include letters/symbols, e.g. "123a", "14★").
    collector_number = models.CharField(max_length=16, blank=True)
    type_line = models.CharField(max_length=255, blank=True)
    # Derived single-bucket type for grouping/filtering (e.g. "Creature").
    primary_type = models.CharField(max_length=32, blank=True, db_index=True)

    # Colors stored as concatenated WUBRG codes, e.g. "WUB"; "" means colorless.
    colors = models.CharField(max_length=5, blank=True)
    color_identity = models.CharField(max_length=5, blank=True)
    rarity = models.CharField(max_length=16, blank=True, db_index=True)
    mana_value = models.FloatField(default=0)

    image_uri = models.URLField(max_length=500, blank=True)
    # Back-face art for double-faced cards (transform/modal_dfc); "" otherwise.
    image_uri_back = models.URLField(max_length=500, blank=True)
    # Scryfall layout, e.g. "normal", "transform", "modal_dfc", "split".
    layout = models.CharField(max_length=32, blank=True)
    scryfall_uri = models.URLField(max_length=500, blank=True)

    # Pricing. Scryfall gives USD only; CAD is computed via FX_RATE_USD_CAD.
    price_usd = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    price_usd_foil = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    last_price_update = models.DateTimeField(null=True, blank=True)

    # Vault membership (separate from any deck usage).
    in_vault = models.BooleanField(default=False, db_index=True)
    added_to_vault_at = models.DateTimeField(null=True, blank=True)

    # Freeform user notes (editable on the card page).
    notes = models.TextField(blank=True)

    tags = models.ManyToManyField(Tag, through="CardTag", related_name="cards", blank=True)

    # Commanders this card is "good for". Self-referential: the targets are the
    # commander cards; reverse ``suggested_cards`` = cards suggested for a commander.
    suggested_commanders = models.ManyToManyField(
        "self", symmetrical=False, related_name="suggested_cards", blank=True
    )

    objects = CardManager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("cards:card_detail", args=[self.pk])

    # --- Vault helpers -----------------------------------------------------

    def add_to_vault(self):
        """Mark this card as part of the Vault, stamping the add time once."""
        self.in_vault = True
        if self.added_to_vault_at is None:
            self.added_to_vault_at = timezone.now()
        self.save(update_fields=["in_vault", "added_to_vault_at"])

    def remove_from_vault(self):
        """Remove from the Vault without deleting the row (decks may use it)."""
        self.in_vault = False
        self.save(update_fields=["in_vault"])

    # --- Derived data ------------------------------------------------------

    @property
    def is_double_faced(self):
        """True when a distinct back-face image is available to flip to."""
        return bool(self.image_uri_back)

    @property
    def price_cad(self):
        """USD price converted to CAD using the configured FX rate."""
        if self.price_usd is None:
            return None
        return round(float(self.price_usd) * settings.FX_RATE_USD_CAD, 2)

    @property
    def color_list(self):
        """Colors in canonical WUBRG order as single-letter codes."""
        return [c for c in COLOR_ORDER if c in (self.colors or "")]

    @property
    def type_group_label(self):
        """Plural display label for this card's primary type (e.g. "Creatures")."""
        return TYPE_LABELS.get(self.primary_type, "Other")

    def sync_primary_type(self):
        """Recompute primary_type from the current type_line."""
        self.primary_type = primary_type_for(self.type_line)

    @property
    def external_links(self):
        """External marketplace/reference links for the detail page buttons.

        Returns an ordered list of ``(label, url)``. Scryfall Tagger keys cards
        by lowercase set code + collector number (e.g. .../card/blc/14); when we
        don't have both yet (un-refreshed row), fall back to Tagger search.
        """
        q = quote_plus(self.name)
        if self.set_code and self.collector_number:
            tagger = f"https://tagger.scryfall.com/card/{self.set_code.lower()}/{self.collector_number}"
        else:
            tagger = f"https://tagger.scryfall.com/search?q={q}"
        return [
            ("Scryfall", self.scryfall_uri or f"https://scryfall.com/search?q={q}"),
            ("Tagger", tagger),
            ("401 Games", f"https://store.401games.ca/pages/search-results?q={q}"),
            # F2F migrated to a Shopify storefront; the old /search/?keyword= URL
            # ignores the query and lands on an empty "Search for Search" page.
            # sort/filter param names captured from the live site's controls.
            ("Face to Face", f"https://facetofacegames.com/search?q={q}&sort_by=price_asc&filter__Availability=In+Stock"),
        ]


class CardTag(models.Model):
    """Through model linking Cards and Tags (per spec)."""

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="card_tags")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="tag_cards")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("card", "tag")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.card} · {self.tag}"
