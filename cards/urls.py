from django.urls import path

from . import views

app_name = "cards"

urlpatterns = [
    path("vault/", views.VaultListView.as_view(), name="vault"),
    path("cards/add/", views.CardAddView.as_view(), name="card_add"),
    path("cards/search.json", views.CardSearchAPIView.as_view(), name="card_search"),
    path("cards/<int:pk>/", views.CardDetailView.as_view(), name="card_detail"),
    path("cards/<int:pk>/tags/", views.CardTagsUpdateView.as_view(), name="card_tags"),
    path("cards/<int:pk>/notes/", views.CardNotesUpdateView.as_view(), name="card_notes"),
    path("cards/<int:pk>/commanders/", views.CardCommandersUpdateView.as_view(), name="card_commanders"),
    path("cards/<int:pk>/remove/", views.VaultRemoveView.as_view(), name="card_remove"),
    # Commanders
    path("commanders/", views.CommanderListView.as_view(), name="commander_list"),
    path("commanders/<int:pk>/", views.CommanderDetailView.as_view(), name="commander_detail"),
    # Tag management
    path("tags/", views.TagListView.as_view(), name="tag_list"),
    path("tags/new/", views.TagCreateView.as_view(), name="tag_create"),
    path("tags/<int:pk>/edit/", views.TagUpdateView.as_view(), name="tag_update"),
    path("tags/<int:pk>/delete/", views.TagDeleteView.as_view(), name="tag_delete"),
]
