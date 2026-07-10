"""Shared rate limiter for the application.

Initialized by app.py on startup, imported by api.py for per-endpoint limits.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
