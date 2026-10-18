"""M1 intake router; mounted through the application's authenticated boundary."""

from .router import create_intake_router

__all__ = ["create_intake_router"]
