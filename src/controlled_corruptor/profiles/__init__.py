"""External game profile framework."""

from __future__ import annotations

from .loader import ProfileLibrary, load_profile_file
from .schema import GameProfile

__all__ = ["GameProfile", "ProfileLibrary", "load_profile_file"]
