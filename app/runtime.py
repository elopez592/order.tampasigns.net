"""Request-local configuration. Tenant credentials never fall back to root secrets."""
from contextvars import ContextVar
import os

configuration = ContextVar('company_configuration', default=None)


def getenv(key, default=None):
    config = configuration.get()
    return os.getenv(key, default) if config is None else config.get(key, default)
