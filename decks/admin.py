from django.contrib import admin

from .models import Deck, DeckCard


class DeckCardInline(admin.TabularInline):
    model = DeckCard
    raw_id_fields = ("card",)
    extra = 0


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = ("name", "format", "commander", "updated_at")
    list_filter = ("format",)
    search_fields = ("name",)
    raw_id_fields = ("commander",)
    inlines = [DeckCardInline]
