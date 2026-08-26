"""Tests for double-faced card parsing (front/back art + layout)."""
from django.test import TestCase

from cards import scryfall


def _dfc_payload():
    """A transform card: no top-level image_uris, images live per-face."""
    return {
        "name": "Delver of Secrets // Insectile Aberration",
        "id": "dfc-1",
        "layout": "transform",
        "cmc": 1,
        "colors": ["U"],
        "color_identity": ["U"],
        "prices": {"usd": "0.20", "usd_foil": None},
        "card_faces": [
            {
                "name": "Delver of Secrets",
                "type_line": "Creature — Human Wizard",
                "image_uris": {"normal": "https://img/delver-front.png"},
            },
            {
                "name": "Insectile Aberration",
                "type_line": "Creature — Human Insect",
                "image_uris": {"normal": "https://img/delver-back.png"},
            },
        ],
    }


class DoubleFacedParsingTests(TestCase):
    def test_dfc_captures_both_faces_and_layout(self):
        fields = scryfall.extract_card_fields(_dfc_payload())
        self.assertEqual(fields["image_uri"], "https://img/delver-front.png")
        self.assertEqual(fields["image_uri_back"], "https://img/delver-back.png")
        self.assertEqual(fields["layout"], "transform")

    def test_single_faced_has_no_back(self):
        payload = {
            "name": "Sol Ring",
            "id": "sr",
            "layout": "normal",
            "cmc": 1,
            "colors": [],
            "color_identity": [],
            "image_uris": {"normal": "https://img/sol-ring.png"},
            "prices": {"usd": "2.00", "usd_foil": None},
        }
        fields = scryfall.extract_card_fields(payload)
        self.assertEqual(fields["image_uri"], "https://img/sol-ring.png")
        self.assertEqual(fields["image_uri_back"], "")
        self.assertEqual(fields["layout"], "normal")

    def test_shared_image_layout_has_no_distinct_back(self):
        # Split/adventure cards expose one top-level image for both faces, so
        # there is nothing to flip to.
        payload = {
            "name": "Fire // Ice",
            "id": "fi",
            "layout": "split",
            "cmc": 2,
            "colors": ["U", "R"],
            "color_identity": ["U", "R"],
            "image_uris": {"normal": "https://img/fire-ice.png"},
            "card_faces": [
                {"name": "Fire", "type_line": "Instant"},
                {"name": "Ice", "type_line": "Instant"},
            ],
            "prices": {"usd": "1.00", "usd_foil": None},
        }
        fields = scryfall.extract_card_fields(payload)
        self.assertEqual(fields["image_uri_back"], "")

    def test_is_double_faced_property_reflects_back_image(self):
        from cards.models import Card

        dfc = Card(name="A", image_uri="f", image_uri_back="b")
        single = Card(name="B", image_uri="f")
        self.assertTrue(dfc.is_double_faced)
        self.assertFalse(single.is_double_faced)
