"""WSGI entry point for the Alluora platform."""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'alluora.settings')
application = get_wsgi_application()
