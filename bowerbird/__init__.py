"""Bowerbird — browser bookmark audit, curation and discovery."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("bowerbird-bookmarks")
except PackageNotFoundError:  # running from a source checkout
    __version__ = "unknown"
