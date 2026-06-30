"""Test the sync_prices management command against a fixture bulk file."""
import json
import tempfile
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from cards.models import Card, Tag


class SyncPricesTests(TestCase):
    def _write_bulk(self, objects):
        fd = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(objects, fd)
        fd.close()
        self.addCleanup(lambda: Path(fd.name).unlink(missing_ok=True))
        return fd.name

    def test_updates_price_without_wiping_tags_or_vault(self):
        tag = Tag.objects.create(name="ramp")
        card = Card.objects.create(
            name="Sol Ring", price_usd=Decimal("1.00"), in_vault=True
        )
        card.tags.add(tag)

        bulk = self._write_bulk([
            {
                "name": "Sol Ring", "set": "ltc", "set_name": "Commander LTR",
                "type_line": "Artifact", "rarity": "uncommon", "cmc": 1,
                "prices": {"usd": "3.50", "usd_foil": "8.00"},
                "scryfall_uri": "https://scryfall.com/x", "id": "abc",
                "oracle_id": "o1", "colors": [], "color_identity": [],
            },
            # Malformed/irrelevant object must not break the run.
            {"name": "Some Other Card", "prices": None},
        ])

        call_command("sync_prices", file=bulk, no_download=True)

        card.refresh_from_db()
        self.assertEqual(card.price_usd, Decimal("3.50"))
        self.assertEqual(card.price_usd_foil, Decimal("8.00"))
        self.assertEqual(card.primary_type, "Artifact")
        # Preserved:
        self.assertTrue(card.in_vault)
        self.assertEqual(list(card.tags.values_list("name", flat=True)), ["ramp"])

    def test_no_local_cards_is_noop(self):
        bulk = self._write_bulk([{"name": "Whatever", "prices": {"usd": "1.00"}}])
        # Should not raise even with no rows to update.
        call_command("sync_prices", file=bulk, no_download=True)
