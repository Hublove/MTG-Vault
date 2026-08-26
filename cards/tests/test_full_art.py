"""Tests for the Full Art gallery (live Scryfall browse page)."""
import uuid
from unittest import mock

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from cards import scryfall, views
from cards.models import Card


def _sid(name):
    """A stable fake Scryfall id for a card name.

    Real ids are UUIDs and the detail route uses the ``uuid`` converter, so
    fixtures can't use readable slugs — tile links wouldn't reverse.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


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
        "id": _sid(name),
        "set": "neo",
        "set_name": "Kamigawa: Neon Dynasty",
        "type_line": "Artifact",
        "rarity": "rare",
        "cmc": 1,
        "colors": [],
        "color_identity": [],
        "image_uris": {"normal": "https://img/" + name + ".png"},
        "scryfall_uri": "https://scryfall.com/x",
        "prices": {"usd": "12.50", "usd_foil": None},
        "released_at": "2022-02-18",
        "edhrec_rank": 42,
    }
    data.update(over)
    return data


def _search_payload(cards, total=None, has_more=False):
    return {
        "data": cards,
        "total_cards": len(cards) if total is None else total,
        "has_more": has_more,
    }


def _gallery(name, **over):
    """A parsed gallery field dict (as extract_gallery_fields would return)."""
    return scryfall.extract_gallery_fields(_scryfall_card(name, **over))


class SearchFullArtTests(TestCase):
    """The /cards/search call the gallery is built on."""

    @mock.patch("cards.scryfall.requests.get")
    def test_default_query_composition(self, m_get):
        m_get.return_value = FakeResp(200, _search_payload([_scryfall_card("Boseiju")]))
        results, total, has_more = scryfall.search_full_art()
        params = m_get.call_args.kwargs["params"]
        self.assertEqual(params["q"], "is:full")
        self.assertEqual(params["unique"], "prints")
        self.assertEqual(params["order"], "released")
        self.assertEqual(params["dir"], "desc")
        self.assertEqual(params["page"], 1)
        self.assertEqual([r["name"] for r in results], ["Boseiju"])
        self.assertEqual(total, 1)
        self.assertFalse(has_more)

    @mock.patch("cards.scryfall.requests.get")
    def test_name_and_set_composition_strips_quotes(self, m_get):
        m_get.return_value = FakeResp(200, _search_payload([]))
        scryfall.search_full_art(name='Sol "Ring"', set_code="neo")
        self.assertEqual(m_get.call_args.kwargs["params"]["q"], 'is:full e:neo "Sol Ring"')

    @mock.patch("cards.scryfall.requests.get")
    def test_exclude_lands_appends_type_filter(self, m_get):
        m_get.return_value = FakeResp(200, _search_payload([]))
        scryfall.search_full_art(exclude_lands=True)
        self.assertEqual(m_get.call_args.kwargs["params"]["q"], "is:full -t:land")

    @mock.patch("cards.scryfall.requests.get")
    def test_exclude_lands_combines_with_set_and_name(self, m_get):
        m_get.return_value = FakeResp(200, _search_payload([]))
        scryfall.search_full_art(name="Sol Ring", set_code="neo", exclude_lands=True)
        self.assertEqual(
            m_get.call_args.kwargs["params"]["q"], 'is:full -t:land e:neo "Sol Ring"'
        )

    @mock.patch("cards.scryfall.requests.get")
    def test_lands_included_by_default(self, m_get):
        m_get.return_value = FakeResp(200, _search_payload([]))
        scryfall.search_full_art(name="Plains")
        self.assertNotIn("-t:land", m_get.call_args.kwargs["params"]["q"])

    @mock.patch("cards.scryfall.requests.get")
    def test_exclude_unpriced_appends_price_filter(self, m_get):
        m_get.return_value = FakeResp(200, _search_payload([]))
        scryfall.search_full_art(exclude_unpriced=True)
        self.assertEqual(m_get.call_args.kwargs["params"]["q"], "is:full usd>0")

    @mock.patch("cards.scryfall.requests.get")
    def test_exclude_unpriced_combines_with_lands_set_and_name(self, m_get):
        m_get.return_value = FakeResp(200, _search_payload([]))
        scryfall.search_full_art(name="Sol Ring", set_code="neo",
                                 exclude_lands=True, exclude_unpriced=True)
        self.assertEqual(
            m_get.call_args.kwargs["params"]["q"], 'is:full -t:land usd>0 e:neo "Sol Ring"'
        )

    @mock.patch("cards.scryfall.requests.get")
    def test_unpriced_included_by_default(self, m_get):
        m_get.return_value = FakeResp(200, _search_payload([]))
        scryfall.search_full_art(name="Plains")
        self.assertNotIn("usd>0", m_get.call_args.kwargs["params"]["q"])

    @mock.patch("cards.scryfall.requests.get")
    def test_sort_and_page_forwarded(self, m_get):
        m_get.return_value = FakeResp(200, _search_payload([]))
        scryfall.search_full_art(order="edhrec", direction="asc", page=3)
        params = m_get.call_args.kwargs["params"]
        self.assertEqual((params["order"], params["dir"], params["page"]), ("edhrec", "asc", 3))

    @mock.patch("cards.scryfall.requests.get")
    def test_404_is_an_empty_result(self, m_get):
        m_get.return_value = FakeResp(404, {"details": "no cards found"})
        self.assertEqual(scryfall.search_full_art(name="zzzznope"), ([], 0, False))

    @mock.patch("cards.scryfall.requests.get")
    def test_non_200_raises(self, m_get):
        m_get.return_value = FakeResp(422, {})
        with self.assertRaises(scryfall.ScryfallError):
            scryfall.search_full_art(page=9999)

    @mock.patch("cards.scryfall.requests.get")
    def test_has_more_flag(self, m_get):
        m_get.return_value = FakeResp(200, _search_payload([_scryfall_card("Bolt")], total=400, has_more=True))
        _results, total, has_more = scryfall.search_full_art()
        self.assertEqual(total, 400)
        self.assertTrue(has_more)

    @mock.patch("cards.scryfall.requests.get")
    def test_gallery_fields_present(self, m_get):
        m_get.return_value = FakeResp(200, _search_payload([_scryfall_card("Boseiju")]))
        card = scryfall.search_full_art()[0][0]
        self.assertEqual(card["released_at"], "2022-02-18")
        self.assertEqual(card["edhrec_rank"], 42)
        self.assertFalse(card["is_double_faced"])
        self.assertEqual(card["set_name"], "Kamigawa: Neon Dynasty")

    def test_gallery_fields_flag_double_faced(self):
        # A transform card carries per-face images and no top-level image_uris.
        payload = _scryfall_card(
            "Boseiju",
            image_uris=None,
            card_faces=[
                {"image_uris": {"normal": "https://img/front.png"}},
                {"image_uris": {"normal": "https://img/back.png"}},
            ],
        )
        fields = scryfall.extract_gallery_fields(payload)
        self.assertTrue(fields["is_double_faced"])
        self.assertEqual(fields["image_uri_back"], "https://img/back.png")

    def test_gallery_fields_tolerate_missing_extras(self):
        payload = _scryfall_card("Plains")
        del payload["released_at"]
        del payload["edhrec_rank"]
        fields = scryfall.extract_gallery_fields(payload)
        self.assertEqual(fields["released_at"], "")
        self.assertIsNone(fields["edhrec_rank"])


class ListSetsTests(TestCase):
    @mock.patch("cards.scryfall.requests.get")
    def test_excludes_digital_and_sorts_newest_first(self, m_get):
        m_get.return_value = FakeResp(200, {"data": [
            {"code": "old", "name": "Old Set", "released_at": "1999-01-01"},
            {"code": "ala", "name": "Arena Only", "released_at": "2024-01-01", "digital": True},
            {"code": "new", "name": "New Set", "released_at": "2026-01-01"},
        ]})
        self.assertEqual(
            scryfall.list_sets(), [("new", "New Set"), ("old", "Old Set")]
        )

    @mock.patch("cards.scryfall.requests.get")
    def test_non_200_raises(self, m_get):
        m_get.return_value = FakeResp(500, {})
        with self.assertRaises(scryfall.ScryfallError):
            scryfall.list_sets()


class FullArtSetChoicesTests(TestCase):
    def setUp(self):
        cache.clear()

    @mock.patch("cards.views.scryfall.list_sets", return_value=[("neo", "Neon Dynasty")])
    def test_caches_across_calls(self, m_list):
        self.assertEqual(views.full_art_set_choices(), [("neo", "Neon Dynasty")])
        self.assertEqual(views.full_art_set_choices(), [("neo", "Neon Dynasty")])
        self.assertEqual(m_list.call_count, 1)

    @mock.patch("cards.views.scryfall.list_sets", side_effect=scryfall.ScryfallError("boom"))
    def test_failure_degrades_to_empty(self, _m):
        self.assertEqual(views.full_art_set_choices(), [])

    @mock.patch("cards.views.scryfall.list_sets", side_effect=views.requests.RequestException("offline"))
    def test_network_failure_degrades_to_empty(self, _m):
        self.assertEqual(views.full_art_set_choices(), [])


@mock.patch("cards.views.full_art_set_choices", return_value=[])
class FullArtGalleryViewTests(TestCase):
    """The page itself. The set dropdown is stubbed out so no test hits the network."""

    url = reverse("cards:full_art")

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_renders_grid_and_pagination_context(self, m_search, _m_sets):
        m_search.return_value = ([_gallery("Boseiju")], 400, True)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_cards"], 400)
        self.assertEqual(resp.context["total_pages"], 3)  # ceil(400 / 175)
        self.assertTrue(resp.context["has_more"])
        self.assertEqual([c["name"] for c in resp.context["cards"]], ["Boseiju"])
        # Tiles open the view-only detail page for that printing.
        self.assertContains(resp, f'href="/full-art/{_sid("Boseiju")}/"')

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_default_sort_is_newest(self, m_search, _m_sets):
        m_search.return_value = ([], 0, False)
        self.client.get(self.url)
        self.assertEqual(m_search.call_args.kwargs["order"], "released")
        self.assertEqual(m_search.call_args.kwargs["direction"], "desc")

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_edhrec_sort_is_ascending(self, m_search, _m_sets):
        m_search.return_value = ([], 0, False)
        resp = self.client.get(self.url, {"sort": "edhrec"})
        self.assertEqual(m_search.call_args.kwargs["order"], "edhrec")
        self.assertEqual(m_search.call_args.kwargs["direction"], "asc")
        self.assertEqual(resp.context["current_sort"], "edhrec")

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_unknown_sort_falls_back_to_newest(self, m_search, _m_sets):
        m_search.return_value = ([], 0, False)
        resp = self.client.get(self.url, {"sort": "; drop table"})
        self.assertEqual(m_search.call_args.kwargs["order"], "released")
        self.assertEqual(resp.context["current_sort"], "newest")

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_name_and_set_forwarded(self, m_search, _m_sets):
        m_search.return_value = ([], 0, False)
        resp = self.client.get(self.url, {"q": "  Sol Ring ", "set": "NEO"})
        self.assertEqual(m_search.call_args.kwargs["name"], "Sol Ring")
        self.assertEqual(m_search.call_args.kwargs["set_code"], "neo")
        self.assertEqual(resp.context["set_code"], "neo")

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_non_alphanumeric_set_is_dropped(self, m_search, _m_sets):
        m_search.return_value = ([], 0, False)
        resp = self.client.get(self.url, {"set": "neo or is:commander"})
        self.assertEqual(m_search.call_args.kwargs["set_code"], "")
        self.assertEqual(resp.context["set_code"], "")

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_hide_lands_excludes_lands_and_ticks_the_box(self, m_search, _m_sets):
        m_search.return_value = ([], 0, False)
        resp = self.client.get(self.url, {"hide_lands": "1"})
        self.assertTrue(m_search.call_args.kwargs["exclude_lands"])
        self.assertTrue(resp.context["hide_lands"])
        self.assertContains(resp, 'name="hide_lands" value="1" checked')

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_lands_shown_unless_hide_lands_is_one(self, m_search, _m_sets):
        m_search.return_value = ([], 0, False)
        for params in ({}, {"hide_lands": "0"}, {"hide_lands": "yes"}):
            resp = self.client.get(self.url, params)
            self.assertFalse(m_search.call_args.kwargs["exclude_lands"], params)
            self.assertFalse(resp.context["hide_lands"], params)

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_hide_unpriced_excludes_unpriced_and_ticks_the_box(self, m_search, _m_sets):
        m_search.return_value = ([], 0, False)
        resp = self.client.get(self.url, {"hide_unpriced": "1"})
        self.assertTrue(m_search.call_args.kwargs["exclude_unpriced"])
        self.assertTrue(resp.context["hide_unpriced"])
        self.assertContains(resp, 'name="hide_unpriced" value="1" checked')

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_unpriced_shown_unless_hide_unpriced_is_one(self, m_search, _m_sets):
        m_search.return_value = ([], 0, False)
        for params in ({}, {"hide_unpriced": "0"}, {"hide_unpriced": "yes"}):
            resp = self.client.get(self.url, params)
            self.assertFalse(m_search.call_args.kwargs["exclude_unpriced"], params)
            self.assertFalse(resp.context["hide_unpriced"], params)

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_both_hide_filters_apply_together(self, m_search, _m_sets):
        m_search.return_value = ([], 0, False)
        resp = self.client.get(self.url, {"hide_lands": "1", "hide_unpriced": "1"})
        self.assertTrue(m_search.call_args.kwargs["exclude_lands"])
        self.assertTrue(m_search.call_args.kwargs["exclude_unpriced"])
        self.assertTrue(resp.context["hide_lands"])
        self.assertTrue(resp.context["hide_unpriced"])

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_tile_shows_price(self, m_search, _m_sets):
        m_search.return_value = ([_gallery("Boseiju")], 1, False)
        resp = self.client.get(self.url)
        # Its own slot on the name row, not tacked onto the truncating set line.
        self.assertContains(resp, '<div class="text-sm text-emerald-400 shrink-0">$12.50</div>')
        self.assertNotContains(resp, "· $12.50")

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_tile_falls_back_to_foil_price(self, m_search, _m_sets):
        # Foil-only printings (no nonfoil price) survive `usd>0`, so the tile has
        # to show their foil price instead of an em-dash.
        card = _gallery("Boseiju", prices={"usd": None, "usd_foil": "31.00"})
        m_search.return_value = ([card], 1, False)
        resp = self.client.get(self.url)
        self.assertContains(resp, '<div class="text-sm text-emerald-400 shrink-0">$31.00</div>')
        self.assertNotContains(resp, '<div class="text-sm text-emerald-400 shrink-0">—</div>')

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_tile_shows_dash_when_unpriced(self, m_search, _m_sets):
        m_search.return_value = ([_gallery("Boseiju", prices={"usd": None})], 1, False)
        resp = self.client.get(self.url)
        self.assertContains(resp, '<div class="text-sm text-emerald-400 shrink-0">—</div>')

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_bad_page_falls_back_to_one(self, m_search, _m_sets):
        m_search.return_value = ([], 0, False)
        for bad in ("abc", "0", "-4"):
            self.client.get(self.url, {"page": bad})
            self.assertEqual(m_search.call_args.kwargs["page"], 1, bad)

    @mock.patch("cards.views.scryfall.search_full_art", side_effect=scryfall.ScryfallError("boom"))
    def test_scryfall_error_still_renders(self, _m_search, _m_sets):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("scryfall_error", resp.context)
        self.assertContains(resp, "Scryfall is unavailable")
        self.assertEqual(resp.context["cards"], [])

    @mock.patch("cards.views.scryfall.search_full_art", side_effect=views.requests.RequestException("offline"))
    def test_network_error_still_renders(self, _m_search, _m_sets):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Scryfall is unavailable")

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_empty_search_shows_no_full_art_message(self, m_search, _m_sets):
        m_search.return_value = ([], 0, False)
        resp = self.client.get(self.url, {"q": "Fblthp"})
        self.assertContains(resp, "No full-art version")
        self.assertContains(resp, "Fblthp")

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_empty_browse_shows_generic_message(self, m_search, _m_sets):
        m_search.return_value = ([], 0, False)
        resp = self.client.get(self.url)
        self.assertContains(resp, "No full-art cards matched")

    @mock.patch("cards.views.scryfall.search_full_art")
    def test_nav_links_to_gallery(self, m_search, _m_sets):
        m_search.return_value = ([], 0, False)
        html = self.client.get(self.url).content.decode()
        # Both nav variants carry the link; they differ only by their classes.
        self.assertIn('<a href="/full-art/" class="hover:text-indigo-300">Full Art</a>', html)
        self.assertIn(
            '<a href="/full-art/" class="block rounded-md px-3 py-2 hover:bg-slate-800">Full Art</a>',
            html,
        )


class FullArtCardDetailViewTests(TestCase):
    """The view-only detail page a gallery tile opens."""

    sid = _sid("Boseiju")

    def setUp(self):
        self.url = reverse("cards:full_art_card_detail", args=[self.sid])
        self.fields = scryfall.extract_card_fields(_scryfall_card("Boseiju"))

    @mock.patch("cards.views.scryfall.lookup_by_id")
    def test_renders_the_printing(self, m_lookup):
        m_lookup.return_value = self.fields
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(m_lookup.call_args.args[0], self.sid)
        self.assertEqual(resp.context["card"].name, "Boseiju")
        self.assertContains(resp, "Kamigawa: Neon Dynasty")
        self.assertContains(resp, "$12.50")  # USD, straight off the payload

    @mock.patch("cards.views.scryfall.lookup_by_id")
    def test_add_to_vault_button_targets_the_add_flow(self, m_lookup):
        m_lookup.return_value = self.fields
        resp = self.client.get(self.url)
        self.assertContains(resp, "+ Add to Vault")
        self.assertContains(resp, f'href="{reverse("cards:card_add")}?scryfall={self.sid}"')

    @mock.patch("cards.views.scryfall.lookup_by_id")
    def test_no_vault_only_sections(self, m_lookup):
        m_lookup.return_value = self.fields
        resp = self.client.get(self.url)
        # Match the headings' markup: "Tags" alone also appears in the site nav.
        self.assertNotContains(resp, '<h2 class="text-sm font-semibold text-slate-300 mb-2">Tags</h2>')
        self.assertNotContains(resp, "Good for commanders")
        self.assertNotContains(resp, '<h2 class="text-sm font-semibold text-slate-300">Notes</h2>')
        self.assertNotContains(resp, "Remove from Vault")

    @mock.patch("cards.views.scryfall.lookup_by_id")
    def test_nothing_is_persisted(self, m_lookup):
        m_lookup.return_value = self.fields
        before = Card.objects.count()
        self.client.get(self.url)
        self.assertEqual(Card.objects.count(), before)

    @mock.patch("cards.views.scryfall.lookup_by_id", return_value=None)
    def test_unknown_id_is_404(self, _m_lookup):
        self.assertEqual(self.client.get(self.url).status_code, 404)

    # The redirect target is never fetched: following it would let the gallery
    # view make a real Scryfall call.
    @mock.patch("cards.views.scryfall.lookup_by_id", side_effect=scryfall.ScryfallError("boom"))
    def test_scryfall_error_redirects_to_the_gallery(self, _m_lookup):
        resp = self.client.get(self.url)
        self.assertRedirects(resp, reverse("cards:full_art"), fetch_redirect_response=False)
        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        self.assertIn("Scryfall is unavailable right now — try again in a moment.", msgs)

    @mock.patch("cards.views.scryfall.lookup_by_id",
                side_effect=views.requests.RequestException("offline"))
    def test_network_error_redirects_to_the_gallery(self, _m_lookup):
        resp = self.client.get(self.url)
        self.assertRedirects(resp, reverse("cards:full_art"), fetch_redirect_response=False)
