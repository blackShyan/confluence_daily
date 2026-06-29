from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path

from .models import ConfigurationError


APP_NAME = "ConfluenceDailyUploader"
COOKIE_SERVICE = "ConfluenceDailyUploader.ConfluenceSessionCookies"


@dataclass(frozen=True)
class AppConfig:
    base_url: str = ""
    email: str = ""
    api_mode: str = "data_center"
    space_id: str = ""
    space_key: str = ""
    parent_page_id: str = ""
    user_name: str = "\uc0ac\uc6a9\uc790"
    month_page_policy: str = "workweek_end_month"
    reminder_time: str = "18:00"
    timezone: str = "Asia/Seoul"
    autostart: bool = False

    @property
    def is_data_center(self) -> bool:
        return self.api_mode == "data_center"

    @property
    def credential_account(self) -> str:
        return self.email.strip() or self.base_url.strip()

    @property
    def effective_space_key(self) -> str:
        return (self.space_key or self.space_id).strip()

    def validate_for_upload(self) -> None:
        missing = []
        if not self.base_url.strip():
            missing.append("Confluence URL")
        if not self.credential_account:
            missing.append("login account")
        if self.is_data_center:
            if not self.effective_space_key:
                missing.append("space_key")
        elif not self.space_id.strip():
            missing.append("space_id")
        if not self.parent_page_id.strip():
            missing.append("parent_page_id")
        if not self.user_name.strip():
            missing.append("user_name")

        if missing:
            raise ConfigurationError("Missing settings: " + ", ".join(missing))


def app_data_dir() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return app_data_dir() / "config.json"


def load_config(path: Path | None = None) -> AppConfig:
    target = path or config_path()
    if not target.exists():
        return AppConfig()

    data = json.loads(target.read_text(encoding="utf-8"))
    known_keys = {field.name for field in AppConfig.__dataclass_fields__.values()}
    return AppConfig(**{key: value for key, value in data.items() if key in known_keys})


def save_config(config: AppConfig, path: Path | None = None) -> None:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_session_cookies(account: str) -> str | None:
    keyring = _load_keyring()
    return keyring.get_password(COOKIE_SERVICE, account)


def set_session_cookies(account: str, cookies_json: str) -> None:
    if not account.strip():
        raise ConfigurationError("Login account is required before saving browser session cookies.")
    if not cookies_json.strip():
        return
    keyring = _load_keyring()
    keyring.set_password(COOKIE_SERVICE, account, cookies_json)


def _load_keyring():
    try:
        import keyring
    except ImportError as exc:
        raise ConfigurationError("Install keyring to store the Confluence login session.") from exc
    return keyring
