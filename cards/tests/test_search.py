"""Tests for the search-and-select card add flow."""
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from cards import scryfall
from cards.models import Card, Tag


class FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


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


class SearchCardsTests(TestCase):
    @mock.patch("cards.scryfall.requests.get")
    def test_parses_multiple_results_with_full_art(self, m_get):
        m_get.return_value = FakeResp(200, {
            "data": [_scryfall_card("Sol Ring"), _scryfall_card("Sol Talisman")],
            "has_more": False,
            "total_cards": 2,
        })
        results, truncated = scryfall.search_cards("sol")
        self.assertEqual([r["name"] for r in results], ["Sol Ring", "Sol Talisman"])
        self.assertIn("img/Sol Ring.png", results[0]["image_uri"])
        self.assertFalse(truncated)

    @mock.patch("cards.scryfall.requests.get")
    def test_404_returns_empty(self, m_get):
        m_get.return_value = FakeResp(404, {"details": "no cards found"})
        results, truncated = scryfall.search_cards("zzzznope")
        self.assertEqual(results, [])
        self.assertFalse(truncated)

    @mock.patch("cards.scryfall.requests.get")
    def test_truncation_flag_when_more_pages(self, m_get):
        m_get.return_value = FakeResp(200, {
            "data": [_scryfall_card("Bolt")],
            "has_more": True,
            "total_cards": 200,
        })
        _results, truncated = scryfall.search_cards("bolt")
        self.assertTrue(truncated)


class SearchAPIViewTests(TestCase):
    @mock.patch("cards.scryfall.search_cards")
    def test_returns_json_results(self, m_search):
        m_search.return_value = ([_fields("Sol Ring")], False)
        resp = self.client.get(reverse("cards:card_search"), {"q": "sol"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["results"][0]["name"], "Sol Ring")
        self.assertIn("image_uri", body["results"][0])

    def test_blank_query_returns_empty(self):
        resp = self.client.get(reverse("cards:card_search"), {"q": "  "})
        self.assertEqual(resp.json(), {"results": [], "truncated": False})

    @mock.patch("cards.scryfall.search_cards", side_effect=scryfall.ScryfallError("boom"))
    def test_scryfall_error_returns_502(self, _m):
        resp = self.client.get(reverse("cards:card_search"), {"q": "sol"})
        self.assertEqual(resp.status_code, 502)
        self.assertIn("error", resp.json())


class CardAddConfirmTests(TestCase):
    @mock.patch("cards.scryfall.lookup_by_id")
    def test_post_adds_selected_card_and_redirects(self, m_lookup):
        m_lookup.return_value = _fields("Sol Ring")
        resp = self.client.post(reverse("cards:card_add"), {"scryfall_id": "id-sol-ring"})
        card = Card.objects.get(name="Sol Ring")
        self.assertTrue(card.in_vault)
        self.assertRedirects(resp, card.get_absolute_url())

    def test_post_without_selection_shows_error(self):
        resp = self.client.post(reverse("cards:card_add"), {"scryfall_id": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Pick a card")

    @mock.patch("cards.scryfall.lookup_by_id", return_value=None)
    def test_post_unknown_id_shows_error(self, _m):
        resp = self.client.post(reverse("cards:card_add"), {"scryfall_id": "bogus"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "could not be found")
        self.assertFalse(Card.objects.exists())

    @mock.patch("cards.scryfall.lookup_by_id")
    def test_post_applies_and_creates_tags(self, m_lookup):
        m_lookup.return_value = _fields("Sol Ring")
        self.client.post(
            reverse("cards:card_add"),
            {"scryfall_id": "id-sol-ring", "tags": "ramp, removal"},
        )
        card = Card.objects.get(name="Sol Ring")
        self.assertEqual(
            set(card.tags.values_list("name", flat=True)), {"ramp", "removal"}
        )
        self.assertTrue(Tag.objects.filter(slug="removal").exists())

    @mock.patch("cards.scryfall.lookup_by_id")
    def test_post_reuses_existing_tag_no_duplicate(self, m_lookup):
        Tag.objects.create(name="ramp")
        m_lookup.return_value = _fields("Sol Ring")
        self.client.post(
            reverse("cards:card_add"),
            {"scryfall_id": "id-sol-ring", "tags": "Ramp"},  # different case → same slug
        )
        self.assertEqual(Tag.objects.filter(slug="ramp").count(), 1)
        card = Card.objects.get(name="Sol Ring")
        self.assertEqual(list(card.tags.values_list("name", flat=True)), ["ramp"])

    @mock.patch("cards.scryfall.lookup_by_id")
    def test_post_no_tags_still_adds(self, m_lookup):
        m_lookup.return_value = _fields("Sol Ring")
        self.client.post(reverse("cards:card_add"), {"scryfall_id": "id-sol-ring", "tags": ""})
        card = Card.objects.get(name="Sol Ring")
        self.assertEqual(card.tags.count(), 0)

    def test_no_selection_with_tags_creates_no_tag(self):
        # Aborted add (no card chosen) must not leave an orphan tag behind.
        resp = self.client.post(
            reverse("cards:card_add"), {"scryfall_id": "", "tags": "brandnewtag"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Card.objects.exists())
        self.assertFalse(Tag.objects.filter(slug="brandnewtag").exists())

    @mock.patch("cards.scryfall.lookup_by_id", return_value=None)
    def test_unknown_card_with_tags_creates_no_tag(self, _m):
        resp = self.client.post(
            reverse("cards:card_add"), {"scryfall_id": "bogus", "tags": "brandnewtag"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Card.objects.exists())
        self.assertFalse(Tag.objects.filter(slug="brandnewtag").exists())

    def test_add_page_wires_tag_combobox(self):
        Tag.objects.create(name="ramp")
        resp = self.client.get(reverse("cards:card_add"))
        # Widget hook + suggestion data are present for the JS combobox.
        self.assertContains(resp, 'id="tag-field"')
        self.assertContains(resp, 'id="all-tag-names"')
        self.assertContains(resp, "ramp")
