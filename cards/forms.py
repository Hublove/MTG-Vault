"""Forms for adding cards to the Vault and managing tags."""
from django import forms

from .models import Tag

# Shared Tailwind input styling.
_INPUT = (
    "w-full rounded-md bg-slate-800 border border-slate-700 px-3 py-2 "
    "text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 "
    "focus:ring-indigo-500"
)


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name", "color"]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT}),
            # Color is chosen from the 8×8 swatch grid in the template; the grid
            # writes the selected hex into this hidden input.
            "color": forms.HiddenInput(attrs={"id": "id_color"}),
        }
