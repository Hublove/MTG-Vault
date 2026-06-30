"""Tests for decklist parsing, import, and bulk-edit reconciliation."""
from decimal import Decimal
from unittest import mock

from django.test import TestCase

from cards.models import Card
from decks.importer import (
    clean_name,
    import_to_deck,
    parse_decklist,
    reconcile_deck,
)
from decks.models import Deck, DeckCard


def _fields(name, primary_type="Creature", price="1.00"):
    """Minimal Scryfall field dict (as extract_card_fields would produce)."""
    return {
        "name": name,
        "type_line": primary_type,
        "primary_type": primary_type,
        "price_usd": Decimal(price),
    }


class ParseDecklistTests(TestCase):
    def test_basic_quantity_and_name(self):
        self.assertEqual(parse_decklist("1 Sol Ring"), [(1, "Sol Ring")])

    def test_x_suffix_quantity(self):
        self.assertEqual(parse_decklist("4x Lightning Bolt"), [(4, "Lightning Bolt")])

    def test_no_quantity_defaults_to_one(self):
        self.assertEqual(parse_decklist("Sol Ring"), [(1, "Sol Ring")])

    def test_strips_set_code_and_collector_number(self):
        self.assertEqual(parse_decklist("1 Sol Ring (LTC) 263"), [(1, "Sol Ring")])
        self.assertEqual(parse_decklist("4 Lightning Bolt [2X2] 117"), [(4, "Lightning Bolt")])

    def test_strips_foil_marker(self):
        self.assertEqual(parse_decklist("1 Sol Ring (C21) 263 *F*"), [(1, "Sol Ring")])

    def test_skips_headers_comments_and_blanks(self):
        text = "Commander\n1 Atraxa\n\n// ramp\nDeck\n1 Sol Ring\nSideboard:\n"
        self.assertEqual(parse_decklist(text), [(1, "Atraxa"), (1, "Sol Ring")])

    def test_strips_mtgo_sideboard_prefix(self):
        self.assertEqual(parse_decklist("SB: 2 Negate"), [(2, "Negate")])

    def test_clean_name_helper(self):
        self.assertEqual(clean_name("Sol Ring (LTC) 263 *F*"), "Sol Ring")


@mock.patch("cards.scryfall.lookup_fuzzy")
@mock.patch("cards.scryfall.lookup_collection")
class ImportTests(TestCase):
    def test_import_creates_cards_not_in_vault(self, m_collection, m_fuzzy):
        m_collection.return_value = (
            {"sol ring": _fields("Sol Ring", "Artifact"),
             "llanowar elves": _fields("Llanowar Elves")},
            [],
        )
        deck = Deck.objects.create(name="Test")

        report = import_to_deck(deck, "1 Sol Ring\n1 Llanowar Elves")

        self.assertEqual(report.imported, 2)
        self.assertEqual(report.created_cards, 2)
        self.assertEqual(deck.entries.count(), 2)
        # Deck-imported cards must NOT enter the Vault.
        self.assertFalse(Card.objects.get(name="Sol Ring").in_vault)

    def test_existing_local_card_not_relooked_up(self, m_collection, m_fuzzy):
        Card.objects.create(name="Sol Ring", price_usd=Decimal("2.00"))
        m_collection.return_value = ({}, [])  # nothing pending should be sent
        deck = Deck.objects.create(name="Test")

        report = import_to_deck(deck, "1 Sol Ring")

        self.assertEqual(report.imported, 1)
        m_collection.assert_not_called()

    def test_unmatched_line_reported_via_fuzzy_failure(self, m_collection, m_fuzzy):
        m_collection.return_value = ({}, ["Sol Rng"])
        m_fuzzy.return_value = (None, "not_found")
        deck = Deck.objects.create(name="Test")

        report = import_to_deck(deck, "1 Sol Rng")

        self.assertEqual(report.imported, 0)
        self.assertEqual(report.failures, [("Sol Rng", "not_found")])

    def test_fuzzy_fallback_recovers_typo(self, m_collection, m_fuzzy):
        m_collection.return_value = ({}, ["Sol Rng"])
        m_fuzzy.return_value = (_fields("Sol Ring", "Artifact"), None)
        deck = Deck.objects.create(name="Test")

        report = import_to_deck(deck, "1 Sol Rng")

        self.assertEqual(report.imported, 1)
        self.assertTrue(Card.objects.filter(name="Sol Ring").exists())
        # A fuzzy substitution onto a different name must be surfaced.
        self.assertEqual(report.fuzzy_matches, [("Sol Rng", "Sol Ring")])

    def test_duplicate_names_quantities_summed(self, m_collection, m_fuzzy):
        m_collection.return_value = ({"forest": _fields("Forest", "Land")}, [])
        deck = Deck.objects.create(name="Test")

        import_to_deck(deck, "10 Forest\n5 Forest")

        self.assertEqual(deck.entries.get(card__name="Forest").quantity, 15)


@mock.patch("cards.scryfall.lookup_fuzzy")
@mock.patch("cards.scryfall.lookup_collection")
class ReconcileTests(TestCase):
    def _seed_deck(self):
        deck = Deck.objects.create(name="Test")
        sol = Card.objects.create(name="Sol Ring")
        bolt = Card.objects.create(name="Lightning Bolt")
        DeckCard.objects.create(deck=deck, card=sol, quantity=1,
                                is_owned=True, category="Ramp")
        DeckCard.objects.create(deck=deck, card=bolt, quantity=1, is_owned=True)
        return deck, sol, bolt

    def test_reconcile_preserves_owned_and_category(self, m_collection, m_fuzzy):
        deck, sol, bolt = self._seed_deck()
        # New text keeps Sol Ring, drops Lightning Bolt, adds Mana Crypt.
        m_collection.return_value = ({"mana crypt": _fields("Mana Crypt", "Artifact")}, [])

        report = reconcile_deck(deck, "1 Sol Ring\n1 Mana Crypt")

        self.assertEqual(report.removed, 1)
        sol_entry = deck.entries.get(card=sol)
        self.assertTrue(sol_entry.is_owned)        # preserved
        self.assertEqual(sol_entry.category, "Ramp")  # preserved
        self.assertFalse(deck.entries.filter(card=bolt).exists())  # removed
        crypt = deck.entries.get(card__name="Mana Crypt")
        self.assertFalse(crypt.is_owned)           # new card defaults un-owned

    def test_reconcile_clears_removed_commander(self, m_collection, m_fuzzy):
        deck, sol, bolt = self._seed_deck()
        deck.commander = bolt
        deck.save()
        m_collection.return_value = ({}, [])

        reconcile_deck(deck, "1 Sol Ring")  # bolt removed

        deck.refresh_from_db()
        self.assertIsNone(deck.commander)
