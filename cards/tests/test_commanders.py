"""Tests for suggested commanders + per-card notes."""
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from cards.models import Card, Tag
from decks.models import Deck


def _fields(name, sid=None):
    """Minimal parsed Scryfall field dict (as extract_card_fields returns)."""
    return {
        "name": name,
        "scryfall_id": sid or ("id-" + name.lower().replace(" ", "-")),
        "type_line": "Legendary Creature — God",
        "primary_type": "Creature",
        "image_uri": "https://img/" + name + ".png",
        "image_uri_back": "",
        "set_code": "CMR",
        "set_name": "Commander Legends",
        "price_usd": Decimal("1.00"),
    }


class CommanderListManagerTests(TestCase):
    def test_includes_deck_commanders_and_suggested(self):
        atraxa = Card.objects.create(name="Atraxa", scryfall_id="sf-atraxa")
        edgar = Card.objects.create(name="Edgar", scryfall_id="sf-edgar")
        sol = Card.objects.create(name="Sol Ring", scryfall_id="sf-sol")
        # Atraxa leads a deck; Edgar is only a suggested commander for Sol Ring.
        Deck.objects.create(name="EDH", commander=atraxa)
        sol.suggested_commanders.add(edgar)

        commanders = set(Card.objects.commanders().values_list("name", flat=True))
        self.assertEqual(commanders, {"Atraxa", "Edgar"})
        self.assertNotIn("Sol Ring", commanders)  # Sol Ring is not a commander

    def test_deduped(self):
        atraxa = Card.objects.create(name="Atraxa", scryfall_id="sf-atraxa")
        Deck.objects.create(name="D1", commander=atraxa)
        Deck.objects.create(name="D2", commander=atraxa)
        c1 = Card.objects.create(name="C1")
        c1.suggested_commanders.add(atraxa)
        self.assertEqual(list(Card.objects.commanders().values_list("name", flat=True)), ["Atraxa"])


class AddWithCommandersAndNotesTests(TestCase):
    @mock.patch("cards.scryfall.lookup_by_id")
    def test_add_sets_commanders_and_notes_creating_missing(self, m_lookup):
        existing = Card.objects.create(name="Atraxa", scryfall_id="sf-atraxa")

        def lookup(sid):
            return {"sf-sol": _fields("Sol Ring", "sf-sol"),
                    "sf-edgar": _fields("Edgar", "sf-edgar")}.get(sid)

        m_lookup.side_effect = lookup
        resp = self.client.post(reverse("cards:card_add"), {
            "scryfall_id": "sf-sol",
            "notes": "great with proliferate",
            "commanders": ["sf-atraxa", "sf-edgar"],  # one existing, one new
        })
        card = Card.objects.get(name="Sol Ring")
        self.assertEqual(card.notes, "great with proliferate")
        self.assertEqual(
            set(card.suggested_commanders.values_list("name", flat=True)), {"Atraxa", "Edgar"}
        )
        # The new commander (Edgar) got created as a reference row.
        self.assertTrue(Card.objects.filter(scryfall_id="sf-edgar").exists())
        self.assertRedirects(resp, card.get_absolute_url())

    @mock.patch("cards.scryfall.lookup_by_id")
    def test_add_without_commanders_or_notes(self, m_lookup):
        m_lookup.return_value = _fields("Sol Ring", "sf-sol")
        self.client.post(reverse("cards:card_add"), {"scryfall_id": "sf-sol"})
        card = Card.objects.get(name="Sol Ring")
        self.assertEqual(card.notes, "")
        self.assertEqual(card.suggested_commanders.count(), 0)


class NotesUpdateTests(TestCase):
    def test_notes_update_view(self):
        card = Card.objects.create(name="Sol Ring", in_vault=True)
        self.client.post(reverse("cards:card_notes", args=[card.pk]), {"notes": "ramp"})
        card.refresh_from_db()
        self.assertEqual(card.notes, "ramp")


class CardCommandersUpdateTests(TestCase):
    @mock.patch("cards.scryfall.lookup_by_id")
    def test_set_replaces_and_creates(self, m_lookup):
        card = Card.objects.create(name="Sol Ring", in_vault=True)
        atraxa = Card.objects.create(name="Atraxa", scryfall_id="sf-atraxa")
        card.suggested_commanders.add(atraxa)
        m_lookup.return_value = _fields("Edgar", "sf-edgar")

        # Replace {Atraxa} with {Edgar} (new); Atraxa is created/known, Edgar fetched.
        self.client.post(
            reverse("cards:card_commanders", args=[card.pk]), {"commanders": ["sf-edgar"]}
        )
        self.assertEqual(
            list(card.suggested_commanders.values_list("name", flat=True)), ["Edgar"]
        )
        self.assertTrue(Card.objects.filter(scryfall_id="sf-edgar").exists())

    def test_empty_clears(self):
        card = Card.objects.create(name="Sol Ring", in_vault=True)
        atraxa = Card.objects.create(name="Atraxa", scryfall_id="sf-atraxa")
        card.suggested_commanders.add(atraxa)
        self.client.post(reverse("cards:card_commanders", args=[card.pk]), {"commanders": []})
        self.assertEqual(card.suggested_commanders.count(), 0)

    def test_detail_seeds_current_commanders(self):
        card = Card.objects.create(name="Sol Ring", in_vault=True)
        atraxa = Card.objects.create(name="Atraxa", scryfall_id="sf-atraxa")
        card.suggested_commanders.add(atraxa)
        resp = self.client.get(reverse("cards:card_detail", args=[card.pk]))
        self.assertContains(resp, 'id="cmd-initial"')
        self.assertContains(resp, "sf-atraxa")

    def test_detail_shows_commander_card_art(self):
        card = Card.objects.create(name="Sol Ring", in_vault=True)
        atraxa = Card.objects.create(
            name="Atraxa", scryfall_id="sf-atraxa",
            image_uri="https://img/atraxa.png",
        )
        card.suggested_commanders.add(atraxa)
        resp = self.client.get(reverse("cards:card_detail", args=[card.pk]))
        # The read-only section renders the commander's full card image.
        self.assertContains(resp, "https://img/atraxa.png")


class CommanderViewsTests(TestCase):
    def test_commander_detail_lists_suggested_cards(self):
        atraxa = Card.objects.create(name="Atraxa", scryfall_id="sf-atraxa")
        Deck.objects.create(name="EDH", commander=atraxa)
        sol = Card.objects.create(name="Sol Ring")
        sol.suggested_commanders.add(atraxa)

        resp = self.client.get(reverse("cards:commander_detail", args=[atraxa.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Sol Ring")

    def test_commander_list_shows_commanders(self):
        atraxa = Card.objects.create(name="Atraxa")
        Deck.objects.create(name="EDH", commander=atraxa)
        resp = self.client.get(reverse("cards:commander_list"))
        self.assertContains(resp, "Atraxa")


class CommanderSuggestDropTests(TestCase):
    """POST endpoint behind drag-and-dropping a card onto a commander page."""

    # Scryfall ids must be syntactically valid UUIDs for this endpoint.
    SOL_UUID = "f295b713-1d6a-43fd-910d-fb35414bf58a"
    ATRAXA_UUID = "0f8f1b32-52aa-4a5e-89e8-a10ea1093a34"

    def setUp(self):
        self.atraxa = Card.objects.create(name="Atraxa", scryfall_id=self.ATRAXA_UUID)
        Deck.objects.create(name="EDH", commander=self.atraxa)
        self.url = reverse("cards:commander_suggest", args=[self.atraxa.pk])

    def test_drop_existing_card_appends_and_redirects(self):
        sol = Card.objects.create(name="Sol Ring", scryfall_id=self.SOL_UUID, in_vault=True)
        resp = self.client.post(self.url, {"scryfall": self.SOL_UUID})
        self.assertRedirects(resp, reverse("cards:commander_detail", args=[self.atraxa.pk]))
        self.assertEqual(list(sol.suggested_commanders.values_list("name", flat=True)), ["Atraxa"])

    def test_drop_appends_without_replacing_other_commanders(self):
        edgar = Card.objects.create(name="Edgar", scryfall_id="sf-edgar")
        sol = Card.objects.create(name="Sol Ring", scryfall_id=self.SOL_UUID)
        sol.suggested_commanders.add(edgar)
        self.client.post(self.url, {"scryfall": self.SOL_UUID})
        self.assertEqual(
            set(sol.suggested_commanders.values_list("name", flat=True)), {"Atraxa", "Edgar"}
        )

    @mock.patch("cards.scryfall.lookup_by_id")
    def test_drop_unknown_card_fetches_reference_row(self, m_lookup):
        m_lookup.return_value = _fields("Sol Ring", self.SOL_UUID)
        self.client.post(self.url, {"scryfall": self.SOL_UUID})
        m_lookup.assert_called_once_with(self.SOL_UUID)
        sol = Card.objects.get(scryfall_id=self.SOL_UUID)
        self.assertIn(self.atraxa, sol.suggested_commanders.all())

    @mock.patch("cards.scryfall.lookup_by_id")
    def test_drop_unresolvable_card_degrades_with_message(self, m_lookup):
        m_lookup.return_value = None
        resp = self.client.post(self.url, {"scryfall": self.SOL_UUID}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "could not be found on Scryfall")
        self.assertEqual(self.atraxa.suggested_cards.count(), 0)

    def test_drop_malformed_id_degrades_with_message(self):
        resp = self.client.post(self.url, {"scryfall": "not-a-uuid"}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "didn&#x27;t look like a Scryfall card")
        self.assertEqual(self.atraxa.suggested_cards.count(), 0)

    def test_drop_commander_onto_itself_is_ignored(self):
        resp = self.client.post(self.url, {"scryfall": self.ATRAXA_UUID}, follow=True)
        self.assertContains(resp, "can&#x27;t be suggested for itself")
        self.assertEqual(self.atraxa.suggested_cards.count(), 0)

    def test_drop_twice_is_idempotent(self):
        sol = Card.objects.create(name="Sol Ring", scryfall_id=self.SOL_UUID)
        self.client.post(self.url, {"scryfall": self.SOL_UUID})
        self.client.post(self.url, {"scryfall": self.SOL_UUID})
        self.assertEqual(sol.suggested_commanders.count(), 1)
        self.assertEqual(self.atraxa.suggested_cards.count(), 1)

    def test_commander_page_renders_drop_form(self):
        resp = self.client.get(reverse("cards:commander_detail", args=[self.atraxa.pk]))
        self.assertContains(resp, 'id="drop-suggest-form"')
        self.assertContains(resp, self.url)


class CommanderSearchParamTests(TestCase):
    @mock.patch("cards.scryfall.search_cards")
    def test_commanders_flag_passed_through(self, m_search):
        m_search.return_value = ([_fields("Atraxa", "sf-atraxa")], False)
        self.client.get(reverse("cards:card_search"), {"q": "atraxa", "commanders": "1"})
        # The view must call search_cards with commanders=True.
        _args, kwargs = m_search.call_args
        self.assertTrue(kwargs.get("commanders"))
