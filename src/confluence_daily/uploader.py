from __future__ import annotations

from datetime import date
from pathlib import Path
import re
from uuid import uuid4

from .calendar_utils import month_page_title, report_month_for_date
from .config import AppConfig
from .confluence_client import ConfluenceClient
from .models import ConflictPolicy, DailyInput, UploadResult, UploadedAttachment
from .page_builder import (
    build_month_storage,
    has_daily_conflict_for_month,
    update_storage_for_entry_for_month,
)
from .state import DailyState


IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm", ".wmv"}


class DailyUploader:
    def __init__(
        self,
        config: AppConfig,
        client: ConfluenceClient | None = None,
        session_cookies: str | None = None,
        state: DailyState | None = None,
    ) -> None:
        config.validate_for_upload()
        self.config = config
        self.client = client or ConfluenceClient(config, session_cookies=session_cookies)
        self.state = state or DailyState()

    def upload(self, daily: DailyInput, conflict_policy: ConflictPolicy = "cancel") -> UploadResult:
        report_month = report_month_for_date(daily.work_date, self.config.month_page_policy)
        title = month_page_title(self.config.user_name, report_month)
        page = self.client.find_page_by_title(title)
        if page is None:
            initial_storage = build_month_storage(report_month.year, report_month.month)
            page = self.client.create_page(title, initial_storage)
        else:
            page = self.client.get_page(page.page_id)

        if conflict_policy == "cancel" and has_daily_conflict_for_month(
            page.storage,
            daily.work_date,
            report_month.year,
            report_month.month,
        ):
            update_storage_for_entry_for_month(
                page.storage,
                daily.work_date,
                tuple(),
                daily.comment,
                report_month.year,
                report_month.month,
                "cancel",
            )

        uploaded = tuple(self._upload_files(page.page_id, daily.work_date, daily.file_paths))
        updated_storage = update_storage_for_entry_for_month(
            page.storage,
            daily.work_date,
            uploaded,
            daily.comment,
            report_month.year,
            report_month.month,
            conflict_policy,
        )
        updated = self.client.update_page(page, updated_storage, "Update daily report")
        self.state.mark_uploaded(daily.work_date, updated.page_id, updated.web_url)

        return UploadResult(
            page_id=updated.page_id,
            page_title=updated.title,
            page_url=updated.web_url,
            attachment_names=tuple(item.attachment_name for item in uploaded),
        )

    def _upload_files(
        self,
        page_id: str,
        work_date: date,
        file_paths: tuple[Path, ...],
    ) -> list[UploadedAttachment]:
        uploaded: list[UploadedAttachment] = []
        for path in file_paths:
            source = Path(path)
            attachment_name = make_attachment_name(work_date, source)
            self.client.upload_attachment(page_id, source, attachment_name)
            uploaded.append(
                UploadedAttachment(
                    source_path=source,
                    attachment_name=attachment_name,
                    media_kind=classify_media(source),
                )
            )
        return uploaded


def classify_media(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return "other"


def make_attachment_name(work_date: date, path: Path) -> str:
    safe_name = re.sub(r"[^\w._-]+", "_", path.name).strip("._")
    if not safe_name:
        safe_name = "attachment"
    return f"{work_date:%Y%m%d}_{uuid4().hex[:8]}_{safe_name}"
