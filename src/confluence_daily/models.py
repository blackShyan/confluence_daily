from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal


MediaKind = Literal["image", "video", "other"]
ConflictPolicy = Literal["cancel", "overwrite", "append"]


@dataclass(frozen=True)
class DailyInput:
    work_date: date
    file_paths: tuple[Path, ...]
    comment: str


@dataclass(frozen=True)
class UploadedAttachment:
    source_path: Path
    attachment_name: str
    media_kind: MediaKind


@dataclass(frozen=True)
class PagePayload:
    page_id: str
    title: str
    version: int
    storage: str
    web_url: str | None = None


@dataclass(frozen=True)
class UploadResult:
    page_id: str
    page_title: str
    page_url: str | None
    attachment_names: tuple[str, ...]


class DailyUploaderError(RuntimeError):
    """Base error for daily uploader failures."""


class DailyEntryConflict(DailyUploaderError):
    """Raised when a date row already has content and policy is cancel."""


class ConfigurationError(DailyUploaderError):
    """Raised when the app is missing required settings."""


class ConfluenceApiError(DailyUploaderError):
    """Raised when Confluence returns an unsuccessful response."""

