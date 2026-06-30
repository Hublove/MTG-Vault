"""Root URL configuration."""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    # The Vault is the home screen.
    path("", RedirectView.as_view(pattern_name="cards:vault", permanent=False)),
    path("", include("cards.urls")),
    path("decks/", include("decks.urls")),
]
