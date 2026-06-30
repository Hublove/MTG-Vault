from django.contrib import admin

from .models import Card, CardTag, Tag


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ("name", "set_code", "primary_type", "rarity", "price_usd", "in_vault")
    list_filter = ("in_vault", "primary_type", "rarity")
    search_fields = ("name",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "color")
    prepopulated_fields = {"slug": ("name",)}


admin.site.register(CardTag)
