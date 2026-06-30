"""Tests for card classification, pricing, and link helpers."""
from decimal import Decimal

from django.test import TestCase, override_settings

from cards.constants import OTHER_GROUP, primary_type_for
from cards.models import Card


class PrimaryTypeTests(TestCase):
    def test_multi_type_creature_wins(self):
        self.assertEqual(primary_type_for("Legendary Artifact Creature — God"), "Creature")

    def test_artifact_equipment(self):
        self.assertEqual(primary_type_for("Artifact — Equipment"), "Artifact")

    def test_land_is_last(self):
        # An "Artifact Land" should bucket as Artifact (higher priority), but a
        # plain land buckets as Land.
        self.assertEqual(primary_type_for("Basic Land — Forest"), "Land")
        self.assertEqual(primary_type_for("Artifact Land"), "Artifact")

    def test_double_faced_uses_front(self):
        self.assertEqual(
            primary_type_for("Legendary Creature — Human // Land"), "Creature"
        )

    def test_instant_and_sorcery(self):
        self.assertEqual(primary_type_for("Instant"), "Instant")
        self.assertEqual(primary_type_for("Sorcery — Arcane"), "Sorcery")

    def test_unknown_is_other(self):
        self.assertEqual(primary_type_for("Dungeon"), OTHER_GROUP)
        self.assertEqual(primary_type_for(""), OTHER_GROUP)


@override_settings(FX_RATE_USD_CAD=2.0)
class CardHelpersTests(TestCase):
    def test_price_cad_conversion(self):
        card = Card(name="Sol Ring", price_usd=Decimal("2.50"))
        self.assertEqual(card.price_cad, 5.0)

    def test_price_cad_none_when_no_usd(self):
        self.assertIsNone(Card(name="X").price_cad)

    def test_color_list_canonical_order(self):
        card = Card(name="Y", colors="GWU")
        self.assertEqual(card.color_list, ["W", "U", "G"])

    def test_external_links_include_stores(self):
        card = Card(name="Lightning Bolt", set_code="2X2")
        labels = {label: url for label, url in card.external_links}
        self.assertIn("401 Games", labels)
        self.assertIn("Lightning+Bolt", labels["401 Games"])
        self.assertIn("facetofacegames.com", labels["Face to Face"])

    def test_tagger_link_uses_lowercase_set_and_collector_number(self):
        card = Card(name="Fortune Teller's Talent", set_code="BLC", collector_number="14")
        tagger = dict(card.external_links)["Tagger"]
        self.assertEqual(tagger, "https://tagger.scryfall.com/card/blc/14")

    def test_tagger_link_falls_back_to_search_without_collector_number(self):
        card = Card(name="Sol Ring", set_code="LTC")  # no collector_number
        tagger = dict(card.external_links)["Tagger"]
        self.assertEqual(tagger, "https://tagger.scryfall.com/search?q=Sol+Ring")
