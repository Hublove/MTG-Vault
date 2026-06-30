"""Refresh prices/data for cards we already track from the Scryfall bulk file.

Why the bulk file (not the per-card API): Scryfall asks that bulk price work use
the downloadable bulk data rather than hammering the card endpoints. We download
the "Oracle Cards" file once, stream it, and update only the ``Card`` rows that
already exist locally. Tags and Vault membership are never touched — only
Scryfall-sourced fields, via ``extract_card_fields`` + the model's update path.
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from cards import scryfall
from cards.models import Card


class Command(BaseCommand):
    help = "Download Scryfall bulk data and refresh prices for tracked cards."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            help="Use an existing bulk JSON file instead of downloading.",
        )
        parser.add_argument(
            "--no-download",
            action="store_true",
            help="Skip download; require an already-cached bulk file.",
        )

    def handle(self, *args, **options):
        path = options.get("file") or settings.SCRYFALL_BULK_PATH

        # We only care about cards we already have; build a name->Card map.
        cards_by_name = {c.name: c for c in Card.objects.all()}
        if not cards_by_name:
            self.stdout.write(self.style.WARNING("No local cards to update. Done."))
            return

        if not options["no_download"] and not options.get("file"):
            self.stdout.write("Downloading Scryfall Oracle Cards bulk file…")
            scryfall.download_bulk_to(path)
        self.stdout.write(f"Reading bulk data from {path}…")

        updated = 0
        now = timezone.now()
        to_save = []
        for payload in scryfall.iter_bulk_cards(path):
            name = payload.get("name")
            card = cards_by_name.get(name)
            if card is None:
                continue
            fields = scryfall.extract_card_fields(payload)
            # Refresh Scryfall-sourced fields only; leave in_vault/tags alone.
            for key in Card.objects.SCRYFALL_FIELDS:
                setattr(card, key, fields.get(key))
            card.last_price_update = now
            to_save.append(card)
            updated += 1

        with transaction.atomic():
            Card.objects.bulk_update(
                to_save,
                list(Card.objects.SCRYFALL_FIELDS) + ["last_price_update"],
                batch_size=500,
            )

        self.stdout.write(self.style.SUCCESS(
            f"Updated {updated} of {len(cards_by_name)} tracked cards."
        ))
