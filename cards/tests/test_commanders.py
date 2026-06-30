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


class CommanderSearchParamTests(TestCase):
    @mock.patch("cards.scryfall.search_cards")
    def test_commanders_flag_passed_through(self, m_search):
        m_search.return_value = ([_fields("Atraxa", "sf-atraxa")], False)
        self.client.get(reverse("cards:card_search"), {"q": "atraxa", "commanders": "1"})
        # The view must call search_cards with commanders=True.
        _args, kwargs = m_search.call_args
        self.assertTrue(kwargs.get("commanders"))
