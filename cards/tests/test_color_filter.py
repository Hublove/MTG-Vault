"""Tests for the multi-select color-identity filter operators."""
from django.test import TestCase

from cards.models import Card


class ColorIdentityFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # color_identity stored as concatenated WUBRG letters; "" = colorless.
        cls.identities = ["", "W", "G", "U", "GW", "GWU"]
        for ci in cls.identities:
            Card.objects.create(name="Card-" + (ci or "C"), color_identity=ci)

    def _result(self, colors, op):
        return set(
            Card.objects.by_color_identity(colors, op).values_list("color_identity", flat=True)
        )

    def test_lte_at_most_includes_exact_and_colorless(self):
        # ≤ GW → green, white, green-white, and colorless.
        self.assertEqual(self._result("GW", "lte"), {"", "W", "G", "GW"})

    def test_lt_fewer_than_excludes_exact(self):
        # < GW → subsets of GW but NOT GW itself; still includes colorless.
        self.assertEqual(self._result("GW", "lt"), {"", "W", "G"})

    def test_eq_exactly(self):
        self.assertEqual(self._result("GW", "eq"), {"GW"})

    def test_gte_at_least_includes_supersets(self):
        # ≥ GW → has both G and W (GW and GWU), maybe more.
        self.assertEqual(self._result("GW", "gte"), {"GW", "GWU"})

    def test_gt_more_than_excludes_exact(self):
        # > GW → strict supersets of GW only.
        self.assertEqual(self._result("GW", "gt"), {"GWU"})

    def test_single_color_at_most(self):
        # ≤ W → white and colorless only.
        self.assertEqual(self._result("W", "lte"), {"", "W"})

    def test_eq_no_colors_is_colorless_only(self):
        self.assertEqual(self._result("", "eq"), {""})

    def test_gte_no_colors_is_everything(self):
        self.assertEqual(self._result("", "gte"), set(self.identities))

    def test_order_independent_input(self):
        # Selecting "WG" must behave identically to "GW".
        self.assertEqual(self._result("WG", "eq"), {"GW"})


class VaultColorFilterViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for ci in ["", "W", "GW", "GWU"]:
            Card.objects.create(
                name="V-" + (ci or "C"), color_identity=ci, in_vault=True
            )

    def test_view_applies_multi_color_and_operator(self):
        # ?color=G&color=W&color_op=lte → ≤ GW
        resp = self.client.get("/vault/", {"color": ["G", "W"], "color_op": "lte"})
        names = {c.name for c in resp.context["cards"]}
        self.assertEqual(names, {"V-C", "V-W", "V-GW"})

    def test_no_color_params_shows_all(self):
        resp = self.client.get("/vault/")
        self.assertEqual(len(resp.context["cards"]), 4)
