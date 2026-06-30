"""Forms for deck creation, import, and bulk editing."""
from django import forms

from .models import Deck

_INPUT = (
    "w-full rounded-md bg-slate-800 border border-slate-700 px-3 py-2 "
    "text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 "
    "focus:ring-indigo-500"
)
_TEXTAREA = _INPUT + " font-mono text-sm"


class DeckForm(forms.ModelForm):
    """Create/edit deck metadata, with an optional initial decklist paste."""

    decklist = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": _TEXTAREA,
            "rows": 12,
            "placeholder": "Optional: paste a decklist to import\n1 Sol Ring\n1 Arcane Signet\n...",
        }),
        help_text="Paste a list to import now. You can set the commander afterward.",
    )

    class Meta:
        model = Deck
        fields = ["name", "description", "format"]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT}),
            "description": forms.Textarea(attrs={"class": _INPUT, "rows": 2}),
            "format": forms.Select(attrs={"class": _INPUT}),
        }


class BulkEditForm(forms.Form):
    """Edit the whole decklist as text; saving replaces the deck contents."""

    decklist = forms.CharField(
        widget=forms.Textarea(attrs={"class": _TEXTAREA, "rows": 24}),
        help_text="Edit freely. Saving replaces the deck; owned/category flags "
                  "are kept for cards that remain.",
    )
