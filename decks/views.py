"""Views for decks: list, grouped detail, create/import, bulk edit, export."""
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView

from cards import scryfall

from .forms import BulkEditForm, DeckForm
from .importer import import_to_deck, reconcile_deck
from .models import Deck, DeckCard


class DeckListView(ListView):
    model = Deck
    template_name = "decks/deck_list.html"
    context_object_name = "decks"

    def get_queryset(self):
        return Deck.objects.select_related("commander")


class DeckCreateView(CreateView):
    """Create a deck and optionally import a pasted list immediately."""

    model = Deck
    form_class = DeckForm
    template_name = "decks/deck_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        decklist = form.cleaned_data.get("decklist", "").strip()
        if decklist:
            try:
                report = import_to_deck(self.object, decklist)
                _flash_report(self.request, report)
            except scryfall.ScryfallError as exc:
                messages.error(self.request, f"Scryfall error during import: {exc}")
        return response


class DeckDetailView(View):
    """Grouped decklist with a type/category toggle and owned summary."""

    template_name = "decks/deck_detail.html"

    def get(self, request, pk):
        from django.shortcuts import render

        deck = get_object_or_404(Deck.objects.select_related("commander"), pk=pk)
        group = request.GET.get("group", "type")
        groups = deck.grouped_by_category() if group == "category" else deck.grouped_by_type()
        return render(request, self.template_name, {
            "deck": deck,
            "groups": groups,
            "group_mode": "category" if group == "category" else "type",
            "commander_entry": deck.commander_entry,
            "summary": deck.owned_summary(),
        })


class DeckDeleteView(DeleteView):
    model = Deck
    template_name = "decks/deck_confirm_delete.html"
    success_url = reverse_lazy("decks:list")


class DeckBulkEditView(View):
    """Edit the deck as decklist text; saving replaces contents (owned kept)."""

    template_name = "decks/deck_bulk_edit.html"

    def get(self, request, pk):
        from django.shortcuts import render

        deck = get_object_or_404(Deck, pk=pk)
        form = BulkEditForm(initial={"decklist": deck.as_text()})
        return render(request, self.template_name, {"deck": deck, "form": form})

    def post(self, request, pk):
        from django.shortcuts import render

        deck = get_object_or_404(Deck, pk=pk)
        form = BulkEditForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"deck": deck, "form": form})
        try:
            report = reconcile_deck(deck, form.cleaned_data["decklist"])
            _flash_report(request, report, replaced=True)
        except scryfall.ScryfallError as exc:
            messages.error(request, f"Scryfall error: {exc}")
            return render(request, self.template_name, {"deck": deck, "form": form})
        return redirect(deck)


class ToggleOwnedView(View):
    """Flip the is_owned flag on a deck card (plain POST; redirects back)."""

    def post(self, request, pk):
        entry = get_object_or_404(DeckCard.objects.select_related("deck"), pk=pk)
        entry.is_owned = not entry.is_owned
        entry.save(update_fields=["is_owned"])
        return redirect(request.POST.get("next") or entry.deck.get_absolute_url())


class SetCommanderView(View):
    """Set or clear a deck's commander by deck-card."""

    def post(self, request, pk):
        entry = get_object_or_404(DeckCard.objects.select_related("deck", "card"), pk=pk)
        deck = entry.deck
        if deck.commander_id == entry.card_id:
            deck.commander = None
            messages.info(request, "Commander cleared.")
        else:
            deck.commander = entry.card
            messages.success(request, f"Commander set to {entry.card.name}.")
        deck.save(update_fields=["commander"])
        return redirect(deck)


class DeckExportView(View):
    """Return the deck as plain text for copy/paste into Moxfield/Arena."""

    def get(self, request, pk):
        deck = get_object_or_404(Deck, pk=pk)
        return HttpResponse(deck.as_text(), content_type="text/plain; charset=utf-8")


def _flash_report(request, report, *, replaced=False):
    """Turn an ImportReport into user-facing flash messages."""
    verb = "Synced" if replaced else "Imported"
    parts = [f"{verb} {report.imported} card(s)"]
    if report.created_cards:
        parts.append(f"{report.created_cards} new to library")
    if report.removed:
        parts.append(f"{report.removed} removed")
    messages.success(request, ", ".join(parts) + ".")
    for requested, matched in report.fuzzy_matches:
        messages.warning(
            request,
            f"Fuzzy match: “{requested}” → “{matched}”. Verify this is the card you meant.",
        )
    for name, reason in report.failures:
        label = "ambiguous" if reason == "ambiguous" else "no match"
        messages.warning(request, f"Couldn't import “{name}” ({label}).")
