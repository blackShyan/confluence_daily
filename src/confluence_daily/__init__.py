"""Confluence Daily Uploader."""

_DEFAULT_VERSION = "0.1.1"

try:
    from ._build_version import __version__
except ImportError:
    __version__ = _DEFAULT_VERSION
