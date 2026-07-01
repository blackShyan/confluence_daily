from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import sys
import traceback
from urllib.parse import urlparse

from .autostart import set_autostart
from .config import (
    AppConfig,
    app_data_dir,
    get_session_cookies,
    load_config,
    save_config,
    set_session_cookies,
)
from .confluence_client import ConfluenceClient
from .models import ConfigurationError, DailyEntryConflict, DailyInput
from .state import DailyState
from .uploader import DailyUploader


IMAGE_PREVIEW_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}


def app_icon_path() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "confluence_daily" / "assets" / "app_icon.ico"
    return Path(__file__).resolve().parent / "assets" / "app_icon.ico"


def main() -> int:
    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is required. Install dependencies with: pip install -e .")
        return 1

    app = QApplication(sys.argv)
    app.setApplicationName("컨플루언스 데일리 업로더")
    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setQuitOnLastWindowClosed(False)
    controller = MainController(app)
    controller.start()
    return app.exec()


class MainController:
    def __init__(self, app) -> None:
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon

        self.app = app
        self.config = load_config()
        _apply_app_theme(self.app, self.config.effective_theme_mode)
        self.state = DailyState()
        self.daily_dialog = None
        self.settings_dialog = None
        self.reminder_dialog = None

        self.tray = QSystemTrayIcon(self._build_icon(), app)
        self.tray.setToolTip("컨플루언스 데일리 업로더")
        self.menu = QMenu()

        self.write_action = QAction("데일리 작성", self.menu)
        self.write_action.triggered.connect(self.show_daily_dialog)
        self.status_action = QAction("오늘 업로드 상태", self.menu)
        self.status_action.triggered.connect(self.show_today_status)
        self.settings_action = QAction("설정", self.menu)
        self.settings_action.triggered.connect(self.show_settings_dialog)
        self.snooze_action = QAction("10분 뒤 다시 알림", self.menu)
        self.snooze_action.triggered.connect(self.snooze_today)
        self.complete_action = QAction("오늘 완료 처리", self.menu)
        self.complete_action.triggered.connect(self.complete_today)
        self.quit_action = QAction("종료", self.menu)
        self.quit_action.triggered.connect(app.quit)

        for action in (
            self.write_action,
            self.status_action,
            self.settings_action,
            self.snooze_action,
            self.complete_action,
        ):
            self.menu.addAction(action)
        self.menu.addSeparator()
        self.menu.addAction(self.quit_action)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)

        self.timer = QTimer()
        self.timer.setInterval(60_000)
        self.timer.timeout.connect(self.check_reminder)

    def start(self) -> None:
        self.tray.show()
        self.timer.start()
        if not self.config.base_url:
            self.show_settings_dialog()
        elif self.config.is_data_center and not get_session_cookies(self.config.credential_account):
            self.show_login_dialog()
        self.check_reminder()

    def show_daily_dialog(self) -> None:
        self.daily_dialog = DailyDialog(self)
        self.daily_dialog.show()
        self.daily_dialog.raise_()
        self.daily_dialog.activateWindow()

    def show_settings_dialog(self) -> None:
        self.settings_dialog = SettingsDialog(self)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def show_today_status(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        today = date.today()
        if self.state.is_uploaded(today):
            QMessageBox.information(None, "오늘 업로드 상태", "오늘 데일리는 이미 업로드되었습니다.")
        elif self.state.is_completed_without_upload(today):
            QMessageBox.information(None, "오늘 업로드 상태", "오늘은 완료 처리되어 알림을 멈췄습니다.")
        else:
            QMessageBox.information(None, "오늘 업로드 상태", "아직 오늘 데일리가 업로드되지 않았습니다.")

    def upload_daily(self, daily: DailyInput, conflict_policy: str = "cancel"):
        cookies = get_session_cookies(self.config.credential_account)
        if not cookies:
            self.show_login_dialog()
            raise ConfigurationError("컨플루언스 로그인이 필요합니다. 로그인 후 세션을 저장하고 다시 업로드해 주세요.")

        uploader = DailyUploader(self.config, session_cookies=cookies, state=self.state)
        return uploader.upload(daily, conflict_policy)

    def show_login_dialog(self) -> None:
        self.login_dialog = BrowserLoginDialog(self.config)
        self.login_dialog.show()

    def reload_config(self) -> None:
        self.config = load_config()
        _apply_app_theme(self.app, self.config.effective_theme_mode)

    def check_reminder(self) -> None:
        now = datetime.now()
        today = now.date()
        if today.weekday() >= 5:
            return
        if self.state.is_uploaded(today) or self.state.is_completed_without_upload(today):
            return

        snooze_until = self.state.snooze_until(today)
        if snooze_until and now < snooze_until:
            return

        reminder_time = _parse_time(self.config.reminder_time)
        if now.time().replace(second=0, microsecond=0) < reminder_time:
            return

        last_notified = self.state.last_notified_at(today)
        if last_notified and last_notified.date() == today and not snooze_until:
            return

        self.state.mark_notified(today)
        self.tray.showMessage("데일리 알림", "오늘 데일리를 Confluence에 올릴 시간입니다.")
        self.show_reminder_dialog()

    def show_reminder_dialog(self) -> None:
        self.reminder_dialog = ReminderDialog(self)
        self.reminder_dialog.show()
        self.reminder_dialog.raise_()
        self.reminder_dialog.activateWindow()

    def snooze_today(self) -> None:
        self.state.set_snooze_until(date.today(), datetime.now() + timedelta(minutes=10))
        self.tray.showMessage("데일리 알림", "10분 뒤 다시 알려드릴게요.")

    def complete_today(self) -> None:
        self.state.mark_completed_without_upload(date.today())
        self.tray.showMessage("데일리 알림", "오늘 알림을 완료 처리했습니다.")

    def _build_icon(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

        icon_path = app_icon_path()
        if icon_path.exists():
            return QIcon(str(icon_path))

        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#2f6df6"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(6, 6, 52, 52, 12, 12)
        painter.setPen(QColor("white"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(22)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "D")
        painter.end()
        return QIcon(pixmap)

    def _on_tray_activated(self, reason) -> None:
        from PySide6.QtWidgets import QSystemTrayIcon

        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_daily_dialog()


class DailyDialog:
    def __init__(self, controller: MainController) -> None:
        from PySide6.QtCore import QDate, Qt
        from PySide6.QtGui import QKeySequence, QShortcut
        from PySide6.QtWidgets import (
            QDateEdit,
            QDialog,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QPushButton,
            QTextEdit,
            QVBoxLayout,
        )

        class DropDialog(QDialog):
            def __init__(self, owner: DailyDialog) -> None:
                super().__init__()
                self.owner = owner
                self.setAcceptDrops(True)

            def dragEnterEvent(self, event) -> None:
                self.owner.handle_drag_enter(event)

            def dragMoveEvent(self, event) -> None:
                self.owner.handle_drag_enter(event)

            def dropEvent(self, event) -> None:
                self.owner.handle_drop(event)

        class DropFileList(QListWidget):
            def __init__(self, owner: DailyDialog) -> None:
                super().__init__()
                self.owner = owner
                self.setAcceptDrops(True)

            def dragEnterEvent(self, event) -> None:
                self.owner.handle_drag_enter(event)

            def dragMoveEvent(self, event) -> None:
                self.owner.handle_drag_enter(event)

            def dropEvent(self, event) -> None:
                self.owner.handle_drop(event)

        self.controller = controller
        self.dialog = DropDialog(self)
        self.dialog.setWindowTitle("데일리 작성")
        self.dialog.resize(560, 520)

        layout = QVBoxLayout(self.dialog)
        layout.setSpacing(12)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        layout.addWidget(QLabel("날짜"))
        layout.addWidget(self.date_edit)

        layout.addWidget(QLabel("캡처/녹화 파일"))
        self.file_list = DropFileList(self)
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.setToolTip("파일을 드래그 앤 드랍하거나 Ctrl+V로 붙여넣을 수 있습니다.")
        layout.addWidget(self.file_list, 1)

        file_buttons = QHBoxLayout()
        self.add_button = QPushButton("파일 추가")
        self.clipboard_button = QPushButton("클립보드 이미지 추가")
        self.remove_button = QPushButton("선택 제거")
        file_buttons.addWidget(self.add_button)
        file_buttons.addWidget(self.clipboard_button)
        file_buttons.addWidget(self.remove_button)
        file_buttons.addStretch(1)
        layout.addLayout(file_buttons)

        layout.addWidget(QLabel("이미지 프리뷰"))
        self.preview_label = QLabel("이미지 파일을 선택하거나 클립보드 이미지를 추가하면 여기 표시됩니다.")
        self.preview_label.setObjectName("imagePreview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(180)
        self.preview_label.setMaximumHeight(220)
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        layout.addWidget(QLabel("참고 comment"))
        self.comment_edit = QTextEdit()
        self.comment_edit.setPlaceholderText("오늘 한 일을 적어주세요.")
        layout.addWidget(self.comment_edit, 1)

        bottom = QHBoxLayout()
        self.upload_button = QPushButton("업로드")
        self.close_button = QPushButton("닫기")
        bottom.addStretch(1)
        bottom.addWidget(self.upload_button)
        bottom.addWidget(self.close_button)
        layout.addLayout(bottom)

        self.add_button.clicked.connect(self.add_files)
        self.clipboard_button.clicked.connect(self.add_clipboard_image)
        self.remove_button.clicked.connect(self.remove_selected_files)
        self.file_list.currentItemChanged.connect(self.update_file_preview)
        self.upload_button.clicked.connect(self.upload)
        self.close_button.clicked.connect(self.dialog.close)
        self.paste_shortcut = QShortcut(QKeySequence.StandardKey.Paste, self.dialog)
        self.paste_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.paste_shortcut.activated.connect(self.paste_from_clipboard)
        self._apply_style()

    def show(self) -> None:
        self.dialog.show()

    def raise_(self) -> None:
        self.dialog.raise_()

    def activateWindow(self) -> None:
        self.dialog.activateWindow()

    def add_files(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        files, _ = QFileDialog.getOpenFileNames(
            self.dialog,
            "캡처/녹화 파일 선택",
            "",
            "Media files (*.png *.jpg *.jpeg *.webp *.gif *.mp4 *.mov *.mkv *.avi *.wmv);;All files (*.*)",
        )
        self.add_file_paths([Path(file_name) for file_name in files])

    def add_file_paths(self, paths: list[Path] | tuple[Path, ...]) -> bool:
        existing = {self.file_list.item(index).text() for index in range(self.file_list.count())}
        last_added_row = None
        for path in paths:
            if not path.exists() or not path.is_file():
                continue

            file_name = str(path)
            if file_name in existing:
                continue

            self.file_list.addItem(file_name)
            existing.add(file_name)
            last_added_row = self.file_list.count() - 1

        if last_added_row is not None:
            self.file_list.setCurrentRow(last_added_row)
            return True
        return False

    def add_clipboard_image(self) -> None:
        self.add_clipboard_content(prefer_files=False, show_warning=True)

    def paste_from_clipboard(self) -> None:
        from PySide6.QtWidgets import QApplication

        if self.add_clipboard_content(prefer_files=True, show_warning=False):
            return

        focused = QApplication.focusWidget()
        paste = getattr(focused, "paste", None)
        if callable(paste):
            paste()

    def add_clipboard_content(self, prefer_files: bool, show_warning: bool) -> bool:
        from PySide6.QtWidgets import QApplication, QMessageBox

        clipboard = QApplication.clipboard()
        if prefer_files and self.add_file_paths(self._file_paths_from_mime_data(clipboard.mimeData())):
            return True

        image = clipboard.image()
        if image.isNull():
            pixmap = clipboard.pixmap()
            if not pixmap.isNull():
                image = pixmap.toImage()

        if image.isNull():
            if show_warning:
                QMessageBox.warning(self.dialog, "클립보드 이미지 없음", "클립보드에 복사된 이미지가 없습니다.")
            return False

        target_dir = app_data_dir() / "clipboard_images"
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"clipboard_{datetime.now():%Y%m%d_%H%M%S_%f}.png"
        if not image.save(str(file_path), "PNG"):
            QMessageBox.critical(self.dialog, "이미지 저장 실패", "클립보드 이미지를 PNG 파일로 저장하지 못했습니다.")
            return False

        existing = {self.file_list.item(index).text() for index in range(self.file_list.count())}
        if str(file_path) not in existing:
            self.file_list.addItem(str(file_path))
            self.file_list.setCurrentRow(self.file_list.count() - 1)
        else:
            for index in range(self.file_list.count()):
                if self.file_list.item(index).text() == str(file_path):
                    self.file_list.setCurrentRow(index)
                    break
        return True

    def handle_drag_enter(self, event) -> None:
        if self._file_paths_from_mime_data(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def handle_drop(self, event) -> None:
        if self.add_file_paths(self._file_paths_from_mime_data(event.mimeData())):
            event.acceptProposedAction()
            return
        event.ignore()

    def _file_paths_from_mime_data(self, mime_data) -> list[Path]:
        if mime_data is None or not mime_data.hasUrls():
            return []

        paths = []
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.exists() and path.is_file():
                paths.append(path)
        return paths

    def remove_selected_files(self) -> None:
        for item in self.file_list.selectedItems():
            row = self.file_list.row(item)
            self.file_list.takeItem(row)
        self.update_file_preview()

    def update_file_preview(self, current=None, previous=None) -> None:
        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import Qt

        item = current or self.file_list.currentItem()
        if item is None:
            self._set_preview_message("이미지 파일을 선택하거나 클립보드 이미지를 추가하면 여기 표시됩니다.")
            return

        path = Path(item.text())
        if path.suffix.lower() not in IMAGE_PREVIEW_EXTENSIONS:
            self._set_preview_message("선택한 항목은 이미지 미리보기를 지원하지 않습니다.")
            return
        if not path.exists():
            self._set_preview_message("선택한 이미지 파일을 찾을 수 없습니다.")
            return

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._set_preview_message("이미지 미리보기를 불러오지 못했습니다.")
            return

        target_width = max(320, self.preview_label.width() - 16)
        target_height = max(140, self.preview_label.height() - 16)
        scaled = pixmap.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setText("")
        self.preview_label.setPixmap(scaled)

    def _set_preview_message(self, message: str) -> None:
        from PySide6.QtGui import QPixmap

        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText(message)

    def upload(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox

        file_paths = tuple(Path(self.file_list.item(index).text()) for index in range(self.file_list.count()))
        if not file_paths:
            QMessageBox.warning(self.dialog, "파일 필요", "캡처 또는 녹화 파일을 하나 이상 선택해 주세요.")
            return

        work_date = self.date_edit.date().toPython()
        if work_date.weekday() >= 5:
            QMessageBox.warning(self.dialog, "평일만 지원", "데일리 표는 월요일부터 금요일까지만 지원합니다.")
            return

        daily = DailyInput(
            work_date=work_date,
            file_paths=file_paths,
            comment=self.comment_edit.toPlainText().strip(),
        )

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.upload_button.setEnabled(False)
        try:
            result = self.controller.upload_daily(daily, "cancel")
        except DailyEntryConflict:
            QApplication.restoreOverrideCursor()
            self.upload_button.setEnabled(True)
            choice = QMessageBox.question(
                self.dialog,
                "기존 내용 발견",
                "해당 날짜 행에 이미 내용이 있습니다. 기존 내용 뒤에 추가할까요?\n\n'아니오'를 누르면 덮어씁니다.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            if choice == QMessageBox.StandardButton.Cancel:
                return
            policy = "append" if choice == QMessageBox.StandardButton.Yes else "overwrite"
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.upload_button.setEnabled(False)
            try:
                result = self.controller.upload_daily(daily, policy)
            except Exception as exc:
                self._show_error(exc)
                return
            finally:
                QApplication.restoreOverrideCursor()
                self.upload_button.setEnabled(True)
        except Exception as exc:
            if "401" in str(exc):
                self.controller.show_login_dialog()
            self._show_error(exc)
            return
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
            self.upload_button.setEnabled(True)

        link_text = f"\n\n{result.page_url}" if result.page_url else ""
        QMessageBox.information(self.dialog, "업로드 완료", f"{result.page_title}에 업로드했습니다.{link_text}")
        self.dialog.close()

    def _show_error(self, exc: Exception) -> None:
        from PySide6.QtWidgets import QMessageBox

        details = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        QMessageBox.critical(self.dialog, "업로드 실패", details)

    def _apply_style(self) -> None:
        self.dialog.setStyleSheet(_app_style(self.controller.config.effective_theme_mode))
        self.upload_button.setObjectName("primary")
        self.upload_button.setDefault(True)


class SettingsDialog:
    def __init__(self, controller: MainController) -> None:
        from PySide6.QtCore import QTime
        from PySide6.QtWidgets import (
            QButtonGroup,
            QCheckBox,
            QComboBox,
            QDialog,
            QFormLayout,
            QHBoxLayout,
            QLineEdit,
            QPushButton,
            QRadioButton,
            QTimeEdit,
            QVBoxLayout,
            QWidget,
        )

        self.controller = controller
        config = controller.config
        self.original_theme_mode = config.effective_theme_mode
        self.current_theme_mode = self.original_theme_mode
        self.theme_committed = False
        self.dialog = QDialog()
        self.dialog.setWindowTitle("설정")
        self.dialog.resize(560, 430)

        outer = QVBoxLayout(self.dialog)
        form = QFormLayout()
        form.setSpacing(10)

        self.api_mode = QComboBox()
        self.api_mode.addItem("Confluence Cloud", "cloud")
        self.api_mode.addItem("Confluence Data Center / Server", "data_center")
        mode_index = self.api_mode.findData(config.api_mode)
        self.api_mode.setCurrentIndex(max(mode_index, 0))
        self.base_url = QLineEdit(config.base_url)
        self.email = QLineEdit(config.email)
        self.space = QLineEdit(config.effective_space_key if config.is_data_center else config.space_id)
        self.parent_page_id = QLineEdit(config.parent_page_id)
        self.user_name = QLineEdit(config.user_name)
        self.month_page_policy = QComboBox()
        self.month_page_policy.addItem("월~금 주차가 끝나는 월 페이지", "workweek_end_month")
        self.month_page_policy.addItem("선택한 날짜의 월 페이지", "date_month")
        policy_index = self.month_page_policy.findData(config.month_page_policy)
        self.month_page_policy.setCurrentIndex(max(policy_index, 0))
        self.theme_group = QButtonGroup(self.dialog)
        self.light_theme = QRadioButton("라이트 모드")
        self.dark_theme = QRadioButton("다크 모드")
        self.theme_group.addButton(self.light_theme)
        self.theme_group.addButton(self.dark_theme)
        self.light_theme.setProperty("themeMode", "light")
        self.dark_theme.setProperty("themeMode", "dark")
        if self.current_theme_mode == "dark":
            self.dark_theme.setChecked(True)
        else:
            self.light_theme.setChecked(True)
        theme_row = QWidget()
        theme_layout = QHBoxLayout(theme_row)
        theme_layout.setContentsMargins(0, 0, 0, 0)
        theme_layout.addWidget(self.light_theme)
        theme_layout.addWidget(self.dark_theme)
        theme_layout.addStretch(1)
        self.reminder_time = QTimeEdit()
        parsed_time = _parse_time(config.reminder_time)
        self.reminder_time.setTime(QTime(parsed_time.hour, parsed_time.minute))
        self.autostart = QCheckBox("Windows 시작 시 자동 실행")
        self.autostart.setChecked(config.autostart)

        form.addRow("API 모드", self.api_mode)
        form.addRow("Confluence URL", self.base_url)
        form.addRow("로그인 계정", self.email)
        form.addRow("Space ID / key", self.space)
        form.addRow("상위 페이지 ID", self.parent_page_id)
        form.addRow("페이지 이름", self.user_name)
        form.addRow("월 페이지 기준", self.month_page_policy)
        form.addRow("화면 테마", theme_row)
        form.addRow("알림 시간", self.reminder_time)
        form.addRow("", self.autostart)
        outer.addLayout(form)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.login_button = QPushButton("로그인")
        self.test_button = QPushButton("세션 테스트")
        self.save_button = QPushButton("저장")
        self.cancel_button = QPushButton("취소")
        bottom.addWidget(self.login_button)
        bottom.addWidget(self.test_button)
        bottom.addWidget(self.save_button)
        bottom.addWidget(self.cancel_button)
        outer.addLayout(bottom)

        self.login_button.clicked.connect(self.login_with_browser)
        self.test_button.clicked.connect(self.test_connection)
        self.save_button.clicked.connect(self.save)
        self.cancel_button.clicked.connect(self.cancel)
        self.theme_group.buttonToggled.connect(self._theme_button_toggled)
        self.dialog.finished.connect(self._restore_unsaved_theme)
        self._apply_style()

    def show(self) -> None:
        self.dialog.show()

    def raise_(self) -> None:
        self.dialog.raise_()

    def activateWindow(self) -> None:
        self.dialog.activateWindow()

    def save(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        config = self._build_config()
        try:
            save_config(config)
            set_autostart(config.autostart)
        except Exception as exc:
            QMessageBox.critical(self.dialog, "설정 저장 실패", str(exc))
            return

        self.theme_committed = True
        self.controller.reload_config()
        QMessageBox.information(self.dialog, "설정 저장", "설정을 저장했습니다.")
        self.dialog.close()

    def cancel(self) -> None:
        self._restore_unsaved_theme()
        self.dialog.close()

    def test_connection(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox

        config = self._build_config()
        cookies = get_session_cookies(config.credential_account)
        if not cookies:
            QMessageBox.warning(self.dialog, "로그인 필요", "먼저 로그인 버튼을 누른 뒤 브라우저 세션을 저장해 주세요.")
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.test_button.setEnabled(False)
        try:
            config.validate_for_upload()
            page = ConfluenceClient(config, session_cookies=cookies).get_page(config.parent_page_id)
        except Exception as exc:
            QMessageBox.critical(self.dialog, "연결 실패", str(exc))
        else:
            QMessageBox.information(
                self.dialog,
                "연결 성공",
                f"페이지에 연결했습니다.\n\n{page.page_id}: {page.title}",
            )
        finally:
            QApplication.restoreOverrideCursor()
            self.test_button.setEnabled(True)

    def login_with_browser(self) -> None:
        config = self._build_config()
        try:
            config.validate_for_upload()
            save_config(config)
            self.theme_committed = True
            self.controller.reload_config()
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self.dialog, "설정 필요", str(exc))
            return

        self.controller.show_login_dialog()

    def _build_config(self) -> AppConfig:
        reminder = self.reminder_time.time()
        api_mode = self.api_mode.currentData()
        space_value = self.space.text().strip()
        return AppConfig(
            base_url=self.base_url.text().strip(),
            email=self.email.text().strip(),
            api_mode=api_mode,
            space_id="" if api_mode == "data_center" else space_value,
            space_key=space_value if api_mode == "data_center" else "",
            parent_page_id=self.parent_page_id.text().strip(),
            user_name=self.user_name.text().strip() or "\uc0ac\uc6a9\uc790",
            month_page_policy=self.month_page_policy.currentData(),
            reminder_time=f"{reminder.hour():02d}:{reminder.minute():02d}",
            timezone="Asia/Seoul",
            autostart=self.autostart.isChecked(),
            theme_mode=self.current_theme_mode,
        )

    def _theme_button_toggled(self, button, checked: bool) -> None:
        if not checked:
            return

        mode = button.property("themeMode")
        if mode not in {"light", "dark"}:
            return

        self.current_theme_mode = mode
        _apply_app_theme(self.controller.app, mode)
        self._apply_style()

    def _restore_unsaved_theme(self, *_args) -> None:
        if self.theme_committed:
            return
        if self.controller.config.effective_theme_mode != self.current_theme_mode:
            _apply_app_theme(self.controller.app, self.controller.config.effective_theme_mode)

    def _apply_style(self) -> None:
        self.dialog.setStyleSheet(_app_style(self.current_theme_mode))


class ReminderDialog:
    def __init__(self, controller: MainController) -> None:
        from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

        self.controller = controller
        self.dialog = QDialog()
        self.dialog.setWindowTitle("데일리 알림")
        self.dialog.resize(380, 160)

        layout = QVBoxLayout(self.dialog)
        label = QLabel("오늘 데일리를 Confluence에 올릴 시간입니다.")
        label.setWordWrap(True)
        layout.addWidget(label)

        buttons = QHBoxLayout()
        self.write_button = QPushButton("작성하기")
        self.snooze_button = QPushButton("10분 뒤")
        self.done_button = QPushButton("오늘 완료")
        buttons.addWidget(self.write_button)
        buttons.addWidget(self.snooze_button)
        buttons.addWidget(self.done_button)
        layout.addLayout(buttons)

        self.write_button.clicked.connect(self._write)
        self.snooze_button.clicked.connect(self._snooze)
        self.done_button.clicked.connect(self._done)
        self.dialog.setStyleSheet(_app_style(self.controller.config.effective_theme_mode))

    def show(self) -> None:
        self.dialog.show()

    def raise_(self) -> None:
        self.dialog.raise_()

    def activateWindow(self) -> None:
        self.dialog.activateWindow()

    def _write(self) -> None:
        self.dialog.close()
        self.controller.show_daily_dialog()

    def _snooze(self) -> None:
        self.controller.snooze_today()
        self.dialog.close()

    def _done(self) -> None:
        self.controller.complete_today()
        self.dialog.close()


class BrowserLoginDialog:
    def __init__(self, config: AppConfig, parent=None) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtWebEngineCore import QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

        self.config = config
        self.cookies: dict[tuple[str, str, str], dict[str, str]] = {}
        self.base_host = urlparse(config.base_url).hostname or ""
        self.dialog = QDialog(parent)
        self.dialog.setWindowTitle("Confluence 로그인")
        self.dialog.resize(1080, 760)

        layout = QVBoxLayout(self.dialog)
        self.status_label = QLabel("회사 SSO로 로그인한 뒤 Confluence 페이지가 열리면 아래의 '세션 저장'을 눌러주세요.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.view = QWebEngineView()
        profile = QWebEngineProfile.defaultProfile()
        self.cookie_store = profile.cookieStore()
        self.cookie_store.cookieAdded.connect(self._on_cookie_added)
        if hasattr(self.cookie_store, "loadAllCookies"):
            self.cookie_store.loadAllCookies()
        self.view.setPage(self.view.page())
        layout.addWidget(self.view, 1)

        buttons = QHBoxLayout()
        self.save_button = QPushButton("세션 저장")
        self.close_button = QPushButton("닫기")
        buttons.addStretch(1)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.save_button.clicked.connect(self.save_session)
        self.close_button.clicked.connect(self.dialog.close)
        self.dialog.setStyleSheet(_app_style(self.config.effective_theme_mode))

        login_url = f"{config.base_url.rstrip('/')}/pages/viewpage.action?pageId={config.parent_page_id}"
        self.view.urlChanged.connect(self._on_url_changed)
        self.view.setUrl(QUrl(login_url))

    def show(self) -> None:
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def _on_cookie_added(self, cookie) -> None:
        name = bytes(cookie.name()).decode("utf-8", errors="replace")
        value = bytes(cookie.value()).decode("utf-8", errors="replace")
        domain = cookie.domain() or self.base_host
        path = cookie.path() or "/"
        if not name:
            return
        if self._cookie_can_auth_confluence(domain):
            self.cookies[(name, domain, path)] = {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
            }

    def _cookie_can_auth_confluence(self, domain: str) -> bool:
        if not self.base_host:
            return True
        if not domain:
            return True
        normalized = domain.lstrip(".").lower()
        base_host = self.base_host.lower()
        return base_host == normalized or base_host.endswith("." + normalized) or normalized.endswith("." + base_host)

    def _on_url_changed(self, url) -> None:
        url = str(url.toString())
        host = urlparse(url).hostname or ""
        if host.lower() == self.base_host.lower() and "/Login" not in url and "nxsaml" not in url:
            self.status_label.setText("Confluence 페이지가 열렸습니다. 로그인 상태라면 '세션 저장'을 눌러주세요.")
        else:
            self.status_label.setText("회사 SSO 로그인을 진행해 주세요. 로그인 후 Confluence 페이지로 돌아오면 세션을 저장할 수 있습니다.")

    def save_session(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        if self._save_session(show_message=True):
            self.dialog.close()

    def _save_session(self, show_message: bool) -> bool:
        from PySide6.QtWidgets import QMessageBox

        cookies = list(self.cookies.values())
        if not cookies:
            QMessageBox.warning(
                self.dialog,
                "세션 없음",
                "아직 Confluence 세션 쿠키가 감지되지 않았습니다. 로그인을 완료하고 Confluence 페이지가 열린 뒤 다시 저장해 주세요.",
            )
            return False

        try:
            set_session_cookies(self.config.credential_account, json.dumps(cookies, ensure_ascii=False))
        except Exception as exc:
            QMessageBox.critical(self.dialog, "세션 저장 실패", str(exc))
            return False

        if show_message:
            QMessageBox.information(
                self.dialog,
                "세션 저장",
                f"Confluence API 호출용 브라우저 세션을 저장했습니다.\n저장된 쿠키 수: {len(cookies)}",
            )
        return True


def _parse_time(value: str) -> time:
    try:
        hour_text, minute_text = value.split(":", 1)
        return time(int(hour_text), int(minute_text))
    except Exception:
        return time(18, 0)


def _apply_app_theme(app, theme_mode: str) -> None:
    from PySide6.QtGui import QColor, QPalette

    app.setStyle("Fusion")
    mode = theme_mode if theme_mode in {"light", "dark"} else "light"
    palette = QPalette()

    if mode == "dark":
        colors = {
            QPalette.ColorRole.Window: "#171b22",
            QPalette.ColorRole.WindowText: "#e8edf7",
            QPalette.ColorRole.Base: "#202632",
            QPalette.ColorRole.AlternateBase: "#262e3b",
            QPalette.ColorRole.Text: "#edf2f8",
            QPalette.ColorRole.Button: "#2d3542",
            QPalette.ColorRole.ButtonText: "#edf2f8",
            QPalette.ColorRole.ToolTipBase: "#202632",
            QPalette.ColorRole.ToolTipText: "#edf2f8",
            QPalette.ColorRole.PlaceholderText: "#9ca9bb",
            QPalette.ColorRole.Highlight: "#5b8cff",
            QPalette.ColorRole.HighlightedText: "#ffffff",
        }
    else:
        colors = {
            QPalette.ColorRole.Window: "#f7f8fb",
            QPalette.ColorRole.WindowText: "#172033",
            QPalette.ColorRole.Base: "#ffffff",
            QPalette.ColorRole.AlternateBase: "#eef2f8",
            QPalette.ColorRole.Text: "#172033",
            QPalette.ColorRole.Button: "#e8edf7",
            QPalette.ColorRole.ButtonText: "#172033",
            QPalette.ColorRole.ToolTipBase: "#ffffff",
            QPalette.ColorRole.ToolTipText: "#172033",
            QPalette.ColorRole.PlaceholderText: "#6a7487",
            QPalette.ColorRole.Highlight: "#2f6df6",
            QPalette.ColorRole.HighlightedText: "#ffffff",
        }

    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(_app_style(mode))


def _app_style(theme_mode: str = "light") -> str:
    if theme_mode == "dark":
        return """
            QDialog, QMenu {
                background: #171b22;
                color: #e8edf7;
                font-size: 14px;
            }
            QLabel {
                font-weight: 600;
                color: #e8edf7;
            }
            QLabel#imagePreview {
                background: #202632;
                border: 1px solid #3a4658;
                border-radius: 6px;
                color: #9ca9bb;
                font-weight: 500;
                padding: 8px;
            }
            QDateEdit, QTextEdit, QListWidget, QLineEdit, QTimeEdit, QComboBox {
                background: #202632;
                color: #edf2f8;
                selection-background-color: #5b8cff;
                selection-color: white;
                border: 1px solid #3a4658;
                border-radius: 6px;
                padding: 8px;
            }
            QComboBox QAbstractItemView, QListWidget::item {
                background: #202632;
                color: #edf2f8;
                selection-background-color: #5b8cff;
                selection-color: white;
            }
            QCheckBox, QRadioButton {
                color: #e8edf7;
                spacing: 8px;
            }
            QPushButton {
                background: #2d3542;
                color: #edf2f8;
                border: 1px solid #3a4658;
                border-radius: 6px;
                padding: 8px 14px;
            }
            QPushButton:hover { background: #374253; }
            QPushButton:disabled {
                background: #232a34;
                color: #7f8b9d;
                border-color: #323b4a;
            }
            QPushButton:default, QPushButton#primary {
                background: #5b8cff;
                color: white;
                border-color: #5b8cff;
            }
        """

    return """
        QDialog, QMenu { background: #f7f8fb; color: #172033; font-size: 14px; }
        QLabel { font-weight: 600; color: #22314d; }
        QLabel#imagePreview {
            background: white;
            border: 1px solid #cfd7e6;
            border-radius: 6px;
            color: #6a7487;
            font-weight: 500;
            padding: 8px;
        }
        QDateEdit, QTextEdit, QListWidget, QLineEdit, QTimeEdit, QComboBox {
            background: white;
            color: #172033;
            selection-background-color: #2f6df6;
            selection-color: white;
            border: 1px solid #cfd7e6;
            border-radius: 6px;
            padding: 8px;
        }
        QComboBox QAbstractItemView, QListWidget::item {
            background: white;
            color: #172033;
            selection-background-color: #2f6df6;
            selection-color: white;
        }
        QCheckBox, QRadioButton { color: #22314d; spacing: 8px; }
        QPushButton {
            background: #e8edf7;
            color: #172033;
            border: 1px solid #c8d2e3;
            border-radius: 6px;
            padding: 8px 14px;
        }
        QPushButton:hover { background: #dfe7f4; }
        QPushButton:disabled {
            background: #eef2f8;
            color: #8a95a8;
            border-color: #d8dfeb;
        }
        QPushButton:default, QPushButton#primary {
            background: #2f6df6;
            color: white;
            border-color: #2f6df6;
        }
    """
