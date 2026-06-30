"""Backfill every existing Tag with a random color from the palette.

Tag.color changed from a Tailwind family name to a hex value; assign all current
tags a random palette hex so they render with varied colors going forward.
"""
import random

from django.db import migrations

from cards.constants import TAG_PALETTE


def randomize_colors(apps, schema_editor):
    Tag = apps.get_model("cards", "Tag")
    for tag in Tag.objects.all():
        tag.color = random.choice(TAG_PALETTE)
        tag.save(update_fields=["color"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0004_alter_tag_color"),
    ]

    operations = [
        migrations.RunPython(randomize_colors, noop),
    ]
