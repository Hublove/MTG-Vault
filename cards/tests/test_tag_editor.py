"""Tests for the card-detail tag editor (CardTagsUpdateView, CSV/set)."""
from django.test import TestCase
from django.urls import reverse

from cards.models import Card, Tag


class CardTagsUpdateTests(TestCase):
    def setUp(self):
        self.card = Card.objects.create(name="Sol Ring", in_vault=True)

    def _post(self, tags):
        return self.client.post(
            reverse("cards:card_tags", args=[self.card.pk]), {"tags": tags}
        )

    def test_sets_and_creates_tags(self):
        self._post("ramp, removal")
        self.assertEqual(
            set(self.card.tags.values_list("name", flat=True)), {"ramp", "removal"}
        )
        self.assertTrue(Tag.objects.filter(slug="removal").exists())

    def test_set_replaces_previous_and_reuses_by_slug(self):
        ramp = Tag.objects.create(name="ramp")
        self.card.tags.add(ramp)
        # New set drops ramp, adds draw; "Ramp" elsewhere wouldn't duplicate.
        self._post("draw")
        self.assertEqual(list(self.card.tags.values_list("name", flat=True)), ["draw"])
        # Re-add ramp by different case → reuse, no duplicate Tag row.
        self._post("draw, RAMP")
        self.assertEqual(Tag.objects.filter(slug="ramp").count(), 1)
        self.assertEqual(
            set(self.card.tags.values_list("name", flat=True)), {"draw", "ramp"}
        )

    def test_empty_clears_all_tags(self):
        self.card.tags.add(Tag.objects.create(name="ramp"))
        self._post("")
        self.assertEqual(self.card.tags.count(), 0)

    def test_detail_page_seeds_current_tags(self):
        self.card.tags.add(Tag.objects.create(name="ramp"))
        resp = self.client.get(reverse("cards:card_detail", args=[self.card.pk]))
        self.assertContains(resp, 'id="initial-tags"')
        self.assertContains(resp, "ramp")
