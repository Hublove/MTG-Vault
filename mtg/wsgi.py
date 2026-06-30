"""WSGI config for the MTG manager."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mtg.settings")

application = get_wsgi_application()
