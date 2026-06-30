"""ASGI config for the MTG manager."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mtg.settings")

application = get_asgi_application()
