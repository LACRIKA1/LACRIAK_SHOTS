from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizeGrip,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.capture import CaptureError, CaptureResult, CaptureService, wait_for_ui_to_hide
from core.config import AppSettings, default_hotkeys, load_settings, save_settings
from core.editor import ImageEditorWindow
from core.hotkeys import (
    MOUSE_4,
    MOUSE_5,
    MOUSE_LEFT,
    MOUSE_MIDDLE,
    MOUSE_RIGHT,
    MOUSE_WHEEL_DOWN,
    MOUSE_WHEEL_UP,
    HotkeyManager,
    hotkey_from_codes,
    normalize_hotkey,
    normalize_vk,
)
from core.recorder import RecorderThread
from core.storage import CaptureRecord, HistoryStore
from core.ui import AnimatedButton, ToastWidget, WindowTitleBar, app_icon
from core.windows import WindowInfo, active_window, activate_window, list_open_windows, window_under_cursor


ACTION_LABELS = {
    "fullscreen": "Весь экран",
    "region": "Область",
    "active_window": "Активное окно",
    "record_mp4": "Запись MP4",
    "record_gif": "Запись GIF",
}


class HotkeyCaptureDialog(QDialog):
    def __init__(self, current: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Запись горячей клавиши")
        self.setModal(True)
        self.setMinimumWidth(430)
        self._codes: set[int] = set()
        self.result_text = normalize_hotkey(current) or current

        layout = QVBoxLayout(self)
        title = QLabel("Нажмите новую комбинацию")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        hint = QLabel("Поддерживаются обычные клавиши и сочетания: Page Up, C+V, Ctrl+Page Up, Shift+F9.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.value_label = QLabel(self.result_text or "Ожидание ввода...")
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setMinimumHeight(56)
        self.value_label.setStyleSheet(
            "background:#101113;border:1px solid #ff4d2e;border-radius:8px;font-size:20px;font-weight:800;"
        )
        layout.addWidget(self.value_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _capture_key_event(self, event) -> bool:
        if event.isAutoRepeat():
            return True
        vk = self._event_vk(event)
        if vk:
            self._codes.add(vk)
            text = hotkey_from_codes(self._codes)
            if text:
                self.result_text = text
                self.value_label.setText(text)
            event.accept()
            return True
        return False

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if self._capture_key_event(event):
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self._capture_key_event(event):
            return
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        code = {
            Qt.LeftButton: MOUSE_LEFT,
            Qt.RightButton: MOUSE_RIGHT,
            Qt.MiddleButton: MOUSE_MIDDLE,
            Qt.XButton1: MOUSE_4,
            Qt.XButton2: MOUSE_5,
        }.get(event.button())
        if code:
            self._codes.add(code)
            text = hotkey_from_codes(self._codes)
            if text:
                self.result_text = text
                self.value_label.setText(text)
            event.accept()
            return
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        self._codes.add(MOUSE_WHEEL_UP if event.angleDelta().y() > 0 else MOUSE_WHEEL_DOWN)
        text = hotkey_from_codes(self._codes)
        if text:
            self.result_text = text
            self.value_label.setText(text)
        event.accept()

    @staticmethod
    def _event_vk(event) -> int | None:
        native = int(event.nativeVirtualKey()) if hasattr(event, "nativeVirtualKey") else 0
        if native:
            return normalize_vk(native)
        qt_map = {
            Qt.Key_PageUp: 0x21,
            Qt.Key_PageDown: 0x22,
            Qt.Key_Home: 0x24,
            Qt.Key_End: 0x23,
            Qt.Key_Insert: 0x2D,
            Qt.Key_Delete: 0x2E,
            Qt.Key_Print: 0x2C,
            Qt.Key_Escape: 0x1B,
            Qt.Key_Tab: 0x09,
            Qt.Key_Return: 0x0D,
            Qt.Key_Enter: 0x0D,
            Qt.Key_Space: 0x20,
            Qt.Key_Control: 0x11,
            Qt.Key_Shift: 0x10,
            Qt.Key_Alt: 0x12,
        }
        key = event.key()
        if key in qt_map:
            return qt_map[key]
        if Qt.Key_A <= key <= Qt.Key_Z:
            return 0x41 + int(key - Qt.Key_A)
        if Qt.Key_0 <= key <= Qt.Key_9:
            return 0x30 + int(key - Qt.Key_0)
        if Qt.Key_F1 <= key <= Qt.Key_F24:
            return 0x70 + int(key - Qt.Key_F1)
        return None


class CaptureOverlay(QWidget):
    selected = Signal(dict)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self._start = QPoint()
        self._end = QPoint()
        self._selecting = False

        desktop_rect = QRect()
        for screen in QApplication.screens():
            desktop_rect = desktop_rect.united(screen.geometry())
        self.setGeometry(desktop_rect)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.LeftButton:
            return
        self._start = event.position().toPoint()
        self._end = self._start
        self._selecting = True
        self.update()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if not self._selecting:
            return
        self._end = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.LeftButton or not self._selecting:
            return
        self._selecting = False
        self._end = event.position().toPoint()
        rect = QRect(self._start, self._end).normalized()
        if rect.width() < 4 or rect.height() < 4:
            self.cancelled.emit()
            self.close()
            return

        top_left = self.mapToGlobal(rect.topLeft())
        monitor = {
            "left": top_left.x(),
            "top": top_left.y(),
            "width": rect.width(),
            "height": rect.height(),
        }
        self.hide()
        QTimer.singleShot(80, lambda: self.selected.emit(monitor))
        QTimer.singleShot(120, self.close)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.close()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
        if self._selecting:
            rect = QRect(self._start, self._end).normalized()
            painter.setPen(QPen(QColor("#2f9e44"), 2))
            painter.setBrush(QColor(47, 158, 68, 45))
            painter.drawRect(rect)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(rect.adjusted(8, 8, -8, -8), f"{rect.width()} x {rect.height()}")
        painter.end()


class StopRecordingWidget(QWidget):
    def __init__(self, stop_callback) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        button = QPushButton("Остановить запись")
        button.clicked.connect(stop_callback)
        button.setMinimumHeight(42)
        button.setStyleSheet(
            """
            QPushButton {
                background: #c92a2a;
                color: white;
                border: 0;
                border-radius: 6px;
                font-weight: 600;
                padding: 8px 18px;
            }
            QPushButton:hover { background: #e03131; }
            QPushButton:disabled { background: #666; }
            """
        )
        layout.addWidget(button)
        self.button = button

        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(screen.right() - self.width() - 24, screen.top() + 24)


class ShareXAnalogWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        self.capture_service = CaptureService(self.settings)
        self.history_store = HistoryStore()
        self.history_records = self.history_store.load()
        self.hotkeys = HotkeyManager()
        self.hotkeys.action_requested.connect(self.handle_hotkey)
        self.hotkeys.status_changed.connect(self.set_hotkey_status)

        self.overlay: CaptureOverlay | None = None
        self.recorder: RecorderThread | None = None
        self.stop_widget: StopRecordingWidget | None = None
        self.editor_windows: list[ImageEditorWindow] = []
        self._restore_after_overlay = True
        self._restore_after_recording = True
        self._force_quit = False
        self._auto_busy = False
        self._auto_remaining = 0

        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self.auto_capture_tick)

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle("ShareX Analog - отечественный аналог ShareX")
        self.setWindowIcon(app_icon())
        self.setMenuWidget(WindowTitleBar(self, "ShareX Analog", "SX"))
        self.resize(1180, 760)
        self.setMinimumSize(980, 620)
        self.build_ui()
        self.apply_styles()
        self.statusBar().addPermanentWidget(QSizeGrip(self), 0)
        self.toast = ToastWidget(self)
        self.toast.hide()
        self.refresh_history()
        self.load_settings_to_form()
        self.build_tray()
        self.hotkeys.start(self.settings)
        self.statusBar().showMessage("Готово.")

    def build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        self.nav = QListWidget()
        self.nav.setFixedWidth(235)
        self.nav.setFrameShape(QFrame.NoFrame)
        self.nav.setFocusPolicy(Qt.NoFocus)
        for text in [
            "Панель захвата",
            "История",
            "Автозахват",
            "Горячие клавиши",
            "Настройки",
            "О программе",
        ]:
            item = QListWidgetItem(text)
            item.setSizeHint(QSize(210, 42))
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self.change_page)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.build_capture_page())
        self.stack.addWidget(self.build_history_page())
        self.stack.addWidget(self.build_auto_page())
        self.stack.addWidget(self.build_hotkeys_page())
        self.stack.addWidget(self.build_settings_page())
        self.stack.addWidget(self.build_about_page())

        root.addWidget(self.nav)
        root.addWidget(self.stack, 1)
        self.nav.setCurrentRow(0)

    def build_capture_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        title = QLabel("Панель захвата")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Локальный инструмент для скриншотов, записи экрана и быстрой передачи результата в буфер обмена."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        group = QGroupBox("Основные действия")
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        grid.addWidget(self.action_button("Весь экран", self.capture_fullscreen), 0, 0)
        grid.addWidget(self.action_button("Выделить область", self.capture_region), 0, 1)
        grid.addWidget(self.action_button("Активное окно", lambda: self.capture_active_window(delayed=True)), 0, 2)
        grid.addWidget(self.window_tool_button(), 1, 0)
        grid.addWidget(self.monitor_tool_button(), 1, 1)
        grid.addWidget(self.action_button("Объект под курсором", self.capture_object_under_cursor), 1, 2)
        grid.addWidget(self.action_button("Запись MP4", lambda: self.start_recording("mp4")), 2, 0)
        grid.addWidget(self.action_button("Запись GIF", lambda: self.start_recording("gif")), 2, 1)
        self.stop_record_button = self.action_button("Остановить запись", self.stop_recording)
        self.stop_record_button.setEnabled(False)
        grid.addWidget(self.stop_record_button, 2, 2)
        layout.addWidget(group)

        info_group = QGroupBox("Текущая маршрутизация")
        info_layout = QFormLayout(info_group)
        self.save_dir_label = QLabel()
        self.template_label = QLabel()
        self.clipboard_label = QLabel()
        for label in [self.save_dir_label, self.template_label, self.clipboard_label]:
            label.setWordWrap(True)
        info_layout.addRow("Папка:", self.save_dir_label)
        info_layout.addRow("Шаблон:", self.template_label)
        info_layout.addRow("После захвата:", self.clipboard_label)

        open_folder = QPushButton("Открыть папку сохранения")
        open_folder.clicked.connect(self.open_save_dir)
        info_layout.addRow("", open_folder)
        layout.addWidget(info_group)
        layout.addStretch(1)
        self.update_route_labels()
        return page

    def build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("История локальных файлов")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(["Дата", "Тип", "Размер", "Источник", "Файл"])
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.itemSelectionChanged.connect(self.update_preview)
        self.history_table.doubleClicked.connect(self.open_selected_file)
        left_layout.addWidget(self.history_table)

        controls = QHBoxLayout()
        for label, slot in [
            ("Открыть", self.open_selected_file),
            ("Редактировать", self.edit_selected_file),
            ("Копировать", self.copy_selected_image),
            ("Удалить", self.delete_selected_record),
            ("Убрать пропавшие", self.remove_missing_records),
        ]:
            button = QPushButton(label)
            button.clicked.connect(slot)
            controls.addWidget(button)
        controls.addStretch(1)
        left_layout.addLayout(controls)

        preview_box = QGroupBox("Предпросмотр")
        preview_layout = QVBoxLayout(preview_box)
        self.preview_label = QLabel("Выберите файл в истории.")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumWidth(300)
        self.preview_label.setWordWrap(True)
        preview_layout.addWidget(self.preview_label, 1)

        splitter.addWidget(left)
        splitter.addWidget(preview_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        return page

    def build_auto_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Автозахват")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        group = QGroupBox("Периодическое документирование экрана")
        form = QFormLayout(group)
        self.auto_interval = QSpinBox()
        self.auto_interval.setRange(1, 3600)
        self.auto_interval.setValue(10)
        self.auto_interval.setSuffix(" с")

        self.auto_count = QSpinBox()
        self.auto_count.setRange(0, 10000)
        self.auto_count.setValue(5)
        self.auto_count.setSpecialValueText("без ограничения")

        self.auto_mode = QComboBox()
        self.auto_mode.addItem("Весь экран", "full")
        self.auto_mode.addItem("Активное окно", "active")

        form.addRow("Интервал:", self.auto_interval)
        form.addRow("Количество:", self.auto_count)
        form.addRow("Режим:", self.auto_mode)

        buttons = QHBoxLayout()
        self.auto_start_button = QPushButton("Старт")
        self.auto_start_button.clicked.connect(self.start_auto_capture)
        self.auto_stop_button = QPushButton("Стоп")
        self.auto_stop_button.clicked.connect(self.stop_auto_capture)
        self.auto_stop_button.setEnabled(False)
        buttons.addWidget(self.auto_start_button)
        buttons.addWidget(self.auto_stop_button)
        buttons.addStretch(1)
        form.addRow("", buttons)

        self.auto_status = QLabel("Автозахват остановлен.")
        self.auto_status.setObjectName("Muted")
        form.addRow("Состояние:", self.auto_status)
        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def build_hotkeys_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("Горячие клавиши")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        self.hotkey_status = QLabel()
        self.hotkey_status.setObjectName("Muted")
        layout.addWidget(self.hotkey_status)

        hint = QLabel(
            "Можно вводить сочетания через плюс: Page Up, C+V, Ctrl+Page Up, Shift+F9. "
            "Комбинации с обычными клавишами работают через низкоуровневый обработчик Windows."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.hotkey_table = QTableWidget(len(default_hotkeys()), 2)
        self.hotkey_table.setHorizontalHeaderLabels(["Действие", "Комбинация"])
        self.hotkey_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.hotkey_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.hotkey_table.verticalHeader().setVisible(False)
        layout.addWidget(self.hotkey_table)

        buttons = QHBoxLayout()
        save = QPushButton("Сохранить горячие клавиши")
        save.clicked.connect(self.save_hotkeys_from_table)
        record = QPushButton("Записать выбранный бинд")
        record.clicked.connect(self.record_selected_hotkey)
        clear = QPushButton("Очистить выбранный")
        clear.clicked.connect(self.clear_selected_hotkey)
        restart = QPushButton("Перезапустить обработчик")
        restart.clicked.connect(lambda: self.hotkeys.start(self.settings))
        reset = QPushButton("Вернуть бинды по умолчанию")
        reset.clicked.connect(self.reset_hotkeys)
        buttons.addWidget(save)
        buttons.addWidget(record)
        buttons.addWidget(clear)
        buttons.addWidget(restart)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.populate_hotkey_table()
        return page

    def build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Настройки")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        group = QGroupBox("Сохранение и обработка")
        form = QFormLayout(group)

        path_row = QHBoxLayout()
        self.save_dir_edit = QLineEdit()
        browse = QPushButton("Выбрать")
        browse.clicked.connect(self.choose_save_dir)
        path_row.addWidget(self.save_dir_edit, 1)
        path_row.addWidget(browse)

        self.template_edit = QLineEdit()
        self.format_combo = QComboBox()
        for fmt in ["png", "jpg", "bmp"]:
            self.format_combo.addItem(fmt.upper(), fmt)

        self.copy_check = QCheckBox("Копировать изображение в буфер обмена")
        self.edit_after_check = QCheckBox("Открывать редактор после скриншота")
        self.hide_check = QCheckBox("Скрывать главное окно перед захватом")
        self.hotkeys_check = QCheckBox("Включить глобальные горячие клавиши")

        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 5000)
        self.delay_spin.setSingleStep(50)
        self.delay_spin.setSuffix(" мс")

        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 60)
        self.fps_spin.setSuffix(" fps")

        self.gif_ms_spin = QSpinBox()
        self.gif_ms_spin.setRange(50, 1000)
        self.gif_ms_spin.setSingleStep(10)
        self.gif_ms_spin.setSuffix(" мс")

        form.addRow("Папка сохранения:", path_row)
        form.addRow("Шаблон имени:", self.template_edit)
        form.addRow("Формат скриншотов:", self.format_combo)
        form.addRow("Задержка перед снимком:", self.delay_spin)
        form.addRow("Частота MP4:", self.fps_spin)
        form.addRow("Интервал GIF:", self.gif_ms_spin)
        form.addRow("", self.copy_check)
        form.addRow("", self.edit_after_check)
        form.addRow("", self.hide_check)
        form.addRow("", self.hotkeys_check)

        buttons = QHBoxLayout()
        save = QPushButton("Сохранить настройки")
        save.clicked.connect(self.save_settings_from_form)
        reset = QPushButton("Вернуть стандартные")
        reset.clicked.connect(self.reset_settings)
        buttons.addWidget(save)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        form.addRow("", buttons)
        layout.addWidget(group)

        hint = QLabel(
            "Доступные поля шаблона: {type}, {date}, {time}, {datetime}, {window}, "
            "{year}, {month}, {day}, {hour}, {minute}, {second}."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def build_about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("О программе")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        text = QLabel(
            "ShareX Analog реализует требования задания ВКР: модульный локальный комплекс "
            "для захвата экрана, выделения областей через оверлей, работы с активными окнами "
            "и мониторами, глобальных горячих клавиш, шаблонов именования файлов, конвейера "
            "после захвата и встроенного редактора аннотаций. Приложение работает по принципу "
            "offline-first: файлы сохраняются локально, а результат передается в системный "
            "буфер обмена без обращения к облачным сервисам."
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        layout.addStretch(1)
        return page

    def action_button(self, text: str, slot) -> QPushButton:
        button = AnimatedButton(text)
        button.clicked.connect(slot)
        button.setMinimumHeight(54)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return button

    def window_tool_button(self) -> QToolButton:
        button = QToolButton()
        button.setText("Выбрать окно")
        button.setPopupMode(QToolButton.InstantPopup)
        button.setMinimumHeight(54)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.window_menu = QMenu(button)
        self.window_menu.aboutToShow.connect(self.populate_window_menu)
        button.setMenu(self.window_menu)
        return button

    def monitor_tool_button(self) -> QToolButton:
        button = QToolButton()
        button.setText("Выбрать монитор")
        button.setPopupMode(QToolButton.InstantPopup)
        button.setMinimumHeight(54)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.monitor_menu = QMenu(button)
        self.monitor_menu.aboutToShow.connect(self.populate_monitor_menu)
        button.setMenu(self.monitor_menu)
        return button

    def build_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        menu = QMenu()
        show_action = QAction("Показать", self)
        show_action.triggered.connect(self.show_from_tray)
        quit_action = QAction("Выход", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_from_tray() if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    def change_page(self, index: int) -> None:
        self.stack.setCurrentIndex(max(0, index))

    def update_route_labels(self) -> None:
        self.save_dir_label.setText(self.settings.save_dir)
        self.template_label.setText(self.settings.filename_template)
        actions = ["локальное сохранение"]
        if self.settings.copy_to_clipboard:
            actions.append("копирование в буфер")
        if self.settings.open_editor_after_capture:
            actions.append("открытие редактора")
        self.clipboard_label.setText(", ".join(actions))

    def populate_window_menu(self) -> None:
        self.window_menu.clear()
        own = {int(self.winId())}
        windows = list_open_windows(exclude_hwnds=own)
        if not windows:
            self.window_menu.addAction("Окна не найдены").setEnabled(False)
            return
        for info in windows[:40]:
            title = info.title if len(info.title) <= 80 else info.title[:77] + "..."
            action = self.window_menu.addAction(title)
            action.triggered.connect(lambda _checked=False, win=info: self.capture_selected_window(win))

    def populate_monitor_menu(self) -> None:
        self.monitor_menu.clear()
        try:
            monitors = self.capture_service.available_monitors()
        except Exception as exc:
            self.monitor_menu.addAction(f"Ошибка: {exc}").setEnabled(False)
            return
        if len(monitors) <= 1:
            self.monitor_menu.addAction("Мониторы не найдены").setEnabled(False)
            return
        for index, monitor in enumerate(monitors[1:], 1):
            text = f"{index}: {monitor['width']} x {monitor['height']}"
            action = self.monitor_menu.addAction(text)
            action.triggered.connect(
                lambda _checked=False, mon=monitor, idx=index: self.capture_monitor(mon, idx)
            )

    def run_hidden(self, callback, restore: bool | None = None) -> None:
        restore_window = self.isVisible() if restore is None else restore
        if self.settings.hide_main_window and self.isVisible():
            self.hide()
        QApplication.processEvents()

        def wrapped() -> None:
            try:
                result = callback()
                if isinstance(result, CaptureResult):
                    self.handle_capture_result(result)
            except Exception as exc:
                self.show_error(str(exc))
            finally:
                if restore_window:
                    self.show_from_tray(raise_window=False)

        QTimer.singleShot(self.settings.screenshot_delay_ms, wrapped)

    def capture_fullscreen(self) -> None:
        self.show_action_toast("Захват: весь экран")
        self.run_hidden(self.capture_service.capture_all)

    def capture_monitor(self, monitor: dict[str, int], index: int) -> None:
        self.show_action_toast(f"Захват: монитор {index}")
        self.run_hidden(lambda: self.capture_service.capture_monitor(monitor, index))

    def capture_region(self) -> None:
        self.show_action_toast("Захват: выделение области")
        self._restore_after_overlay = self.isVisible()
        if self.settings.hide_main_window and self.isVisible():
            self.hide()
        QApplication.processEvents()
        QTimer.singleShot(100, self.show_overlay)

    def show_overlay(self) -> None:
        self.overlay = CaptureOverlay()
        self.overlay.selected.connect(self.finish_region_capture)
        self.overlay.cancelled.connect(self.restore_after_overlay)
        self.overlay.show()

    def finish_region_capture(self, monitor: dict) -> None:
        try:
            wait_for_ui_to_hide(100)
            result = self.capture_service.capture_rect(monitor, "region", "selected-region")
            self.handle_capture_result(result)
        except Exception as exc:
            self.show_error(str(exc))
        finally:
            self.restore_after_overlay()

    def restore_after_overlay(self) -> None:
        if self._restore_after_overlay:
            self.show_from_tray(raise_window=False)

    def capture_selected_window(self, info: WindowInfo) -> None:
        self.show_action_toast("Захват: выбранное окно")
        restore_window = self.isVisible()
        if self.isVisible():
            self.hide()
        activate_window(info.hwnd)
        QApplication.processEvents()

        def do_capture() -> None:
            try:
                current = active_window()
                target = current if current and current.hwnd == info.hwnd else info
                result = self.capture_service.capture_window(target.monitor, target.title)
                self.handle_capture_result(result)
            except Exception as exc:
                self.show_error(str(exc))
            finally:
                if restore_window:
                    self.show_from_tray(raise_window=False)

        QTimer.singleShot(max(500, self.settings.screenshot_delay_ms), do_capture)

    def capture_active_window(self, delayed: bool = False) -> None:
        self.show_action_toast("Захват: активное окно")
        restore_window = self.isVisible()
        if delayed and self.isVisible():
            self.statusBar().showMessage("Активируйте нужное окно: снимок будет сделан через 1.5 секунды.")
            self.hide()
            delay = 1500
        else:
            delay = self.settings.screenshot_delay_ms

        def do_capture() -> None:
            try:
                info = active_window()
                if info is None:
                    raise CaptureError("Активное окно не найдено.")
                if info.hwnd == int(self.winId()):
                    raise CaptureError("Сначала активируйте окно, которое нужно захватить.")
                result = self.capture_service.capture_window(info.monitor, info.title)
                self.handle_capture_result(result)
            except Exception as exc:
                self.show_error(str(exc))
            finally:
                if restore_window:
                    self.show_from_tray(raise_window=False)

        QTimer.singleShot(delay, do_capture)

    def capture_object_under_cursor(self) -> None:
        self.show_action_toast("Захват: объект под курсором")
        restore_window = self.isVisible()
        if self.isVisible():
            self.statusBar().showMessage("Наведите курсор на нужный объект: снимок будет сделан через 1.5 секунды.")
            self.hide()

        def do_capture() -> None:
            try:
                info = window_under_cursor()
                if info is None:
                    raise CaptureError("Объект под курсором не найден.")
                result = self.capture_service.capture_window(info.monitor, info.title or "cursor-object")
                self.handle_capture_result(result)
            except Exception as exc:
                self.show_error(str(exc))
            finally:
                if restore_window:
                    self.show_from_tray(raise_window=False)

        QTimer.singleShot(1500, do_capture)

    def handle_capture_result(self, result: CaptureResult) -> None:
        record = CaptureRecord.create(
            path=result.path,
            kind=result.kind,
            width=result.width,
            height=result.height,
            source_title=result.source_title,
            copied_to_clipboard=result.copied_to_clipboard,
        )
        self.history_records = self.history_store.add(record)
        self.refresh_history()
        copied = " и скопирован в буфер" if result.copied_to_clipboard else ""
        self.statusBar().showMessage(f"Файл сохранен{copied}: {result.path}", 6000)
        if self.settings.open_editor_after_capture and result.path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}:
            self.open_editor(result.path)

    def start_recording(self, mode: str) -> None:
        if self.recorder and self.recorder.isRunning():
            self.statusBar().showMessage("Запись уже идет.")
            return
        self.show_action_toast("Запись: MP4" if mode == "mp4" else "Запись: GIF")
        self._restore_after_recording = self.isVisible()
        if self.settings.hide_main_window and self.isVisible():
            self.hide()
        QApplication.processEvents()

        def start() -> None:
            self.recorder = RecorderThread(self.settings, mode=mode)
            self.recorder.finished_recording.connect(self.recording_finished)
            self.recorder.failed.connect(self.recording_failed)
            self.recorder.status.connect(lambda text: self.statusBar().showMessage(text))
            self.recorder.start()
            self.stop_record_button.setEnabled(True)
            self.stop_widget = StopRecordingWidget(self.stop_recording)
            self.stop_widget.show()

        QTimer.singleShot(self.settings.screenshot_delay_ms, start)

    def stop_recording(self) -> None:
        if not self.recorder or not self.recorder.isRunning():
            return
        self.show_action_toast("Запись останавливается")
        if self.stop_widget:
            self.stop_widget.button.setEnabled(False)
        self.statusBar().showMessage("Остановка записи...")
        self.recorder.stop()

    def recording_finished(self, data: dict) -> None:
        path = Path(data["path"])
        record = CaptureRecord.create(
            path=path,
            kind=str(data.get("kind", "video")),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            source_title=str(data.get("source_title", "")),
            note=f"frames={data.get('frames', 0)}",
        )
        self.history_records = self.history_store.add(record)
        self.refresh_history()
        self.stop_record_button.setEnabled(False)
        if self.stop_widget:
            self.stop_widget.close()
            self.stop_widget = None
        if self._restore_after_recording:
            self.show_from_tray(raise_window=False)
        self.statusBar().showMessage(f"Запись сохранена: {path}", 6000)

    def recording_failed(self, message: str) -> None:
        self.stop_record_button.setEnabled(False)
        if self.stop_widget:
            self.stop_widget.close()
            self.stop_widget = None
        if self._restore_after_recording:
            self.show_from_tray(raise_window=False)
        self.show_error(f"Ошибка записи: {message}")

    def start_auto_capture(self) -> None:
        self._auto_remaining = self.auto_count.value()
        self.auto_timer.start(self.auto_interval.value() * 1000)
        self.auto_start_button.setEnabled(False)
        self.auto_stop_button.setEnabled(True)
        self.auto_status.setText("Автозахват запущен.")
        self.auto_capture_tick()

    def stop_auto_capture(self) -> None:
        self.auto_timer.stop()
        self._auto_busy = False
        self.auto_start_button.setEnabled(True)
        self.auto_stop_button.setEnabled(False)
        self.auto_status.setText("Автозахват остановлен.")

    def auto_capture_tick(self) -> None:
        if self._auto_busy:
            return
        if self._auto_remaining == 0 and self.auto_count.value() != 0:
            self.stop_auto_capture()
            return
        self._auto_busy = True
        mode = self.auto_mode.currentData()
        restore_window = self.isVisible()
        if self.settings.hide_main_window and self.isVisible():
            self.hide()
            QApplication.processEvents()

        def capture() -> CaptureResult:
            if mode == "active":
                info = active_window()
                if info is None or info.hwnd == int(self.winId()):
                    return self.capture_service.capture_all()
                return self.capture_service.capture_window(info.monitor, info.title)
            return self.capture_service.capture_all()

        def done() -> None:
            try:
                result = capture()
                self.handle_capture_result(result)
                if self.auto_count.value() != 0:
                    self._auto_remaining -= 1
                left = "без ограничения" if self.auto_count.value() == 0 else str(max(0, self._auto_remaining))
                self.auto_status.setText(f"Автозахват активен. Осталось: {left}.")
            except Exception as exc:
                self.auto_status.setText(f"Ошибка: {exc}")
            finally:
                if restore_window:
                    self.show_from_tray(raise_window=False)
                self._auto_busy = False

        QTimer.singleShot(self.settings.screenshot_delay_ms, done)

    def refresh_history(self) -> None:
        self.history_records = self.history_store.load()
        self.history_table.setRowCount(len(self.history_records))
        for row, record in enumerate(self.history_records):
            size = f"{record.width} x {record.height}" if record.width and record.height else "-"
            values = [
                record.created_at.replace("T", " "),
                record.kind,
                size,
                record.source_title or "-",
                Path(record.path).name,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, record.path)
                self.history_table.setItem(row, col, item)
        self.history_table.resizeRowsToContents()
        self.update_preview()

    def selected_record(self) -> CaptureRecord | None:
        row = self.history_table.currentRow()
        if row < 0 or row >= len(self.history_records):
            return None
        return self.history_records[row]

    def update_preview(self) -> None:
        record = self.selected_record()
        if record is None:
            self.preview_label.setText("Выберите файл в истории.")
            self.preview_label.setPixmap(QPixmap())
            return
        path = Path(record.path)
        if not path.exists():
            self.preview_label.setText("Файл отсутствует на диске.")
            self.preview_label.setPixmap(QPixmap())
            return
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp"}:
            self.preview_label.setText(f"{path.name}\n\nПредпросмотр доступен только для изображений.")
            self.preview_label.setPixmap(QPixmap())
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.preview_label.setText("Не удалось открыть изображение.")
            return
        self.preview_label.setPixmap(pixmap.scaled(360, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def open_selected_file(self) -> None:
        record = self.selected_record()
        if record:
            self.open_path(Path(record.path))

    def edit_selected_file(self) -> None:
        record = self.selected_record()
        if not record:
            return
        path = Path(record.path)
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp"}:
            self.show_error("Редактор доступен только для изображений.")
            return
        self.open_editor(path)

    def copy_selected_image(self) -> None:
        record = self.selected_record()
        if not record:
            return
        path = Path(record.path)
        if not path.exists():
            self.show_error("Файл отсутствует на диске.")
            return
        if not self.capture_service.copy_image_to_clipboard(path):
            self.show_error("Не удалось скопировать файл как изображение.")
            return
        self.statusBar().showMessage("Изображение скопировано в буфер обмена.", 3000)

    def delete_selected_record(self) -> None:
        record = self.selected_record()
        if not record:
            return
        path = Path(record.path)
        answer = QMessageBox.question(
            self,
            "Удалить запись",
            f"Удалить запись истории и файл?\n{path}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.history_records = [item for item in self.history_records if item.path != record.path]
        if path.exists():
            try:
                path.unlink()
            except OSError as exc:
                self.show_error(str(exc))
        self.history_store.save(self.history_records)
        self.refresh_history()

    def remove_missing_records(self) -> None:
        self.history_records = [record for record in self.history_records if Path(record.path).exists()]
        self.history_store.save(self.history_records)
        self.refresh_history()

    def open_editor(self, path: Path) -> None:
        if not path.exists():
            self.show_error("Файл отсутствует на диске.")
            return
        try:
            editor = ImageEditorWindow(path)
        except Exception as exc:
            self.show_error(str(exc))
            return
        editor.saved.connect(lambda _path: self.update_preview())
        editor.destroyed.connect(lambda _obj=None, win=editor: self.forget_editor(win))
        self.editor_windows.append(editor)
        editor.show()

    def forget_editor(self, editor: ImageEditorWindow) -> None:
        if editor in self.editor_windows:
            self.editor_windows.remove(editor)

    def open_path(self, path: Path) -> None:
        if not path.exists():
            self.show_error("Файл отсутствует на диске.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_save_dir(self) -> None:
        path = Path(self.settings.save_dir)
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def choose_save_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Папка сохранения", self.save_dir_edit.text())
        if directory:
            self.save_dir_edit.setText(directory)

    def load_settings_to_form(self) -> None:
        self.save_dir_edit.setText(self.settings.save_dir)
        self.template_edit.setText(self.settings.filename_template)
        index = self.format_combo.findData(self.settings.image_format.lower())
        self.format_combo.setCurrentIndex(max(0, index))
        self.copy_check.setChecked(self.settings.copy_to_clipboard)
        self.edit_after_check.setChecked(self.settings.open_editor_after_capture)
        self.hide_check.setChecked(self.settings.hide_main_window)
        self.hotkeys_check.setChecked(self.settings.hotkeys_enabled)
        self.delay_spin.setValue(self.settings.screenshot_delay_ms)
        self.fps_spin.setValue(self.settings.recording_fps)
        self.gif_ms_spin.setValue(self.settings.gif_frame_ms)
        self.populate_hotkey_table()

    def save_settings_from_form(self) -> None:
        self.settings.save_dir = self.save_dir_edit.text().strip() or self.settings.save_dir
        self.settings.filename_template = self.template_edit.text().strip() or "{type}_{date}_{time}_{window}"
        self.settings.image_format = self.format_combo.currentData()
        self.settings.copy_to_clipboard = self.copy_check.isChecked()
        self.settings.open_editor_after_capture = self.edit_after_check.isChecked()
        self.settings.hide_main_window = self.hide_check.isChecked()
        self.settings.hotkeys_enabled = self.hotkeys_check.isChecked()
        self.settings.screenshot_delay_ms = self.delay_spin.value()
        self.settings.recording_fps = self.fps_spin.value()
        self.settings.gif_frame_ms = self.gif_ms_spin.value()
        save_settings(self.settings)
        self.capture_service.update_settings(self.settings)
        self.hotkeys.start(self.settings)
        self.update_route_labels()
        self.statusBar().showMessage("Настройки сохранены.", 3000)

    def reset_settings(self) -> None:
        self.settings = AppSettings()
        save_settings(self.settings)
        self.capture_service.update_settings(self.settings)
        self.load_settings_to_form()
        self.update_route_labels()
        self.hotkeys.start(self.settings)

    def populate_hotkey_table(self) -> None:
        if not hasattr(self, "hotkey_table"):
            return
        hotkeys = self.settings.hotkeys
        for row, action in enumerate(default_hotkeys().keys()):
            action_item = QTableWidgetItem(ACTION_LABELS.get(action, action))
            action_item.setData(Qt.UserRole, action)
            action_item.setFlags(action_item.flags() & ~Qt.ItemIsEditable)
            key_item = QTableWidgetItem(hotkeys.get(action, ""))
            key_item.setToolTip("Примеры: Page Up, C+V, Ctrl+Page Up, Shift+F9")
            self.hotkey_table.setItem(row, 0, action_item)
            self.hotkey_table.setItem(row, 1, key_item)

    def save_hotkeys_from_table(self) -> None:
        values = {}
        invalid = []
        combo_owner = {}
        for row in range(self.hotkey_table.rowCount()):
            action_item = self.hotkey_table.item(row, 0)
            key_item = self.hotkey_table.item(row, 1)
            if action_item is None:
                continue
            action = action_item.data(Qt.UserRole)
            raw = key_item.text().strip() if key_item else ""
            if not raw:
                values[action] = ""
                continue
            normalized = normalize_hotkey(raw)
            if normalized is None:
                invalid.append(raw or ACTION_LABELS.get(action, action))
                continue
            previous_action = combo_owner.get(normalized)
            if previous_action:
                values[previous_action] = ""
            values[action] = normalized
            combo_owner[normalized] = action
        if invalid:
            self.show_error("Некорректные сочетания: " + ", ".join(invalid))
            return
        self.settings.hotkeys.update(values)
        save_settings(self.settings)
        self.populate_hotkey_table()
        self.hotkeys.start(self.settings)
        self.statusBar().showMessage("Горячие клавиши сохранены.", 3000)

    def record_selected_hotkey(self) -> None:
        row = self.hotkey_table.currentRow()
        if row < 0:
            self.show_error("Сначала выберите строку с действием.")
            return
        key_item = self.hotkey_table.item(row, 1)
        current = key_item.text().strip() if key_item else ""

        self.hotkeys.stop()
        dialog = HotkeyCaptureDialog(current, self)
        if dialog.exec() == QDialog.Accepted:
            normalized = normalize_hotkey(dialog.result_text)
            if normalized:
                self.set_hotkey_row_value(row, normalized)
        self.hotkeys.start(self.settings)

    def clear_selected_hotkey(self) -> None:
        row = self.hotkey_table.currentRow()
        if row < 0:
            self.show_error("Сначала выберите строку с действием.")
            return
        item = self.hotkey_table.item(row, 1)
        if item is None:
            item = QTableWidgetItem()
            self.hotkey_table.setItem(row, 1, item)
        item.setText("")

    def set_hotkey_row_value(self, row: int, value: str) -> None:
        for other_row in range(self.hotkey_table.rowCount()):
            if other_row == row:
                continue
            other_item = self.hotkey_table.item(other_row, 1)
            other_value = normalize_hotkey(other_item.text().strip()) if other_item else None
            if other_value == value:
                if other_item is None:
                    other_item = QTableWidgetItem()
                    self.hotkey_table.setItem(other_row, 1, other_item)
                other_item.setText("")

        key_item = self.hotkey_table.item(row, 1)
        if key_item is None:
            key_item = QTableWidgetItem()
            self.hotkey_table.setItem(row, 1, key_item)
        key_item.setText(value)

    def reset_hotkeys(self) -> None:
        self.settings.hotkeys = default_hotkeys()
        save_settings(self.settings)
        self.populate_hotkey_table()
        self.hotkeys.start(self.settings)
        self.statusBar().showMessage("Горячие клавиши возвращены к стандартным.", 3000)

    def handle_hotkey(self, action: str) -> None:
        if action == "fullscreen":
            self.capture_fullscreen()
        elif action == "region":
            self.capture_region()
        elif action == "active_window":
            self.capture_active_window(delayed=False)
        elif action == "record_mp4":
            self.toggle_recording("mp4")
        elif action == "record_gif":
            self.toggle_recording("gif")

    def toggle_recording(self, mode: str) -> None:
        if self.recorder and self.recorder.isRunning():
            self.stop_recording()
        else:
            self.start_recording(mode)

    def set_hotkey_status(self, text: str) -> None:
        if hasattr(self, "hotkey_status"):
            self.hotkey_status.setText(text)
        self.statusBar().showMessage(text, 4000)

    def show_from_tray(self, raise_window: bool = True) -> None:
        self.show()
        if raise_window:
            self.raise_()
            self.activateWindow()

    def quit_app(self) -> None:
        self._force_quit = True
        self.close()
        QApplication.quit()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._force_quit:
            self.hotkeys.stop()
            if self.recorder and self.recorder.isRunning():
                self.recorder.stop()
                self.recorder.wait(2000)
            event.accept()
            return
        if self.tray.isVisible():
            self.hide()
            event.ignore()
            self.statusBar().showMessage("Приложение свернуто в трей. Горячие клавиши продолжают работать.")
            return
        event.accept()

    def show_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 6000)
        QMessageBox.warning(self, "Ошибка", message)

    def show_action_toast(self, message: str) -> None:
        if hasattr(self, "toast") and self.isVisible():
            self.toast.show_message(message)

    def apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #191b1f;
                color: #f5f7fa;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }
            QWidget#WindowTitleBar {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #101113, stop:0.58 #17191d, stop:1 #241b18);
                border-bottom: 1px solid #343a40;
            }
            QLabel#TitleLogo {
                background: #ff4d2e;
                color: white;
                border-radius: 7px;
                font-weight: 900;
            }
            QLabel#TitleText {
                color: #f8f9fa;
                font-size: 14px;
                font-weight: 700;
            }
            QToolButton#TitleButton, QToolButton#TitleCloseButton {
                background: transparent;
                border: 0;
                border-radius: 6px;
                color: #cfd4da;
                font-weight: 700;
            }
            QToolButton#TitleButton:hover, QToolButton#TitleCloseButton:hover {
                background: #2b3036;
                color: white;
            }
            QToolButton#TitleCloseButton:hover {
                background: #e03131;
                color: white;
            }
            QListWidget {
                background: #101113;
                border: 0;
                outline: 0;
                padding: 14px 10px;
            }
            QListWidget::item {
                border-radius: 8px;
                border: 0;
                outline: 0;
                padding-left: 12px;
                color: #d8dee6;
            }
            QListWidget::item:focus {
                border: 0;
                outline: 0;
            }
            QListWidget::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff4d2e, stop:1 #b62f1d);
                color: #ffffff;
            }
            QListWidget::item:hover {
                background: #252a30;
                color: #ffffff;
            }
            QLabel#PageTitle {
                font-size: 25px;
                font-weight: 800;
                color: #ffffff;
            }
            QLabel#Muted {
                color: #adb5bd;
            }
            QGroupBox {
                background: #1f2227;
                border: 1px solid #3c424a;
                border-radius: 8px;
                margin-top: 18px;
                padding: 16px;
                font-weight: 700;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #ffffff;
            }
            QPushButton, QToolButton {
                background: #282d32;
                border: 1px solid #46505a;
                border-radius: 7px;
                color: #f1f3f5;
                padding: 8px 12px;
                font-weight: 600;
            }
            QPushButton:hover, QToolButton:hover {
                background: #343139;
                border-color: #ff4d2e;
            }
            QPushButton:pressed, QToolButton:pressed {
                background: #17191d;
                border-color: #ff6b4a;
            }
            QPushButton:disabled {
                color: #868e96;
                background: #24272b;
            }
            QLineEdit, QSpinBox, QComboBox {
                background: #101113;
                border: 1px solid #454b50;
                border-radius: 6px;
                padding: 6px;
                selection-background-color: #ff4d2e;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border-color: #ff4d2e;
            }
            QTableWidget {
                background: #16181c;
                border: 1px solid #343a40;
                gridline-color: #343a40;
                selection-background-color: #b62f1d;
            }
            QHeaderView::section {
                background: #101113;
                color: #f1f3f5;
                border: 0;
                border-right: 1px solid #343a40;
                border-bottom: 1px solid #343a40;
                padding: 8px;
            }
            QMenu {
                background: #15171a;
                color: #f1f3f5;
                border: 1px solid #343a40;
                border-radius: 6px;
            }
            QMenu::item {
                padding: 7px 28px;
            }
            QMenu::item:selected {
                background: #ff4d2e;
            }
            QStatusBar {
                background: #101113;
                color: #ced4da;
                border-top: 1px solid #343a40;
            }
            QWidget#ToastWidget {
                background: rgba(16, 17, 19, 226);
                border: 1px solid #ff5a36;
                border-radius: 12px;
            }
            QLabel#ToastText {
                color: #ffffff;
                font-weight: 800;
                font-size: 13px;
            }
            """
        )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ShareX Analog")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    window = ShareXAnalogWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
