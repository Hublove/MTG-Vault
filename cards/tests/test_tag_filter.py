"""Tests for the multi-select tag filter (Any/All match modes)."""
from django.test import TestCase

from cards.models import Card, Tag


class ByTagsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ramp = Tag.objects.create(name="ramp")
        removal = Tag.objects.create(name="removal")
        cls.a = Card.objects.create(name="A", in_vault=True)
        cls.b = Card.objects.create(name="B", in_vault=True)
        cls.c = Card.objects.create(name="C", in_vault=True)
        cls.d = Card.objects.create(name="D", in_vault=True)
        cls.a.tags.add(ramp)
        cls.b.tags.add(ramp, removal)
        cls.c.tags.add(removal)
        # D has no tags.

    def _names(self, slugs, match):
        return set(
            Card.objects.by_tags(slugs, match).distinct().values_list("name", flat=True)
        )

    def test_any_is_union(self):
        self.assertEqual(self._names(["ramp", "removal"], "any"), {"A", "B", "C"})

    def test_all_is_intersection(self):
        self.assertEqual(self._names(["ramp", "removal"], "all"), {"B"})

    def test_single_tag_either_mode(self):
        self.assertEqual(self._names(["ramp"], "any"), {"A", "B"})
        self.assertEqual(self._names(["ramp"], "all"), {"A", "B"})

    def test_empty_selection_unchanged(self):
        self.assertEqual(Card.objects.by_tags([], "any").count(), 4)
        self.assertEqual(Card.objects.by_tags([""], "all").count(), 4)


class VaultTagFilterViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ramp = Tag.objects.create(name="ramp")
        removal = Tag.objects.create(name="removal")
        a = Card.objects.create(name="A", in_vault=True)
        b = Card.objects.create(name="B", in_vault=True)
        c = Card.objects.create(name="C", in_vault=True)
        a.tags.add(ramp)
        b.tags.add(ramp, removal)
        c.tags.add(removal)

    def test_match_all(self):
        resp = self.client.get("/vault/", {"tag": ["ramp", "removal"], "tag_match": "all"})
        self.assertEqual({c.name for c in resp.context["cards"]}, {"B"})

    def test_match_any_default(self):
        resp = self.client.get("/vault/", {"tag": ["ramp", "removal"]})
        self.assertEqual({c.name for c in resp.context["cards"]}, {"A", "B", "C"})
