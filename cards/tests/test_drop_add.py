"""Tests for the drag-and-drop add prefill (?scryfall=<uuid> on the add page)."""
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from cards import scryfall
from cards.models import Card, Tag

# A syntactically valid Scryfall card UUID, as extracted from a dropped image URL.
VALID_UUID = "f295b713-1d6a-43fd-910d-fb35414bf58a"


def _scryfall_card(name, **over):
    """A minimal raw Scryfall card object for parsing tests."""
    data = {
        "name": name,
        "id": "id-" + name.lower().replace(" ", "-"),
        "set": "ltc",
        "set_name": "Commander Masters",
        "type_line": "Artifact",
        "rarity": "uncommon",
        "cmc": 1,
        "colors": [],
        "color_identity": [],
        "image_uris": {"normal": "https://img/" + name + ".png"},
        "scryfall_uri": "https://scryfall.com/x",
        "prices": {"usd": "2.50", "usd_foil": None},
    }
    data.update(over)
    return data


def _fields(name):
    """A parsed field dict (as extract_card_fields would return)."""
    return scryfall.extract_card_fields(_scryfall_card(name))


class DropPrefillTests(TestCase):
    url = reverse("cards:card_add")

    @mock.patch("cards.scryfall.lookup_by_id")
    def test_get_with_scryfall_param_prefills_card(self, m_lookup):
        m_lookup.return_value = _fields("Sol Ring")
        resp = self.client.get(self.url, {"scryfall": VALID_UUID})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="prefill-card"')
        self.assertContains(resp, "Sol Ring")
        m_lookup.assert_called_once_with(VALID_UUID)

    @mock.patch("cards.scryfall.lookup_by_id")
    def test_prefill_enriched_with_vault_state(self, m_lookup):
        cmdr = Card.objects.create(name="Atraxa", scryfall_id="sf-atraxa")
        card = Card.objects.create(name="Sol Ring", in_vault=True, notes="great ramp")
        card.tags.add(Tag.objects.create(name="ramp"))
        card.suggested_commanders.add(cmdr)
        m_lookup.return_value = _fields("Sol Ring")

        resp = self.client.get(self.url, {"scryfall": VALID_UUID})
        prefill = resp.context["prefill_card"]
        self.assertTrue(prefill["in_vault"])
        self.assertEqual(prefill["tags"], ["ramp"])
        self.assertEqual(
            prefill["commanders"], [{"name": "Atraxa", "scryfall_id": "sf-atraxa"}]
        )
        self.assertEqual(prefill["notes"], "great ramp")

    @mock.patch("cards.scryfall.lookup_by_id", return_value=None)
    def test_unknown_uuid_degrades_gracefully(self, _m):
        resp = self.client.get(self.url, {"scryfall": VALID_UUID})
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'id="prefill-card"')
        self.assertContains(resp, "could not be found")

    @mock.patch(
        "cards.scryfall.lookup_by_id", side_effect=scryfall.ScryfallError("boom")
    )
    def test_scryfall_error_degrades_gracefully(self, _m):
        resp = self.client.get(self.url, {"scryfall": VALID_UUID})
        self.assertEqual(resp.status_code, 200)
        # The normal add page still renders, with an error banner.
        self.assertContains(resp, 'id="card-search"')
        self.assertContains(resp, "Scryfall error")
        self.assertNotContains(resp, 'id="prefill-card"')

    @mock.patch("cards.scryfall.lookup_by_id")
    def test_malformed_id_skips_lookup(self, m_lookup):
        resp = self.client.get(self.url, {"scryfall": "not-a-uuid"})
        self.assertEqual(resp.status_code, 200)
        m_lookup.assert_not_called()
        self.assertNotContains(resp, 'id="prefill-card"')
        self.assertContains(resp, "didn&#x27;t look like a Scryfall card")

    def test_plain_get_has_no_prefill(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'id="prefill-card"')
        self.assertIsNone(resp.context.get("prefill_card"))
