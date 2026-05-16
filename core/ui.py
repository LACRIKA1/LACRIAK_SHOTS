from __future__ import annotations

import random

from PySide6.QtCore import QEasingCurve, QPoint, Property, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QWidget,
)


def mix_color(left: QColor, right: QColor, factor: float) -> QColor:
    factor = max(0.0, min(1.0, factor))
    return QColor(
        int(left.red() + (right.red() - left.red()) * factor),
        int(left.green() + (right.green() - left.green()) * factor),
        int(left.blue() + (right.blue() - left.blue()) * factor),
        int(left.alpha() + (right.alpha() - left.alpha()) * factor),
    )


class WindowTitleBar(QWidget):
    def __init__(self, window: QWidget, title: str, badge: str = "SX") -> None:
        super().__init__(window)
        self.window = window
        self._drag_position: QPoint | None = None
        self.setFixedHeight(46)
        self.setObjectName("WindowTitleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 8, 0)
        layout.setSpacing(10)

        logo = LogoMark(30, self)
        logo.setToolTip(badge)
        layout.addWidget(logo)

        title_label = QLabel(title)
        title_label.setObjectName("TitleText")
        layout.addWidget(title_label, 1)

        self.min_button = self._title_button("_", "Свернуть")
        self.max_button = self._title_button("□", "Развернуть")
        self.close_button = self._title_button("X", "Закрыть")
        self.close_button.setObjectName("TitleCloseButton")

        self.min_button.clicked.connect(window.showMinimized)
        self.max_button.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(window.close)

        layout.addWidget(self.min_button)
        layout.addWidget(self.max_button)
        layout.addWidget(self.close_button)

    def _title_button(self, text: str, tooltip: str) -> QToolButton:
        button = QToolButton(self)
        button.setText(text)
        button.setToolTip(tooltip)
        button.setFixedSize(36, 30)
        button.setObjectName("TitleButton")
        return button

    def toggle_maximized(self) -> None:
        if self.window.isMaximized():
            self.window.showNormal()
            self.max_button.setText("□")
        else:
            self.window.showMaximized()
            self.max_button.setText("❐")

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self.toggle_maximized()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_position is None or not event.buttons() & Qt.LeftButton:
            return
        if self.window.isMaximized():
            return
        self.window.move(event.globalPosition().toPoint() - self._drag_position)

    def mouseReleaseEvent(self, _event) -> None:  # type: ignore[override]
        self._drag_position = None


class AnimatedButton(QPushButton):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._glow = 0.0
        self._ripple = 0.0
        self._pressed = False
        self._accent = QColor("#ff4d2e")
        self._variant = 0
        self._ripple_origin = QPoint()
        self._animation = QPropertyAnimation(self, b"glow", self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._ripple_animation = QPropertyAnimation(self, b"ripple", self)
        self._ripple_animation.setDuration(340)
        self._ripple_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(46)
        self.setFont(QFont("Segoe UI", 10, QFont.DemiBold))

    def get_glow(self) -> float:
        return self._glow

    def set_glow(self, value: float) -> None:
        self._glow = value
        self.update()

    glow = Property(float, get_glow, set_glow)

    def get_ripple(self) -> float:
        return self._ripple

    def set_ripple(self, value: float) -> None:
        self._ripple = value
        self.update()

    ripple = Property(float, get_ripple, set_ripple)

    def _animate(self, value: float) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._glow)
        self._animation.setEndValue(value)
        self._animation.start()

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self._accent = random.choice(
            [
                QColor("#ff4d2e"),
                QColor("#ff7a38"),
                QColor("#e03131"),
                QColor("#f03e3e"),
                QColor("#ffd166"),
            ]
        )
        self._variant = random.randrange(0, 4)
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._pressed = False
        self._animate(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self._pressed = True
        self._ripple_origin = event.position().toPoint()
        self._variant = random.randrange(0, 5)
        self._ripple_animation.stop()
        self._ripple_animation.setStartValue(0.0)
        self._ripple_animation.setEndValue(1.0)
        self._ripple_animation.start()
        self._animate(0.65)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._pressed = False
        self._animate(1.0 if self.underMouse() else 0.0)
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        radius = 8
        base = QColor("#282d32")
        hover = QColor("#3b332f")
        accent = self._accent
        disabled = QColor("#24272a")
        fill = disabled if not self.isEnabled() else mix_color(base, hover, self._glow)
        if self._pressed and self.isEnabled():
            fill = mix_color(fill, QColor("#191b1f"), 0.35)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, mix_color(fill, accent, self._glow * 0.18))
        gradient.setColorAt(1.0, fill)
        painter.setBrush(gradient)
        painter.setPen(QPen(mix_color(QColor("#46505a"), accent, self._glow), 1.3))
        painter.drawRoundedRect(rect, radius, radius)

        if self._glow > 0.02 and self.isEnabled():
            glow = QColor(accent)
            glow.setAlpha(int(28 * self._glow))
            painter.setPen(QPen(glow, 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)

            line_color = QColor(accent)
            line_color.setAlpha(int(70 * self._glow))
            painter.setPen(QPen(line_color, 1.2))
            if self._variant == 0:
                painter.drawLine(rect.left() + 12, rect.bottom() - 6, rect.right() - 12, rect.bottom() - 6)
            elif self._variant == 1:
                painter.drawLine(rect.left() + 10, rect.top() + 7, rect.left() + 38, rect.top() + 7)
                painter.drawLine(rect.right() - 38, rect.bottom() - 7, rect.right() - 10, rect.bottom() - 7)
            elif self._variant == 2:
                painter.drawLine(rect.left() + 12, rect.top() + 8, rect.left() + 30, rect.bottom() - 8)
                painter.drawLine(rect.right() - 30, rect.top() + 8, rect.right() - 12, rect.bottom() - 8)
            else:
                painter.drawArc(rect.adjusted(8, 8, -8, -8), 20 * 16, 70 * 16)

        if self._ripple > 0.01 and self.isEnabled():
            ripple = QColor(accent)
            ripple.setAlpha(int(55 * (1.0 - self._ripple)))
            painter.setPen(Qt.NoPen)
            painter.setBrush(ripple)
            radius_ripple = int(max(rect.width(), rect.height()) * 0.75 * self._ripple)
            painter.drawEllipse(self._ripple_origin, radius_ripple, radius_ripple)

        painter.setPen(QColor("#ffffff") if self.isEnabled() else QColor("#777f87"))
        painter.drawText(rect, Qt.AlignCenter, self.text())
        painter.end()


class ToastWidget(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setObjectName("ToastWidget")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedHeight(54)
        self.setMinimumWidth(260)
        self.setStyleSheet(
            """
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
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        self.label = QLabel()
        self.label.setObjectName("ToastText")
        layout.addWidget(self.label)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.fade = QPropertyAnimation(self.effect, b"opacity", self)
        self.slide = QPropertyAnimation(self, b"pos", self)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.fade_out)

    def show_message(self, text: str, duration_ms: int = 1800) -> None:
        self.label.setText(text)
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None and parent.isVisible():
            global_top_left = parent.mapToGlobal(QPoint(0, 0))
            parent_rect = parent.rect()
            target = QPoint(global_top_left.x() + parent_rect.right() - self.width() - 22, global_top_left.y() + 62)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            target = QPoint(screen.right() - self.width() - 28, screen.top() + 72)
        start = QPoint(target.x() + 22, target.y())
        self.move(start)
        self.show()
        self.raise_()

        self.fade.stop()
        self.slide.stop()
        self.effect.setOpacity(0.0)
        self.fade.setDuration(180)
        self.fade.setStartValue(0.0)
        self.fade.setEndValue(1.0)
        self.fade.setEasingCurve(QEasingCurve.OutCubic)
        self.slide.setDuration(220)
        self.slide.setStartValue(start)
        self.slide.setEndValue(target)
        self.slide.setEasingCurve(QEasingCurve.OutCubic)
        self.fade.start()
        self.slide.start()
        self.hide_timer.start(duration_ms)

    def fade_out(self) -> None:
        self.fade.stop()
        self.fade.setDuration(260)
        self.fade.setStartValue(self.effect.opacity())
        self.fade.setEndValue(0.0)
        self.fade.setEasingCurve(QEasingCurve.InCubic)
        self.fade.finished.connect(self.hide)
        self.fade.start()


class LogoMark(QWidget):
    def __init__(self, size: int = 30, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self.setObjectName("LogoMark")

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        draw_logo(painter, self.rect())
        painter.end()


def draw_logo(painter: QPainter, rect) -> None:
    box = rect.adjusted(1, 1, -1, -1)
    radius = max(6, int(box.width() * 0.22))

    bg = QLinearGradient(box.topLeft(), box.bottomRight())
    bg.setColorAt(0, QColor("#ff5a36"))
    bg.setColorAt(0.55, QColor("#d73321"))
    bg.setColorAt(1, QColor("#111316"))
    painter.setPen(Qt.NoPen)
    painter.setBrush(bg)
    painter.drawRoundedRect(box, radius, radius)

    center = box.center()
    scale = box.width() / 64.0
    pen_width = max(2.4, 8.0 * scale)

    for color, start in [
        (QColor("#fff2e8"), 25),
        (QColor("#ffb03a"), 145),
        (QColor("#14171b"), 265),
    ]:
        color.setAlpha(230)
        pen = QPen(color, pen_width, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        arc_rect = box.adjusted(int(13 * scale), int(13 * scale), -int(13 * scale), -int(13 * scale))
        painter.drawArc(arc_rect, start * 16, 250 * 16)

    painter.setPen(QPen(QColor(255, 255, 255, 70), max(1, int(1.2 * scale))))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(box.adjusted(1, 1, -1, -1), radius, radius)

    painter.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI", max(6, int(14 * scale)), QFont.Black)
    painter.setFont(font)
    painter.drawText(box.adjusted(0, 1, 0, 0), Qt.AlignCenter, "S")


def logo_pixmap(size: int = 64) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    draw_logo(painter, pixmap.rect())
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(size))
    return icon
