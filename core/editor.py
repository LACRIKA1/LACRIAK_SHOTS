from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSizeGrip,
    QSpinBox,
    QToolBar,
    QWidget,
)
from PySide6.QtWidgets import QApplication

from .ui import WindowTitleBar, app_icon


class EditorCanvas(QWidget):
    changed = Signal()
    zoom_changed = Signal(float)

    def __init__(self, image_path: Path) -> None:
        super().__init__()
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            raise ValueError(f"Не удалось открыть изображение: {image_path}")
        self.image_path = image_path
        self.pixmap = pixmap
        self.tool = "pen"
        self.color = QColor("#e03131")
        self.pen_width = 4
        self.font_size = 22
        self.zoom = 1.0
        self._undo: list[QPixmap] = []
        self._drawing = False
        self._start = QPoint()
        self._last = QPoint()
        self._current = QPoint()
        self.setMouseTracking(True)
        self.update_scaled_size()

    def sizeHint(self) -> QSize:
        return self.scaled_size()

    def scaled_size(self) -> QSize:
        return QSize(
            max(1, int(self.pixmap.width() * self.zoom)),
            max(1, int(self.pixmap.height() * self.zoom)),
        )

    def update_scaled_size(self) -> None:
        size = self.scaled_size()
        self.setMinimumSize(size)
        self.resize(size)
        self.updateGeometry()
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self.zoom = max(0.08, min(5.0, zoom))
        self.update_scaled_size()
        self.zoom_changed.emit(self.zoom)

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom * 1.18)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom / 1.18)

    def reset_zoom(self) -> None:
        self.set_zoom(1.0)

    def fit_zoom(self, viewport_size: QSize) -> None:
        if self.pixmap.isNull():
            return
        available_width = max(1, viewport_size.width() - 24)
        available_height = max(1, viewport_size.height() - 24)
        factor = min(available_width / self.pixmap.width(), available_height / self.pixmap.height())
        self.set_zoom(min(1.0, factor))

    def map_to_image(self, point: QPoint) -> QPoint:
        return QPoint(
            max(0, min(self.pixmap.width() - 1, int(point.x() / self.zoom))),
            max(0, min(self.pixmap.height() - 1, int(point.y() / self.zoom))),
        )

    def set_tool(self, tool: str) -> None:
        self.tool = tool

    def set_color(self, color: QColor) -> None:
        if color.isValid():
            self.color = color

    def set_width(self, width: int) -> None:
        self.pen_width = max(1, width)

    def undo(self) -> None:
        if not self._undo:
            return
        self.pixmap = self._undo.pop()
        self.update()
        self.changed.emit()

    def save(self, path: Path | None = None) -> Path:
        target = path or self.image_path
        if not self.pixmap.save(str(target)):
            raise OSError(f"Не удалось сохранить файл: {target}")
        self.image_path = target
        return target

    def copy_to_clipboard(self) -> None:
        QApplication.clipboard().setPixmap(self.pixmap)

    def _push_undo(self) -> None:
        self._undo.append(QPixmap(self.pixmap))
        if len(self._undo) > 30:
            self._undo.pop(0)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.LeftButton:
            return
        point = self.map_to_image(event.position().toPoint())
        if not QRect(QPoint(0, 0), self.pixmap.size()).contains(point):
            return

        if self.tool == "text":
            text, ok = QInputDialog.getText(self, "Текст", "Введите подпись:")
            if ok and text:
                self._push_undo()
                painter = QPainter(self.pixmap)
                painter.setPen(QPen(self.color, self.pen_width))
                font = QFont("Segoe UI", self.font_size)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(point, text)
                painter.end()
                self.update()
                self.changed.emit()
            return

        self._push_undo()
        self._drawing = True
        self._start = point
        self._last = point
        self._current = point

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if not self._drawing:
            return
        point = self.map_to_image(event.position().toPoint())
        if self.tool == "pen":
            painter = QPainter(self.pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(self.color, self.pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(self._last, point)
            painter.end()
            self._last = point
            self.changed.emit()
        self._current = point
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.LeftButton or not self._drawing:
            return
        self._drawing = False
        self._current = self.map_to_image(event.position().toPoint())
        if self.tool != "pen":
            painter = QPainter(self.pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            self._draw_shape(painter, self._start, self._current)
            painter.end()
            self.changed.emit()
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.scale(self.zoom, self.zoom)
        painter.drawPixmap(0, 0, self.pixmap)
        if self._drawing and self.tool != "pen":
            painter.setRenderHint(QPainter.Antialiasing)
            self._draw_shape(painter, self._start, self._current, preview=True)
        painter.end()

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if event.modifiers() & Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def _draw_shape(
        self,
        painter: QPainter,
        start: QPoint,
        end: QPoint,
        preview: bool = False,
    ) -> None:
        color = QColor(self.color)
        if preview:
            color.setAlpha(180)
        painter.setPen(QPen(color, self.pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        rect = QRect(start, end).normalized()

        if self.tool == "line":
            painter.drawLine(start, end)
        elif self.tool == "rect":
            painter.drawRect(rect)
        elif self.tool == "ellipse":
            painter.drawEllipse(rect)
        elif self.tool == "arrow":
            self._draw_arrow(painter, start, end)

    def _draw_arrow(self, painter: QPainter, start: QPoint, end: QPoint) -> None:
        painter.drawLine(start, end)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy)
        if length < 4:
            return
        angle = math.atan2(dy, dx)
        head_len = max(12, self.pen_width * 4)
        spread = math.radians(28)
        points = [end]
        for sign in (-1, 1):
            theta = angle + math.pi + sign * spread
            points.append(
                QPoint(
                    int(end.x() + head_len * math.cos(theta)),
                    int(end.y() + head_len * math.sin(theta)),
                )
            )
        painter.setBrush(self.color)
        painter.drawPolygon(QPolygonF(points))


class ImageEditorWindow(QMainWindow):
    saved = Signal(str)

    def __init__(self, image_path: Path) -> None:
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setWindowTitle(f"Редактор аннотаций - {image_path.name}")
        self.setWindowIcon(app_icon())
        self.setMenuWidget(WindowTitleBar(self, f"Редактор аннотаций - {image_path.name}", "ED"))
        self.canvas = EditorCanvas(image_path)
        self.canvas.zoom_changed.connect(self.update_zoom_label)
        self._build_toolbar()

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.viewport().installEventFilter(self)
        self.setCentralWidget(self.scroll)
        self.apply_styles()
        self.fit_to_image()
        self.statusBar().addPermanentWidget(QSizeGrip(self), 0)
        self.statusBar().showMessage(str(image_path))
        QTimer.singleShot(0, self.fit_canvas_to_view)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Инструменты")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        group = QActionGroup(self)
        group.setExclusive(True)
        for label, tool in [
            ("Карандаш", "pen"),
            ("Линия", "line"),
            ("Стрелка", "arrow"),
            ("Прямоугольник", "rect"),
            ("Эллипс", "ellipse"),
            ("Текст", "text"),
        ]:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setData(tool)
            action.triggered.connect(lambda _checked=False, a=action: self.canvas.set_tool(a.data()))
            group.addAction(action)
            toolbar.addAction(action)
            if tool == "pen":
                action.setChecked(True)

        toolbar.addSeparator()

        color_action = QAction("Цвет", self)
        color_action.triggered.connect(self.choose_color)
        toolbar.addAction(color_action)

        width_box = QSpinBox()
        width_box.setRange(1, 30)
        width_box.setValue(self.canvas.pen_width)
        width_box.setPrefix("Толщина ")
        width_box.valueChanged.connect(self.canvas.set_width)
        toolbar.addWidget(width_box)

        toolbar.addSeparator()

        zoom_out_action = QAction("−", self)
        zoom_out_action.setToolTip("Отдалить")
        zoom_out_action.triggered.connect(self.canvas.zoom_out)
        toolbar.addAction(zoom_out_action)

        zoom_in_action = QAction("+", self)
        zoom_in_action.setToolTip("Приблизить")
        zoom_in_action.triggered.connect(self.canvas.zoom_in)
        toolbar.addAction(zoom_in_action)

        fit_action = QAction("По размеру", self)
        fit_action.triggered.connect(self.fit_canvas_to_view)
        toolbar.addAction(fit_action)

        real_size_action = QAction("100%", self)
        real_size_action.triggered.connect(self.canvas.reset_zoom)
        toolbar.addAction(real_size_action)

        self.zoom_label = QAction("100%", self)
        self.zoom_label.setEnabled(False)
        toolbar.addAction(self.zoom_label)

        toolbar.addSeparator()

        undo_action = QAction("Отменить", self)
        undo_action.triggered.connect(self.canvas.undo)
        toolbar.addAction(undo_action)

        copy_action = QAction("Копировать", self)
        copy_action.triggered.connect(self.copy_to_clipboard)
        toolbar.addAction(copy_action)

        save_action = QAction("Сохранить", self)
        save_action.triggered.connect(self.save)
        toolbar.addAction(save_action)

        save_as_action = QAction("Сохранить как", self)
        save_as_action.triggered.connect(self.save_as)
        toolbar.addAction(save_as_action)

        close_action = QAction("Сохранить и закрыть", self)
        close_action.triggered.connect(self.close)
        toolbar.addAction(close_action)

    def choose_color(self) -> None:
        color = QColorDialog.getColor(self.canvas.color, self, "Цвет аннотаций")
        self.canvas.set_color(color)

    def save(self) -> None:
        try:
            path = self.canvas.save()
        except OSError as exc:
            QMessageBox.warning(self, "Ошибка сохранения", str(exc))
            return
        self.canvas.copy_to_clipboard()
        self.statusBar().showMessage(f"Сохранено: {path}", 4000)
        self.saved.emit(str(path))

    def save_as(self) -> None:
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить изображение",
            str(self.canvas.image_path),
            "Images (*.png *.jpg *.bmp)",
        )
        if not file_name:
            return
        try:
            path = self.canvas.save(Path(file_name))
        except OSError as exc:
            QMessageBox.warning(self, "Ошибка сохранения", str(exc))
            return
        self.canvas.copy_to_clipboard()
        self.statusBar().showMessage(f"Сохранено: {path}", 4000)
        self.saved.emit(str(path))

    def copy_to_clipboard(self) -> None:
        self.canvas.copy_to_clipboard()
        self.statusBar().showMessage("Изображение скопировано в буфер обмена.", 3000)

    def fit_to_image(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        image_size = self.canvas.pixmap.size()
        width = min(max(900, image_size.width() + 90), int(screen.width() * 0.94))
        height = min(max(620, image_size.height() + 170), int(screen.height() * 0.92))
        self.resize(width, height)
        frame = self.frameGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.topLeft())

    def fit_canvas_to_view(self) -> None:
        self.canvas.fit_zoom(self.scroll.viewport().size())

    def update_zoom_label(self, zoom: float) -> None:
        if hasattr(self, "zoom_label"):
            self.zoom_label.setText(f"{int(zoom * 100)}%")

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        if watched is self.scroll.viewport() and event.type() == QEvent.Wheel:
            if event.modifiers() & Qt.ControlModifier:
                if event.angleDelta().y() > 0:
                    self.canvas.zoom_in()
                else:
                    self.canvas.zoom_out()
                return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            path = self.canvas.save()
            self.canvas.copy_to_clipboard()
            self.saved.emit(str(path))
        except OSError as exc:
            QMessageBox.warning(self, "Ошибка сохранения", str(exc))
        event.accept()

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
            }
            QToolBar {
                background: #101113;
                border: 0;
                border-bottom: 1px solid #343a40;
                spacing: 6px;
                padding: 8px;
            }
            QToolButton {
                background: #282d32;
                border: 1px solid #46505a;
                border-radius: 7px;
                color: #f1f3f5;
                padding: 7px 10px;
                font-weight: 600;
            }
            QToolButton:hover {
                background: #343139;
                border-color: #ff4d2e;
            }
            QToolButton:checked, QToolButton:pressed {
                background: #b62f1d;
                border-color: #ff6b4a;
                color: white;
            }
            QSpinBox {
                background: #15171a;
                border: 1px solid #454b50;
                border-radius: 6px;
                padding: 5px;
                min-width: 92px;
            }
            QScrollArea {
                background: #101113;
                border: 0;
            }
            QStatusBar {
                background: #101113;
                color: #ced4da;
                border-top: 1px solid #343a40;
            }
            """
        )
