from django.urls import path

from . import views

app_name = "decks"

urlpatterns = [
    path("", views.DeckListView.as_view(), name="list"),
    path("new/", views.DeckCreateView.as_view(), name="create"),
    path("<int:pk>/", views.DeckDetailView.as_view(), name="detail"),
    path("<int:pk>/delete/", views.DeckDeleteView.as_view(), name="delete"),
    path("<int:pk>/edit-list/", views.DeckBulkEditView.as_view(), name="bulk_edit"),
    path("<int:pk>/export/", views.DeckExportView.as_view(), name="export"),
    # Per-entry actions
    path("entry/<int:pk>/toggle-owned/", views.ToggleOwnedView.as_view(), name="toggle_owned"),
    path("entry/<int:pk>/set-commander/", views.SetCommanderView.as_view(), name="set_commander"),
]
