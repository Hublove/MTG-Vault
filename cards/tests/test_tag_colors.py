"""Tests for random tag colors + the color picker form."""
from django.test import TestCase
from django.urls import reverse

from cards.constants import TAG_PALETTE, random_tag_color
from cards.models import Card, Tag


class RandomColorTests(TestCase):
    def test_palette_is_64_unique_hex(self):
        self.assertEqual(len(TAG_PALETTE), 64)
        self.assertEqual(len(set(TAG_PALETTE)), 64)
        self.assertTrue(all(c.startswith("#") and len(c) == 7 for c in TAG_PALETTE))

    def test_random_tag_color_in_palette(self):
        self.assertIn(random_tag_color(), TAG_PALETTE)

    def test_new_tag_from_csv_gets_palette_color(self):
        (tag,) = Tag.objects.get_or_create_from_csv("ramp")
        self.assertIn(tag.color, TAG_PALETTE)

    def test_existing_tag_color_preserved(self):
        existing = Tag.objects.create(name="ramp", color="#123456")
        (tag,) = Tag.objects.get_or_create_from_csv("Ramp")  # same slug
        self.assertEqual(tag.pk, existing.pk)
        self.assertEqual(tag.color, "#123456")


class AddCardTagColorTests(TestCase):
    def test_tag_created_during_add_gets_color(self):
        # CardTagsUpdateView (card-detail editor) routes through get_or_create_from_csv.
        card = Card.objects.create(name="Sol Ring", in_vault=True)
        self.client.post(reverse("cards:card_tags", args=[card.pk]), {"tags": "brandnew"})
        tag = Tag.objects.get(slug="brandnew")
        self.assertIn(tag.color, TAG_PALETTE)


class TagFormGridTests(TestCase):
    def test_edit_page_renders_8x8_grid(self):
        tag = Tag.objects.create(name="ramp", color=TAG_PALETTE[0])
        resp = self.client.get(reverse("cards:tag_update", args=[tag.pk]))
        self.assertContains(resp, "grid-cols-8")
        # 64 swatch buttons present.
        self.assertEqual(resp.content.decode().count('data-color="'), 64)

    def test_create_page_preselects_random_color(self):
        resp = self.client.get(reverse("cards:tag_create"))
        # Hidden color input has a palette value as its initial.
        html = resp.content.decode()
        self.assertIn('id="id_color"', html)

    def test_saving_color_persists_hex(self):
        tag = Tag.objects.create(name="ramp")
        self.client.post(
            reverse("cards:tag_update", args=[tag.pk]),
            {"name": "ramp", "color": "#ec4899"},
        )
        tag.refresh_from_db()
        self.assertEqual(tag.color, "#ec4899")
