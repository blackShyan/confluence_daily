from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from textwrap import dedent

from .config import app_data_dir


APP_EXE_NAME = "ConfluenceDailyUploader.exe"
DISTRIBUTION_FOLDER_NAME = "ConfluenceDailyUploader"
MANIFEST_NAME = "latest.json"


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    source_dir: Path
    manifest_path: Path
    notes: str = ""


def compare_versions(left: str, right: str) -> int:
    left_parts = _version_parts(left)
    right_parts = _version_parts(right)
    max_length = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (max_length - len(left_parts)))
    right_parts.extend([0] * (max_length - len(right_parts)))

    if left_parts > right_parts:
        return 1
    if left_parts < right_parts:
        return -1
    return 0


def find_update(update_source_path: str, current_version: str) -> UpdateInfo | None:
    info = load_update_info(update_source_path)
    if compare_versions(info.version, current_version) <= 0:
        return None
    return info


def load_update_info(update_source_path: str) -> UpdateInfo:
    source_text = update_source_path.strip()
    if not source_text:
        raise UpdateError("업데이트 경로가 설정되지 않았습니다. 설정에서 latest.json이 있는 폴더를 지정해 주세요.")

    source_root = Path(source_text)

    manifest_path = source_root / MANIFEST_NAME
    if not manifest_path.exists():
        raise UpdateError(f"업데이트 manifest를 찾을 수 없습니다: {manifest_path}")

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise UpdateError(f"업데이트 manifest를 읽지 못했습니다: {manifest_path}") from exc

    version = str(payload.get("version", "")).strip()
    if not version:
        raise UpdateError("업데이트 manifest에 version 값이 없습니다.")

    folder_value = str(payload.get("folder") or payload.get("path") or DISTRIBUTION_FOLDER_NAME).strip()
    update_dir = Path(folder_value)
    if not update_dir.is_absolute():
        update_dir = source_root / update_dir
    update_dir = update_dir.resolve()

    exe_path = update_dir / APP_EXE_NAME
    if not exe_path.exists():
        raise UpdateError(f"업데이트 배포 폴더에 exe가 없습니다: {exe_path}")

    return UpdateInfo(
        version=version,
        source_dir=update_dir,
        manifest_path=manifest_path,
        notes=str(payload.get("notes", "")).strip(),
    )


def stage_update(update_info: UpdateInfo, staging_root: Path | None = None) -> Path:
    root = staging_root or app_data_dir() / "updates" / "staged"
    target = root / DISTRIBUTION_FOLDER_NAME
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(update_info.source_dir, target)
    return target


def can_self_update() -> bool:
    return bool(getattr(sys, "frozen", False))


def current_install_dir() -> Path:
    if can_self_update():
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


def launch_update_installer(
    staged_dir: Path,
    install_dir: Path | None = None,
    current_pid: int | None = None,
) -> None:
    target_dir = install_dir or current_install_dir()
    pid = current_pid or os.getpid()
    script_path = app_data_dir() / "updates" / "apply_update.ps1"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(_installer_script(), encoding="utf-8")

    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-ProcessIdToWait",
        str(pid),
        "-Source",
        str(staged_dir),
        "-Target",
        str(target_dir),
        "-ExeName",
        APP_EXE_NAME,
    ]

    subprocess.Popen(
        args,
        creationflags=(
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        ),
    )


def _version_parts(value: str) -> list[int]:
    match = re.match(r"^\s*v?(\d+(?:\.\d+)*)", value)
    if not match:
        raise UpdateError(f"버전 형식이 올바르지 않습니다: {value}")
    return [int(part) for part in match.group(1).split(".")]


def _installer_script() -> str:
    return dedent(
        r"""
        param(
            [Parameter(Mandatory=$true)][int]$ProcessIdToWait,
            [Parameter(Mandatory=$true)][string]$Source,
            [Parameter(Mandatory=$true)][string]$Target,
            [Parameter(Mandatory=$true)][string]$ExeName
        )

        $ErrorActionPreference = "Stop"

        try {
            Wait-Process -Id $ProcessIdToWait -Timeout 60 -ErrorAction SilentlyContinue
        } catch {
        }

        robocopy $Source $Target /MIR /R:5 /W:1 /NFL /NDL /NJH /NJS /NP
        $CopyExitCode = $LASTEXITCODE
        if ($CopyExitCode -gt 7) {
            exit $CopyExitCode
        }

        $ExePath = Join-Path $Target $ExeName
        if (Test-Path -LiteralPath $ExePath) {
            Start-Process -FilePath $ExePath
        }
        """
    ).strip()
