"""Views for the Vault (card browser), card detail, add flow, and tag CRUD."""
from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .constants import (
    COLOR_NAMES,
    COLOR_ORDER,
    COLOR_SWATCH,
    TAG_PALETTE,
    TYPE_LABELS,
    random_tag_color,
)
from .forms import TagForm
from .models import Card, Tag
from . import scryfall

# Allowed sort options -> ORM ordering. "recent" is the Vault default.
SORT_OPTIONS = {
    "recent": ("-added_to_vault_at", "-id"),
    "price_desc": ("-price_usd",),
    "price_asc": ("price_usd",),
    "name": ("name",),
}


class VaultListView(ListView):
    """The Vault: browse, filter, and sort cards the user has collected."""

    model = Card
    template_name = "cards/vault_list.html"
    context_object_name = "cards"
    paginate_by = 60

    def get_queryset(self):
        qs = Card.objects.in_vault().prefetch_related("tags")
        params = self.request.GET

        selected_tags = params.getlist("tag")
        if selected_tags:
            qs = qs.by_tags(selected_tags, params.get("tag_match", "any"))
        if set_code := params.get("set"):
            qs = qs.filter(set_code=set_code)
        if ctype := params.get("type"):
            qs = qs.filter(primary_type=ctype)
        if rarity := params.get("rarity"):
            qs = qs.filter(rarity=rarity)
        # Multi-select color identity with a set-comparison operator. Inactive on
        # first load (no params) so the Vault shows everything by default.
        selected_colors = params.getlist("color")
        color_op = params.get("color_op")
        if selected_colors or color_op:
            qs = qs.by_color_identity(selected_colors, color_op or "lte")

        sort = params.get("sort", "recent")
        ordering = SORT_OPTIONS.get(sort, SORT_OPTIONS["recent"])
        return qs.order_by(*ordering).distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        vault = Card.objects.in_vault()
        # Filter option lists, derived from what's actually in the Vault.
        ctx["all_tags"] = Tag.objects.filter(cards__in_vault=True).distinct().annotate(
            n=Count("cards")
        )
        ctx["sets"] = (
            vault.exclude(set_code="").values_list("set_code", "set_name").distinct().order_by("set_name")
        )
        ctx["types"] = [
            (key, TYPE_LABELS[key])
            for key in TYPE_LABELS
            if vault.filter(primary_type=key).exists()
        ]
        ctx["rarities"] = vault.exclude(rarity="").values_list("rarity", flat=True).distinct().order_by("rarity")
        ctx["selected_tags"] = self.request.GET.getlist("tag")
        ctx["current_tag_match"] = self.request.GET.get("tag_match", "any")
        ctx["color_choices"] = [(c, COLOR_NAMES[c], COLOR_SWATCH[c]) for c in COLOR_ORDER]
        ctx["selected_colors"] = self.request.GET.getlist("color")
        ctx["color_ops"] = [
            ("lte", "≤ at most"),
            ("lt", "< fewer than"),
            ("eq", "= exactly"),
            ("gte", "≥ at least"),
            ("gt", "> more than"),
        ]
        ctx["current_color_op"] = self.request.GET.get("color_op", "lte")
        ctx["sort_options"] = SORT_OPTIONS
        ctx["current"] = self.request.GET
        return ctx


class CardDetailView(DetailView):
    model = Card
    template_name = "cards/card_detail.html"
    context_object_name = "card"

    def get_queryset(self):
        return super().get_queryset().prefetch_related("tags", "suggested_commanders")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Data for the shared tag combobox: all tags for suggestions, this card's
        # current tags pre-seeded as chips.
        ctx["all_tag_names"] = list(Tag.objects.values_list("name", flat=True))
        ctx["initial_tag_names"] = list(self.object.tags.values_list("name", flat=True))
        # Data for the commander combobox editor (+ button).
        ctx["commander_options"] = commander_options()
        ctx["initial_commanders"] = [
            {"name": c.name, "scryfall_id": c.scryfall_id}
            for c in self.object.suggested_commanders.all()
        ]
        return ctx


def commander_options():
    """The existing commander list, as lightweight dicts for the combobox."""
    return [
        {"name": c.name, "scryfall_id": c.scryfall_id, "set_code": c.set_code}
        for c in Card.objects.commanders().order_by("name")
    ]


def resolve_commanders(scryfall_ids):
    """Resolve a list of Scryfall ids to commander Card rows, creating missing ones.

    Existing local cards (incl. deck commanders) match by ``scryfall_id``; unknown
    ids are fetched and upserted as reference rows (``in_vault`` untouched). Used by
    the add flow to attach a card's suggested commanders.
    """
    cards = []
    for sid in scryfall_ids:
        sid = sid.strip()
        if not sid:
            continue
        card = Card.objects.filter(scryfall_id=sid).first()
        if card is None:
            fields = scryfall.lookup_by_id(sid)
            if fields is None:
                continue
            card, _ = Card.objects.upsert_from_payload(fields)
        cards.append(card)
    return cards


class CardSearchAPIView(View):
    """JSON search endpoint backing the live "Add a card" results grid."""

    def get(self, request):
        query = request.GET.get("q", "").strip()
        commanders = request.GET.get("commanders") == "1"
        if not query:
            return JsonResponse({"results": [], "truncated": False})
        try:
            results, truncated = scryfall.search_cards(query, commanders=commanders)
        except scryfall.ScryfallError as exc:
            return JsonResponse({"error": str(exc)}, status=502)
        # Expose only what the grid needs; image_uri is the full card art.
        payload = [
            {
                "name": r["name"],
                "scryfall_id": r["scryfall_id"],
                "image_uri": r["image_uri"],
                "set_code": r["set_code"],
                "set_name": r["set_name"],
                "price_usd": str(r["price_usd"]) if r["price_usd"] is not None else None,
            }
            for r in results
        ]
        return JsonResponse({"results": payload, "truncated": truncated})


class CardAddView(View):
    """Search Scryfall, pick a card from the results grid, and add it to the Vault.

    GET renders the search page (results load via AJAX from CardSearchAPIView).
    POST confirms the chosen card by Scryfall id and adds it.
    """

    template_name = "cards/card_add.html"

    def _context(self):
        # Existing tag names power the tag combobox; existing commanders seed the
        # commander combobox's default options.
        return {
            "all_tag_names": list(Tag.objects.values_list("name", flat=True)),
            "initial_tag_names": [],
            "commander_options": commander_options(),
            "initial_commanders": [],
        }

    def get(self, request):
        from django.shortcuts import render
        return render(request, self.template_name, self._context())

    def post(self, request):
        from django.shortcuts import render

        scryfall_id = request.POST.get("scryfall_id", "").strip()
        if not scryfall_id:
            messages.error(request, "Pick a card from the results first.")
            return render(request, self.template_name, self._context())
        try:
            fields = scryfall.lookup_by_id(scryfall_id)
        except scryfall.ScryfallError as exc:
            messages.error(request, f"Scryfall error: {exc}")
            return render(request, self.template_name, self._context())
        if fields is None:
            messages.error(request, "That card could not be found on Scryfall.")
            return render(request, self.template_name, self._context())

        # Add the card and apply tags atomically: tags are only created here —
        # after a confirmed add — so an abandoned add never leaves orphan tags,
        # and a failure mid-block rolls back any tag rows just created.
        with transaction.atomic():
            card, created = Card.objects.upsert_from_payload(fields, add_to_vault=True)
            if created:
                msg = f"Added “{card.name}” to the Vault."
            elif card.in_vault:
                msg = f"“{card.name}” is already in the Vault (data refreshed)."
            else:
                card.add_to_vault()
                msg = f"Added existing card “{card.name}” to the Vault."

            # Apply (and auto-create) any tags typed in the confirm bar.
            tags = Tag.objects.get_or_create_from_csv(request.POST.get("tags", ""))
            if tags:
                card.tags.add(*tags)
                msg = f"{msg.rstrip('.')} with {len(tags)} tag{'s' if len(tags) != 1 else ''}."

            # Notes + suggested commanders (commanders resolved/created on submit).
            card.notes = request.POST.get("notes", "").strip()
            card.save(update_fields=["notes"])
            commanders = resolve_commanders(request.POST.getlist("commanders"))
            if commanders:
                card.suggested_commanders.set(commanders)
        messages.success(request, msg)
        return redirect(card)


class CardTagsUpdateView(View):
    """Set a Vault card's tags from the combobox's comma-separated value.

    The chip list is the full desired set, so we ``set`` (not ``add``) — an empty
    value clears all tags. New tag names are created on save (only here), reusing
    existing ones by slug.
    """

    def post(self, request, pk):
        card = get_object_or_404(Card, pk=pk)
        with transaction.atomic():
            tags = Tag.objects.get_or_create_from_csv(request.POST.get("tags", ""))
            card.tags.set(tags)
        messages.success(request, "Tags updated.")
        return redirect(card)


class CardNotesUpdateView(View):
    """Save the freeform notes for a card (pen-edit on the card page)."""

    def post(self, request, pk):
        card = get_object_or_404(Card, pk=pk)
        card.notes = request.POST.get("notes", "").strip()
        card.save(update_fields=["notes"])
        messages.success(request, "Notes saved.")
        return redirect(card)


class CardCommandersUpdateView(View):
    """Set a card's suggested commanders from the combobox (+ editor on the card page).

    The chip list is the full desired set, so we ``set`` — an empty submit clears
    them. New commanders are created/reused via ``resolve_commanders``.
    """

    def post(self, request, pk):
        card = get_object_or_404(Card, pk=pk)
        with transaction.atomic():
            commanders = resolve_commanders(request.POST.getlist("commanders"))
            card.suggested_commanders.set(commanders)
        messages.success(request, "Commanders updated.")
        return redirect(card)


class CommanderListView(ListView):
    """All commanders (deck commanders + suggested-as-commander cards)."""

    template_name = "cards/commander_list.html"
    context_object_name = "commanders"

    def get_queryset(self):
        return Card.objects.commanders().annotate(
            n_suggested=Count("suggested_cards", distinct=True)
        ).order_by("name")


class CommanderDetailView(DetailView):
    """A commander's page: its info plus the cards suggested for it."""

    model = Card
    template_name = "cards/commander_detail.html"
    context_object_name = "commander"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["suggested"] = self.object.suggested_cards.prefetch_related("tags").order_by("name")
        ctx["decks_led"] = self.object.commands_decks.all()
        return ctx


class VaultRemoveView(View):
    """Remove a card from the Vault (keeps the row for any deck use)."""

    def post(self, request, pk):
        card = get_object_or_404(Card, pk=pk)
        card.remove_from_vault()
        messages.info(request, f"Removed “{card.name}” from the Vault.")
        return redirect("cards:vault")


# --- Tag management --------------------------------------------------------

class TagListView(ListView):
    model = Tag
    template_name = "cards/tag_list.html"
    context_object_name = "tags"

    def get_queryset(self):
        return Tag.objects.annotate(n=Count("cards"))


class TagFormMixin:
    """Shared config for the tag create/edit form (the 8×8 color grid)."""

    model = Tag
    form_class = TagForm
    template_name = "cards/tag_form.html"
    success_url = reverse_lazy("cards:tag_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tag_palette"] = TAG_PALETTE
        return ctx


class TagCreateView(TagFormMixin, CreateView):
    def get_initial(self):
        # Preselect a random swatch so a new tag is never colorless.
        return {**super().get_initial(), "color": random_tag_color()}


class TagUpdateView(TagFormMixin, UpdateView):
    pass


class TagDeleteView(DeleteView):
    model = Tag
    template_name = "cards/tag_confirm_delete.html"
    success_url = reverse_lazy("cards:tag_list")
