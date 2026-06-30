"""Root URL configuration."""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Service worker must be served from the root so its scope covers the whole app.
    path(
        "sw.js",
        TemplateView.as_view(template_name="sw.js", content_type="application/javascript"),
        name="sw",
    ),
    # The Vault is the home screen.
    path("", RedirectView.as_view(pattern_name="cards:vault", permanent=False)),
    path("", include("cards.urls")),
    path("decks/", include("decks.urls")),
]
