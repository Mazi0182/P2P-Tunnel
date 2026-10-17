"""
P2P Tunnel Modern Windows Client Application (PyQt6).
Monochrome Dark & Light theme architecture with native Windows frame,
180Hz hardware-accelerated animations, and server-provided connection address.
"""

import asyncio
import ctypes
import os
import sys
import tempfile
import threading
from PyQt6.QtCore import (
    Qt, QPoint, QPointF, QRectF, QEvent, QPropertyAnimation, QEasingCurve,
    pyqtSignal, QObject, QTimer, QParallelAnimationGroup
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QGraphicsOpacityEffect,
    QSystemTrayIcon, QMenu, QProgressBar
)
from PyQt6.QtGui import (
    QColor, QIcon, QPixmap, QAction, QPalette, QPainter,
    QPainterPath, QPen, QFont, QCursor, QGuiApplication
)

from core.invite import normalize_server_key
from core.paths import get_client_config_path, get_asset_path
from core.updater import (
    check_for_updates, fetch_version_manifest, download_file,
    apply_update_and_restart, APP_VERSION, DEFAULT_UPDATE_URL
)
from client.client_core import P2PMCClientCore
from client.gui.styles import build_theme_stylesheet, THEME_PALETTES
from client.gui.widgets import (
    SmoothLabel, MarqueeLabel, ServerNodeIcon, ThemeToggleButton,
    PingBadge, TunnelSwitch, AnimatedButton, AnimatedStack,
    HighHzAnimator, ease_out_cubic
)
from client.gui.dialogs import ServerConfigPage


class AsyncBridge(QObject):
    """Bridges asynchronous client events to Qt Main Thread signals."""
    state_changed = pyqtSignal(str)
    connected = pyqtSignal(int, float)
    ping_updated = pyqtSignal(float)
    error_occurred = pyqtSignal(str)
    disconnected = pyqtSignal()
    update_available = pyqtSignal(dict)
    update_progress = pyqtSignal(int)
    update_error = pyqtSignal(str)
    update_ready = pyqtSignal(str, str)
    post_update_notes_ready = pyqtSignal(str)


class _ThemeCrossfadeOverlay(QWidget):
    """
    Temporary 180Hz full-window overlay that fades out the old theme snapshot
    so switching between Dark and Light themes is butter-smooth.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._pixmap = None
        self._alpha = 0.0
        self.hide()

        self._anim = HighHzAnimator(duration_ms=220, easing=ease_out_cubic, parent=self)
        self._anim.valueChanged.connect(self._on_step)
        self._anim.finished.connect(self.hide)

    def start_crossfade(self, snapshot: QPixmap):
        self._pixmap = snapshot
        self._alpha = 1.0
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self._anim.start(1.0, 0.0)

    def _on_step(self, val: float):
        self._alpha = max(0.0, min(1.0, float(val)))
        self.update()

    def paintEvent(self, event):
        if not self._pixmap or self._pixmap.isNull() or self._alpha <= 0.005:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(self._alpha)
        painter.drawPixmap(QPointF(0.0, 0.0), self._pixmap)


class UpdateToast(QFrame):
    """Floating monochrome notification pill for update notifications and release notes."""
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("UpdateToast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)

        self.setStyleSheet("""
            #UpdateToast {
                background-color: #141417;
                border: 1px solid #3f3f46;
                border-radius: 14px;
            }
            #UpdateToast QLabel {
                background: transparent;
                border: none;
            }
            #UpdateToastIcon {
                color: #34d399;
                font-size: 14px;
                font-weight: bold;
            }
            #UpdateToastText {
                color: #fafafa;
                font-size: 12px;
                font-weight: 700;
            }
            #UpdateToastSub {
                color: #a1a1aa;
                font-size: 11px;
                font-weight: 500;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 9, 16, 9)
        layout.setSpacing(10)

        self.lbl_icon = QLabel("✓", self)
        self.lbl_icon.setObjectName("UpdateToastIcon")
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.lbl_icon)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self.lbl_text = QLabel("", self)
        self.lbl_text.setObjectName("UpdateToastText")
        self.lbl_text.setWordWrap(True)
        text_col.addWidget(self.lbl_text)

        self.lbl_sub = QLabel("", self)
        self.lbl_sub.setObjectName("UpdateToastSub")
        self.lbl_sub.setWordWrap(True)
        self.lbl_sub.setVisible(False)
        text_col.addWidget(self.lbl_sub)

        layout.addLayout(text_col, 1)

        self._anim_group = None
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.fade_out)

    def show_toast(self, text: str, duration_ms: int = 4000, notes: str = ""):
        parent = self.parent()
        if not parent:
            return

        p_width = parent.width()
        max_w = max(240, p_width - 28)
        max_text_w = max_w - 52

        self.lbl_text.setMaximumWidth(max_text_w)
        self.lbl_text.setText(text)

        clean_notes = (notes or "").strip()
        if clean_notes:
            self.lbl_sub.setMaximumWidth(max_text_w)
            self.lbl_sub.setText(clean_notes)
            self.lbl_sub.setVisible(True)
        else:
            self.lbl_sub.setText("")
            self.lbl_sub.setVisible(False)

        self.layout().activate()
        self.adjustSize()

        tw = min(max_w, max(200, self.sizeHint().width()))
        th = self.sizeHint().height()
        self.resize(tw, th)

        rest_x = max(10, (p_width - tw) // 2)
        rest_y = 14

        start_x = rest_x
        start_y = -th - 10

        self.move(start_x, start_y)
        self.show()
        self.raise_()

        if self._anim_group and self._anim_group.state() == QParallelAnimationGroup.State.Running:
            self._anim_group.stop()

        self._opacity_effect.setOpacity(0.0)
        self._anim_group = QParallelAnimationGroup(self)

        pos_anim = QPropertyAnimation(self, b"pos")
        pos_anim.setDuration(360)
        pos_anim.setStartValue(QPoint(start_x, start_y))
        pos_anim.setEndValue(QPoint(rest_x, rest_y))
        pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        opacity_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        opacity_anim.setDuration(280)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        opacity_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        self._anim_group.addAnimation(pos_anim)
        self._anim_group.addAnimation(opacity_anim)
        self._anim_group.finished.connect(lambda: self._dismiss_timer.start(duration_ms))
        self._anim_group.start()

    def fade_out(self):
        if not self.isVisible():
            return
        if self._anim_group and self._anim_group.state() == QParallelAnimationGroup.State.Running:
            self._anim_group.stop()

        curr_x = self.x()
        curr_y = self.y()
        self._anim_group = QParallelAnimationGroup(self)

        pos_anim = QPropertyAnimation(self, b"pos")
        pos_anim.setDuration(300)
        pos_anim.setStartValue(QPoint(curr_x, curr_y))
        pos_anim.setEndValue(QPoint(curr_x, curr_y - 12))
        pos_anim.setEasingCurve(QEasingCurve.Type.InQuad)

        opacity_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        opacity_anim.setDuration(300)
        opacity_anim.setStartValue(self._opacity_effect.opacity())
        opacity_anim.setEndValue(0.0)
        opacity_anim.setEasingCurve(QEasingCurve.Type.InQuad)

        self._anim_group.addAnimation(pos_anim)
        self._anim_group.addAnimation(opacity_anim)
        self._anim_group.finished.connect(self.hide)
        self._anim_group.start()


class RestartOverlay(QFrame):
    """Monochrome full-frame overlay shown when an OTA update is being applied."""
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("RestartOverlay")
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_icon = QLabel("↻", self)
        self.lbl_icon.setFixedSize(52, 52)
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_icon, 0, Qt.AlignmentFlag.AlignCenter)

        self.lbl_title = QLabel("Güncelleme Kuruluyor", self)
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_title)

        self.lbl_desc = QLabel("Uygulama yeniden başlatılıyor...", self)
        self.lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_desc)

        self.pbar = QProgressBar(self)
        self.pbar.setRange(0, 0)
        self.pbar.setFixedWidth(190)
        self.pbar.setFixedHeight(5)
        self.pbar.setTextVisible(False)
        layout.addWidget(self.pbar, 0, Qt.AlignmentFlag.AlignCenter)

        self.set_theme("dark")

    def set_theme(self, theme: str):
        if theme == "light":
            self.setStyleSheet("#RestartOverlay { background-color: #efeff2; border: none; } #RestartOverlay QLabel { background: transparent; border: none; }")
            self.lbl_icon.setStyleSheet("background-color: #141417; color: #ffffff; font-size: 26px; font-weight: bold; border-radius: 26px;")
            self.lbl_title.setStyleSheet("color: #141417; font-size: 16px; font-weight: 800;")
            self.lbl_desc.setStyleSheet("color: #52525b; font-size: 12px; font-weight: 500;")
            self.pbar.setStyleSheet("QProgressBar { background-color: #d4d4d8; border: none; border-radius: 2px; } QProgressBar::chunk { background-color: #141417; border-radius: 2px; }")
        else:
            self.setStyleSheet("#RestartOverlay { background-color: #0c0c0e; border: none; } #RestartOverlay QLabel { background: transparent; border: none; }")
            self.lbl_icon.setStyleSheet("background-color: #f4f4f6; color: #141417; font-size: 26px; font-weight: bold; border-radius: 26px;")
            self.lbl_title.setStyleSheet("color: #f4f4f6; font-size: 16px; font-weight: 800;")
            self.lbl_desc.setStyleSheet("color: #8e8e99; font-size: 12px; font-weight: 500;")
            self.pbar.setStyleSheet("QProgressBar { background-color: #232329; border: none; border-radius: 2px; } QProgressBar::chunk { background-color: #f4f4f6; border-radius: 2px; }")

    def show_overlay(self):
        parent = self.parent()
        if parent:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()


class _TrayMenuItem(QWidget):
    """180Hz animated custom row for the modern system tray popup menu."""
    clicked = pyqtSignal()

    def __init__(
        self,
        label: str,
        icon_kind: str = "window",
        badge_text: str = "",
        is_danger: bool = False,
        theme: str = "dark",
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self._label = label
        self._icon_kind = icon_kind
        self._badge_text = badge_text
        self._is_danger = is_danger
        self._theme = theme
        self._hover_t = 0.0
        self._press_t = 0.0

        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        self._hover_anim = HighHzAnimator(duration_ms=150, easing=ease_out_cubic, parent=self)
        self._hover_anim.valueChanged.connect(self._on_hover_step)

    def set_theme(self, theme: str):
        self._theme = "light" if theme == "light" else "dark"
        self.update()

    def set_content(self, label: str, badge_text: str = ""):
        self._label = label
        self._badge_text = badge_text
        self.update()

    def _on_hover_step(self, val: float):
        self._hover_t = max(0.0, min(1.0, float(val)))
        self.update()

    def enterEvent(self, event):
        self._hover_anim.start(self._hover_t, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._press_t = 0.0
        self._hover_anim.start(self._hover_t, 0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_t = 1.0
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            was_pressed = self._press_t > 0.0
            self._press_t = 0.0
            self.update()
            if was_pressed and self.rect().contains(event.pos()):
                self.clicked.emit()
        super().mouseReleaseEvent(event)

    def _draw_icon(self, painter: QPainter, cx: float, cy: float, color: QColor):
        pen = QPen(color, 1.65, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if self._icon_kind == "window":
            rect = QRectF(cx - 6.5, cy - 5.5, 13.0, 11.0)
            painter.drawRoundedRect(rect, 2.5, 2.5)
            painter.drawLine(QPointF(cx - 6.0, cy - 2.0), QPointF(cx + 6.0, cy - 2.0))
        elif self._icon_kind == "power":
            arc_rect = QRectF(cx - 6.0, cy - 5.5, 12.0, 12.0)
            painter.drawArc(arc_rect, 130 * 16, 280 * 16)
            painter.drawLine(QPointF(cx, cy - 7.0), QPointF(cx, cy - 1.0))
        elif self._icon_kind == "copy":
            back_rect = QRectF(cx - 5.5, cy - 6.0, 8.5, 8.5)
            front_rect = QRectF(cx - 2.5, cy - 3.0, 8.5, 8.5)
            painter.drawRoundedRect(back_rect, 1.8, 1.8)
            painter.drawRoundedRect(front_rect, 1.8, 1.8)
        elif self._icon_kind == "theme":
            if self._theme == "dark":
                painter.drawEllipse(QPointF(cx, cy), 4.2, 4.2)
            else:
                painter.drawEllipse(QPointF(cx, cy), 5.0, 5.0)
                painter.setBrush(color)
                painter.drawEllipse(QPointF(cx, cy), 2.2, 2.2)
                painter.setBrush(Qt.BrushStyle.NoBrush)
        elif self._icon_kind == "quit":
            painter.drawLine(QPointF(cx - 4.5, cy - 4.5), QPointF(cx + 4.5, cy + 4.5))
            painter.drawLine(QPointF(cx + 4.5, cy - 4.5), QPointF(cx - 4.5, cy + 4.5))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        is_dark = self._theme == "dark"
        w = float(self.width())
        h = float(self.height())

        if self._hover_t > 0.005:
            if self._is_danger:
                bg_col = QColor(239, 68, 68, int(38 * self._hover_t))
                border_col = QColor(239, 68, 68, int(75 * self._hover_t))
            elif is_dark:
                bg_col = QColor(255, 255, 255, int(22 * self._hover_t))
                border_col = QColor(255, 255, 255, int(38 * self._hover_t))
            else:
                bg_col = QColor(20, 20, 23, int(18 * self._hover_t))
                border_col = QColor(20, 20, 23, int(32 * self._hover_t))

            pill_rect = QRectF(1.0, 1.0, w - 2.0, h - 2.0)
            painter.setBrush(bg_col)
            painter.setPen(QPen(border_col, 1.0))
            painter.drawRoundedRect(pill_rect, 9.0, 9.0)

        slide_x = 2.5 * self._hover_t
        if self._is_danger:
            fg = QColor("#f87171") if is_dark else QColor("#dc2626")
        elif is_dark:
            fg = QColor("#fafafa") if self._hover_t > 0.25 else QColor("#d4d4d8")
        else:
            fg = QColor("#141417") if self._hover_t > 0.25 else QColor("#3f3f46")

        self._draw_icon(painter, 18.0 + slide_x, h / 2.0, fg)

        font = QFont("Segoe UI", 9)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(fg)

        text_rect = QRectF(36.0 + slide_x, 0.0, w - 46.0 - slide_x, h)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), self._label)

        if self._badge_text:
            badge_font = QFont("Consolas", 8)
            badge_font.setWeight(QFont.Weight.Bold)
            painter.setFont(badge_font)
            badge_col = QColor("#a1a1aa") if is_dark else QColor("#71717a")
            painter.setPen(badge_col)
            badge_rect = QRectF(36.0, 0.0, w - 48.0, h)
            painter.drawText(badge_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), self._badge_text)


class ModernTrayMenu(QWidget):
    """
    Frameless, theme-aware, 180Hz animated popup context menu for the system tray.
    """

    def __init__(self, main_window: "P2PMCMainWindow"):
        super().__init__(None)
        self.main_win = main_window
        self._theme = main_window._current_theme

        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(256)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(4)

        # Header Status Card
        self.header_box = QFrame(self)
        header_layout = QVBoxLayout(self.header_box)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setSpacing(2)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self.lbl_dot = QLabel("●", self.header_box)
        self.lbl_title = QLabel("P2P TUNNEL", self.header_box)
        self.lbl_ver = QLabel(f"v{APP_VERSION}", self.header_box)
        top_row.addWidget(self.lbl_dot)
        top_row.addWidget(self.lbl_title)
        top_row.addStretch(1)
        top_row.addWidget(self.lbl_ver)
        header_layout.addLayout(top_row)

        self.lbl_sub = QLabel("Bağlı Değil", self.header_box)
        header_layout.addWidget(self.lbl_sub)
        root_layout.addWidget(self.header_box)

        # Menu Items
        self.item_show = _TrayMenuItem("P2P Tunnel'ı Göster", icon_kind="window", badge_text="Aç", theme=self._theme, parent=self)
        self.item_show.clicked.connect(self._on_show_clicked)
        root_layout.addWidget(self.item_show)

        self.item_toggle_conn = _TrayMenuItem("Hızlı Bağlan", icon_kind="power", theme=self._theme, parent=self)
        self.item_toggle_conn.clicked.connect(self._on_toggle_conn_clicked)
        root_layout.addWidget(self.item_toggle_conn)

        self.item_copy_addr = _TrayMenuItem("Bağlantı Adresini Kopyala", icon_kind="copy", theme=self._theme, parent=self)
        self.item_copy_addr.clicked.connect(self._on_copy_clicked)
        root_layout.addWidget(self.item_copy_addr)

        self.item_theme = _TrayMenuItem("Görünüm: Açık Tema", icon_kind="theme", theme=self._theme, parent=self)
        self.item_theme.clicked.connect(self._on_theme_clicked)
        root_layout.addWidget(self.item_theme)

        self.sep_line = QFrame(self)
        self.sep_line.setFixedHeight(1)
        root_layout.addWidget(self.sep_line)

        self.item_quit = _TrayMenuItem("Çıkış Yap", icon_kind="quit", is_danger=True, theme=self._theme, parent=self)
        self.item_quit.clicked.connect(self._on_quit_clicked)
        root_layout.addWidget(self.item_quit)

        self._popup_anim = None
        self.set_theme(self._theme)

    def set_theme(self, theme: str):
        self._theme = "light" if theme == "light" else "dark"
        is_dark = self._theme == "dark"

        if is_dark:
            self.header_box.setStyleSheet(
                "QFrame { background-color: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; }"
                "QLabel { background: transparent; border: none; }"
            )
            self.lbl_title.setStyleSheet("color: #fafafa; font-size: 11px; font-weight: 800; letter-spacing: 0.6px;")
            self.lbl_ver.setStyleSheet("color: #a1a1aa; font-family: 'Consolas'; font-size: 10px; font-weight: 700;")
            self.lbl_sub.setStyleSheet("color: #a1a1aa; font-size: 11px; font-weight: 500;")
            self.sep_line.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); border: none;")
        else:
            self.header_box.setStyleSheet(
                "QFrame { background-color: rgba(20, 20, 23, 0.04); border: 1px solid rgba(20, 20, 23, 0.09); border-radius: 10px; }"
                "QLabel { background: transparent; border: none; }"
            )
            self.lbl_title.setStyleSheet("color: #141417; font-size: 11px; font-weight: 800; letter-spacing: 0.6px;")
            self.lbl_ver.setStyleSheet("color: #52525b; font-family: 'Consolas'; font-size: 10px; font-weight: 700;")
            self.lbl_sub.setStyleSheet("color: #52525b; font-size: 11px; font-weight: 500;")
            self.sep_line.setStyleSheet("background-color: rgba(20, 20, 23, 0.09); border: none;")

        for item in (self.item_show, self.item_toggle_conn, self.item_copy_addr, self.item_theme, self.item_quit):
            item.set_theme(self._theme)

        next_theme_label = "Görünüm: Açık Tema" if is_dark else "Görünüm: Koyu Tema"
        self.item_theme.set_content(next_theme_label)
        self.update()

    def refresh_state(self):
        self.set_theme(self.main_win._current_theme)
        core = self.main_win.client_core
        srv_name = (core.config.get("server_name") or "Oyun Sunucusu").strip()

        if core.is_connected:
            self.lbl_dot.setStyleSheet("color: #34d399; font-size: 11px;")
            self.lbl_sub.setText(f"Bağlı • {srv_name}")
            self.item_toggle_conn.set_content("Bağlantıyı Kes", "Aktif")
            self.item_copy_addr.setVisible(True)
            self.item_copy_addr.set_content("Adresi Kopyala", core.active_connection_address or "")
        elif self.main_win._is_connecting:
            self.lbl_dot.setStyleSheet("color: #fbbf24; font-size: 11px;")
            self.lbl_sub.setText("Sunucuya bağlanılıyor...")
            self.item_toggle_conn.set_content("Bağlanıyor...", "")
            self.item_copy_addr.setVisible(False)
        else:
            dot_col = "#71717a" if self._theme == "dark" else "#a1a1aa"
            self.lbl_dot.setStyleSheet(f"color: {dot_col}; font-size: 11px;")
            self.lbl_sub.setText(f"Bağlı Değil • {srv_name}")
            self.item_toggle_conn.set_content("Hızlı Bağlan", "")
            self.item_copy_addr.setVisible(False)

        self.adjustSize()

    def popup_at_cursor(self):
        self.refresh_state()
        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos) or QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRectF(0, 0, 1920, 1080).toRect()

        w = self.width()
        h = self.sizeHint().height()
        self.setFixedHeight(h)

        target_x = min(max(avail.left() + 8, cursor_pos.x() - w // 2), avail.right() - w - 8)
        if cursor_pos.y() - h - 8 >= avail.top():
            target_y = cursor_pos.y() - h - 8
            start_y = target_y + 10
        else:
            target_y = min(cursor_pos.y() + 8, avail.bottom() - h - 8)
            start_y = target_y - 10

        if self._popup_anim and self._popup_anim.state() == QParallelAnimationGroup.State.Running:
            self._popup_anim.stop()

        self.setWindowOpacity(0.0)
        self.move(target_x, start_y)
        self.show()
        self.raise_()
        self.activateWindow()

        self._popup_anim = QParallelAnimationGroup(self)

        pos_anim = QPropertyAnimation(self, b"pos")
        pos_anim.setDuration(180)
        pos_anim.setStartValue(QPoint(target_x, start_y))
        pos_anim.setEndValue(QPoint(target_x, target_y))
        pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        op_anim = QPropertyAnimation(self, b"windowOpacity")
        op_anim.setDuration(160)
        op_anim.setStartValue(0.0)
        op_anim.setEndValue(1.0)
        op_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        self._popup_anim.addAnimation(pos_anim)
        self._popup_anim.addAnimation(op_anim)
        self._popup_anim.start()

    def _on_show_clicked(self):
        self.hide()
        self.main_win._restore_from_tray()

    def _on_toggle_conn_clicked(self):
        self.hide()
        if not self.main_win._is_connecting:
            self.main_win._on_action_button_clicked()

    def _on_copy_clicked(self):
        self.hide()
        self.main_win._copy_assigned_address()

    def _on_theme_clicked(self):
        next_theme = "light" if self.main_win._current_theme == "dark" else "dark"
        self.main_win._on_theme_toggled(next_theme)
        self.refresh_state()

    def _on_quit_clicked(self):
        self.hide()
        self.main_win._quit_from_tray()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_dark = self._theme == "dark"
        bg_col = QColor(16, 16, 20, 248) if is_dark else QColor(246, 246, 249, 250)
        border_col = QColor(255, 255, 255, 34) if is_dark else QColor(20, 20, 23, 32)
        inner_col = QColor(255, 255, 255, 14) if is_dark else QColor(255, 255, 255, 180)

        rect = QRectF(1.0, 1.0, float(self.width()) - 2.0, float(self.height()) - 2.0)
        painter.setBrush(bg_col)
        painter.setPen(QPen(border_col, 1.0))
        painter.drawRoundedRect(rect, 14.0, 14.0)

        inner_rect = QRectF(2.0, 2.0, float(self.width()) - 4.0, float(self.height()) - 4.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(inner_col, 1.0))
        painter.drawRoundedRect(inner_rect, 13.0, 13.0)


class P2PMCMainWindow(QMainWindow):
    def __init__(self, config_path: str = None):
        super().__init__()
        self.config_path = config_path or get_client_config_path()
        self.client_core = P2PMCClientCore(self.config_path)
        self.bridge = AsyncBridge()

        saved_theme = str(self.client_core.config.get("theme", "dark")).strip().lower()
        self._current_theme = "light" if saved_theme == "light" else "dark"
        self.client_core.config["theme"] = self._current_theme

        self._is_updating = False
        self._pending_update = None
        self._is_connecting = False

        self._init_window()
        self._init_ui()
        self._apply_theme(self._current_theme)
        self._init_system_tray()
        self._connect_signals()

        # Check if launched after update or if version changed since last run
        last_ver = self.client_core.config.get("last_seen_version", "")
        self._just_updated = ("--updated" in sys.argv) or bool(last_ver and last_ver != APP_VERSION)
        if self._just_updated:
            QTimer.singleShot(600, self._show_update_success_banner)

        if last_ver != APP_VERSION:
            self.client_core.config["last_seen_version"] = APP_VERSION
            self.client_core.save_server_config(
                self.client_core.server_name,
                self.client_core.server_code,
                self.client_core.admin_key,
                self.client_core.saved_servers,
            )

        # Non-blocking background update check
        threading.Thread(target=self._check_updates_worker, daemon=True).start()

    def _init_window(self):
        # Standard native Windows frame with top-left icon and top-right Minimize & Close
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setFixedSize(390, 470)
        self.setWindowTitle("P2P Tunnel")

        ico_path = get_asset_path("app_icon.ico")
        png_path = get_asset_path("app_icon.png")
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))
        elif os.path.exists(png_path):
            self.setWindowIcon(QIcon(png_path))

        self._apply_windows_titlebar_theme()

    def _apply_windows_titlebar_theme(self):
        """Matches the native Windows 11/10 titlebar color to the active Dark or Light monochrome theme."""
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            dwmapi = ctypes.windll.dwmapi
            if self._current_theme == "dark":
                dark_mode = ctypes.c_int(1)
                dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
                dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
                # COLORREF 0x00BBGGRR for #0c0c0e -> R=0x0C, G=0x0C, B=0x0E -> 0x000E0C0C
                caption_color = ctypes.c_int(0x000E0C0C)
                dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_color), ctypes.sizeof(caption_color))
                # COLORREF 0x00BBGGRR for #f4f4f6 -> 0x00F6F4F4
                text_color = ctypes.c_int(0x00F6F4F4)
                dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_color), ctypes.sizeof(text_color))
            else:
                light_mode = ctypes.c_int(0)
                dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(light_mode), ctypes.sizeof(light_mode))
                dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(light_mode), ctypes.sizeof(light_mode))
                # COLORREF 0x00BBGGRR for #efeff2 -> R=0xEF, G=0xEF, B=0xF2 -> 0x00F2EFEF
                caption_color = ctypes.c_int(0x00F2EFEF)
                dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_color), ctypes.sizeof(caption_color))
                # COLORREF 0x00BBGGRR for #141417 -> 0x00171414
                text_color = ctypes.c_int(0x00171414)
                dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_color), ctypes.sizeof(text_color))
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_windows_titlebar_theme()

    def _init_ui(self):
        root = QWidget(self)
        root.setObjectName("MainRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        # Animated In-Window Page Stack (Page 0: Main View, Page 1: Server Settings)
        self.stack = AnimatedStack(root)
        root_layout.addWidget(self.stack)

        # --- PAGE 0: MAIN VIEW ---
        self.page_main = QWidget(self.stack)
        self.page_main.setObjectName("PageMain")
        self.page_main.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        main_layout = QVBoxLayout(self.page_main)
        main_layout.setContentsMargins(20, 14, 20, 12)
        main_layout.setSpacing(12)

        # 1. Top Header Bar
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        lbl_brand = QLabel("P2P TUNNEL", self.page_main)
        lbl_brand.setObjectName("BrandTitle")
        header_row.addWidget(lbl_brand)

        self.lbl_role_badge = QLabel("OYUNCU", self.page_main)
        self.lbl_role_badge.setObjectName("RoleBadge")
        self.lbl_role_badge.setVisible(False)
        header_row.addWidget(self.lbl_role_badge)

        header_row.addStretch()

        self.ping_badge = PingBadge(self.page_main)
        header_row.addWidget(self.ping_badge)

        self.theme_toggle_btn = ThemeToggleButton(initial_theme=self._current_theme, parent=self.page_main)
        self.theme_toggle_btn.theme_toggled.connect(self._on_theme_toggled)
        header_row.addWidget(self.theme_toggle_btn)

        main_layout.addLayout(header_row)

        # 1.5 Update Banner (Hidden unless OTA update is available)
        self.update_bar = QFrame(self.page_main)
        self.update_bar.setObjectName("UpdateBar")
        self.update_bar.setStyleSheet("""
            #UpdateBar {
                background-color: #141417;
                border: 1px solid #27272a;
                border-radius: 10px;
            }
        """)
        update_bar_layout = QHBoxLayout(self.update_bar)
        update_bar_layout.setContentsMargins(12, 7, 12, 7)
        update_bar_layout.setSpacing(8)

        self.lbl_update_text = QLabel("Yeni sürüm mevcut", self.update_bar)
        self.lbl_update_text.setStyleSheet("color: #fafafa; font-size: 11px; font-weight: 600;")
        self.btn_apply_update = AnimatedButton(
            "Güncelle", variant="dock_action", radius=6, font_size=11, padding="4px 10px", parent=self.update_bar
        )
        self.btn_apply_update.clicked.connect(self._on_start_update_download)

        update_bar_layout.addWidget(self.lbl_update_text, 1)
        update_bar_layout.addWidget(self.btn_apply_update)
        self.update_bar.setVisible(False)
        main_layout.addWidget(self.update_bar)

        # 2. Center Hero Card (Tunnel Switch + Status + Animated Server-Provided Address Pill)
        self.hero_card = QFrame(self.page_main)
        self.hero_card.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(self.hero_card)
        hero_layout.setContentsMargins(20, 22, 20, 20)
        hero_layout.setSpacing(8)
        hero_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hero_layout.addStretch(1)

        # Central Animated Tunnel Switch
        self.tunnel_switch = TunnelSwitch(self.hero_card)
        self.tunnel_switch.toggled.connect(self._on_action_button_clicked)
        hero_layout.addWidget(self.tunnel_switch, 0, Qt.AlignmentFlag.AlignCenter)

        hero_layout.addSpacing(4)

        # Big Status Title
        self.lbl_status_title = SmoothLabel(
            "Bağlı Değil", color_rgb="244, 244, 246", font_size=22, font_weight=800, parent=self.hero_card
        )
        self.lbl_status_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status_title.setMinimumWidth(260)
        self.lbl_status_title.setFixedHeight(30)
        hero_layout.addWidget(self.lbl_status_title, 0, Qt.AlignmentFlag.AlignCenter)

        # Status Subtitle
        self.status_label = SmoothLabel(
            "Bağlanmak için anahtara dokunun.", color_rgb="142, 142, 153", font_size=12, font_weight=500, parent=self.hero_card
        )
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumWidth(280)
        self.status_label.setMinimumHeight(34)
        hero_layout.addWidget(self.status_label)

        # Animated Connection Address Pill (Revealed smoothly at 180Hz when connected)
        self.address_pill = QFrame(self.hero_card)
        self.address_pill.setObjectName("AddressPill")
        self.address_pill.setFixedHeight(0)
        self.address_pill.setVisible(False)

        pill_layout = QHBoxLayout(self.address_pill)
        pill_layout.setContentsMargins(14, 6, 8, 6)
        pill_layout.setSpacing(8)

        self.lbl_assigned_address = QLabel("baglanti.localhost", self.address_pill)
        self.lbl_assigned_address.setObjectName("AddressText")
        pill_layout.addWidget(self.lbl_assigned_address, 1)

        self.btn_copy_ip = AnimatedButton(
            "Kopyala", variant="dock_action", radius=7, font_size=11, padding="5px 12px", parent=self.address_pill
        )
        self.btn_copy_ip.setFixedHeight(28)
        self.btn_copy_ip.clicked.connect(self._copy_assigned_address)
        pill_layout.addWidget(self.btn_copy_ip)

        self._pill_anim = HighHzAnimator(duration_ms=210, easing=ease_out_cubic, parent=self)
        self._pill_anim.valueChanged.connect(self._on_pill_anim_step)
        self._pill_anim.finished.connect(self._on_pill_anim_done)
        self._pill_visible_target = False

        hero_layout.addSpacing(4)
        hero_layout.addWidget(self.address_pill)
        hero_layout.addStretch(1)

        main_layout.addWidget(self.hero_card, 1)

        # 3. Bottom Active Server Dock
        self.server_card = QFrame(self.page_main)
        self.server_card.setObjectName("ServerDockCard")
        srv_card_layout = QHBoxLayout(self.server_card)
        srv_card_layout.setContentsMargins(14, 12, 14, 12)
        srv_card_layout.setSpacing(12)

        # Crisp Vector Server Rack Icon (replaces broken glyph)
        self.server_node_icon = ServerNodeIcon(self.server_card)
        srv_card_layout.addWidget(self.server_node_icon)

        srv_info_vbox = QVBoxLayout()
        srv_info_vbox.setSpacing(2)

        self.lbl_server_name = QLabel("", self.server_card)
        self.lbl_server_name.setObjectName("ServerNameTitle")
        self.lbl_server_code = MarqueeLabel("", self.server_card)
        self.lbl_server_code.setObjectName("ServerCodeSub")

        srv_info_vbox.addWidget(self.lbl_server_name)
        srv_info_vbox.addWidget(self.lbl_server_code)
        srv_card_layout.addLayout(srv_info_vbox, 1)

        self.btn_edit_server = AnimatedButton(
            "Değiştir", variant="dock_action", radius=8, font_size=12, padding="6px 14px", parent=self.server_card
        )
        self.btn_edit_server.clicked.connect(self._open_server_config_page)
        srv_card_layout.addWidget(self.btn_edit_server)

        main_layout.addWidget(self.server_card)

        # 4. Minimal Footer (Version only, right-aligned)
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(2, 0, 2, 0)
        footer_layout.addStretch()

        self.lbl_version = QLabel(f"v{APP_VERSION}", self.page_main)
        self.lbl_version.setObjectName("AppVersionLabel")
        footer_layout.addWidget(self.lbl_version)
        main_layout.addLayout(footer_layout)

        # --- PAGE 1: IN-WINDOW SERVER CONFIGURATION ---
        self.page_config = ServerConfigPage(self.stack)
        self.page_config.saved.connect(self._on_server_saved)
        self.page_config.servers_updated.connect(self._on_servers_updated_immediately)
        self.page_config.cancelled.connect(lambda: self.stack.slide_to(0))

        self.stack.addWidget(self.page_main)
        self.stack.addWidget(self.page_config)

        # Overlays
        self.update_toast = UpdateToast(self)
        self.restart_overlay = RestartOverlay(self)
        self._theme_overlay = _ThemeCrossfadeOverlay(root)

        self._refresh_server_card_labels()
        self._apply_ui_state("normal")

    def _on_theme_toggled(self, new_theme: str):
        new_theme = "light" if new_theme == "light" else "dark"
        if new_theme == self._current_theme:
            return

        # Capture current frame before applying new theme for 180Hz crossfade
        snapshot = self.centralWidget().grab()

        self._current_theme = new_theme
        self.client_core.config["theme"] = new_theme
        self.client_core.save_server_config(
            self.client_core.server_name,
            self.client_core.server_code,
            self.client_core.admin_key,
            self.client_core.saved_servers,
        )

        self._apply_theme(new_theme)
        self._theme_overlay.start_crossfade(snapshot)

    def _apply_theme(self, theme: str):
        theme = "light" if theme == "light" else "dark"
        self._current_theme = theme

        app = QApplication.instance()
        if app:
            pal_cfg = THEME_PALETTES[theme]
            pal = app.palette()
            pal.setColor(QPalette.ColorRole.Window, QColor(pal_cfg["window_bg"]))
            pal.setColor(QPalette.ColorRole.WindowText, QColor(pal_cfg["text_primary"]))
            pal.setColor(QPalette.ColorRole.Base, QColor(pal_cfg["card_bg"]))
            pal.setColor(QPalette.ColorRole.Text, QColor(pal_cfg["text_primary"]))
            pal.setColor(QPalette.ColorRole.Button, QColor(pal_cfg["card_bg"]))
            pal.setColor(QPalette.ColorRole.ButtonText, QColor(pal_cfg["text_primary"]))
            app.setPalette(pal)
            app.setStyleSheet(build_theme_stylesheet(theme))

        self._apply_windows_titlebar_theme()
        self.stack.set_theme(theme)
        self.tunnel_switch.set_theme(theme)
        self.ping_badge.set_theme(theme)
        self.theme_toggle_btn.set_theme(theme, animate=False)
        self.btn_edit_server.set_theme(theme)
        self.btn_copy_ip.set_theme(theme)
        self.btn_apply_update.set_theme(theme)
        self.page_config.set_theme(theme)
        self.restart_overlay.set_theme(theme)

        if hasattr(self, "tray_menu") and self.tray_menu:
            self.tray_menu.set_theme(theme)

        if theme == "dark":
            self.lbl_status_title.set_color_rgb("244, 244, 246")
            self.status_label.set_color_rgb("142, 142, 153")
        else:
            self.lbl_status_title.set_color_rgb("20, 20, 23")
            self.status_label.set_color_rgb("104, 104, 115")

    def _on_pill_anim_step(self, val: float):
        self.address_pill.setFixedHeight(int(val))

    def _on_pill_anim_done(self):
        if not self._pill_visible_target:
            self.address_pill.setVisible(False)

    def _set_address_pill_visible(self, visible: bool, address_text: str = ""):
        if address_text:
            self.lbl_assigned_address.setText(address_text)
        self._pill_visible_target = visible
        if visible:
            self.address_pill.setVisible(True)
            self._pill_anim.start(float(self.address_pill.height()), 42.0)
        else:
            self._pill_anim.start(float(self.address_pill.height()), 0.0)

    def _refresh_server_card_labels(self):
        cfg_name = (self.client_core.config.get("server_name") or "").strip()
        cfg_code = normalize_server_key(self.client_core.config.get("server_code") or "")
        cfg_admin = (self.client_core.config.get("admin_key") or "").strip()

        if not cfg_code:
            self.lbl_server_name.setText("Sunucu Seçilmedi")
            self.lbl_server_code.setText("Eklemek için Değiştir'e basın")
        else:
            display_name = cfg_name if cfg_name and cfg_name not in ("Tanımlanmadı", "Tanimlanmadi", "-") else "Oyun Sunucusu"
            self.lbl_server_name.setText(display_name)
            suffix = " • Yönetici" if cfg_admin else ""
            self.lbl_server_code.setText(f"{cfg_code}{suffix}")

    def _apply_ui_state(self, mode: str):
        """Updates central tunnel switch state."""
        switch_state = {
            "normal": "idle",
            "connecting": "connecting",
            "disconnect": "connected",
            "error": "error",
        }.get(mode, "idle")
        self.tunnel_switch.set_state(switch_state)

    def _connect_signals(self):
        self.bridge.state_changed.connect(self._handle_state_changed)
        self.bridge.connected.connect(self._handle_connected)
        self.bridge.ping_updated.connect(self._handle_ping_updated)
        self.bridge.error_occurred.connect(self._handle_error)
        self.bridge.disconnected.connect(self._handle_disconnected)
        self.bridge.update_available.connect(self._handle_update_available)
        self.bridge.update_progress.connect(self._handle_update_progress)
        self.bridge.update_error.connect(self._handle_update_error)
        self.bridge.update_ready.connect(self._handle_update_ready)
        self.bridge.post_update_notes_ready.connect(self._handle_post_update_notes)

        self.client_core.on_state_change = lambda s: self.bridge.state_changed.emit(s)
        self.client_core.on_connected = lambda role, rtt: self.bridge.connected.emit(int(role), rtt)
        self.client_core.on_ping_update = lambda rtt: self.bridge.ping_updated.emit(rtt)
        self.client_core.on_error = lambda e: self.bridge.error_occurred.emit(e)
        self.client_core.on_disconnected = lambda: self.bridge.disconnected.emit()

    def _check_updates_worker(self):
        update_url = self.client_core.config.get("update_url", DEFAULT_UPDATE_URL).strip() or DEFAULT_UPDATE_URL
        if not update_url:
            return
        manifest = fetch_version_manifest(update_url)
        if not manifest:
            return
        from core.updater import is_version_newer
        remote_ver = str(manifest.get("version", "")).strip()
        if remote_ver and is_version_newer(remote_ver, APP_VERSION):
            self.bridge.update_available.emit(manifest)
        elif getattr(self, "_just_updated", False):
            notes = str(manifest.get("notes") or "").strip()
            if notes:
                self.bridge.post_update_notes_ready.emit(notes)

    def _handle_post_update_notes(self, notes: str):
        clean_notes = (notes or "").strip()
        if not clean_notes:
            return
        self.client_core.config["last_update_notes"] = clean_notes
        self.client_core.save_server_config(
            self.client_core.server_name,
            self.client_core.server_code,
            self.client_core.admin_key,
            self.client_core.saved_servers,
        )
        self.update_toast.show_toast(
            f"Uygulama güncellendi (v{APP_VERSION})",
            duration_ms=6500,
            notes=clean_notes,
        )

    def _handle_update_available(self, update_info: dict):
        self._pending_update = update_info
        ver = update_info.get("version", "")
        notes = str(update_info.get("notes") or "").strip()
        if notes:
            self.client_core.config["last_update_notes"] = notes
            self.update_bar.setToolTip(notes)
        self.lbl_update_text.setText(f"Yeni sürüm (v{ver}) indiriliyor...")
        self.btn_apply_update.setText("İndiriliyor...")
        self.btn_apply_update.setEnabled(False)
        self.update_bar.setVisible(True)
        self._on_start_update_download()

    def _on_start_update_download(self):
        if not self._pending_update:
            return
        download_url = self._pending_update.get("download_url")
        sha256 = self._pending_update.get("sha256")
        target_filename = self._pending_update.get("filename")
        if not download_url:
            return

        self.btn_apply_update.setEnabled(False)
        self.btn_apply_update.setText("İndiriliyor...")

        def _download_thread():
            temp_dir = tempfile.gettempdir()
            clean_ver = str(self._pending_update.get("version") or "latest").replace(".", "_")
            dest_file = os.path.join(temp_dir, f"P2P_Tunnel_Client_v{clean_ver}.exe")
            ok = download_file(
                download_url,
                dest_file,
                expected_sha256=sha256,
                progress_callback=lambda p: self.bridge.update_progress.emit(p)
            )
            if ok:
                self.bridge.update_ready.emit(dest_file, target_filename or "")
            else:
                self.bridge.update_error.emit("İndirme doğrulanamadı.")

        threading.Thread(target=_download_thread, daemon=True).start()

    def _handle_update_progress(self, pct: int):
        ver = (self._pending_update or {}).get("version", "")
        if pct >= 100:
            self.lbl_update_text.setText(f"v{ver} doğrulanıyor...")
            self.btn_apply_update.setText("Doğrulanıyor...")
        else:
            self.lbl_update_text.setText(f"v{ver} indiriliyor: %{pct}")

    def _handle_update_ready(self, dest_file: str, target_filename: str):
        self._downloaded_update = (dest_file, target_filename)
        ver = (self._pending_update or {}).get("version", "")
        notes = str((self._pending_update or {}).get("notes") or "").strip()
        if notes:
            self.client_core.config["last_update_notes"] = notes
            self.client_core.save_server_config(
                self.client_core.server_name,
                self.client_core.server_code,
                self.client_core.admin_key,
                self.client_core.saved_servers,
            )
        self.lbl_update_text.setText(f"v{ver} güncellemesi hazır")
        self.btn_apply_update.setEnabled(True)
        self.btn_apply_update.setText("Şimdi Kur")
        try:
            self.btn_apply_update.clicked.disconnect()
        except Exception:
            pass
        self.btn_apply_update.clicked.connect(self._trigger_update_restart)
        self.update_toast.show_toast(f"v{ver} güncellemesi hazır.", duration_ms=6000, notes=notes)

    def _trigger_update_restart(self):
        if not getattr(self, "_downloaded_update", None):
            return
        dest_file, target_filename = self._downloaded_update
        self._is_updating = True
        self.restart_overlay.show_overlay()
        QTimer.singleShot(
            1200,
            lambda: apply_update_and_restart(dest_file, target_filename=target_filename or None),
        )

    def _handle_update_error(self, err_msg: str):
        self.btn_apply_update.setEnabled(True)
        self.btn_apply_update.setText("Tekrar Dene")
        self.lbl_update_text.setText(f"Hata: {err_msg}")

    def _show_update_success_banner(self):
        saved_notes = str(self.client_core.config.get("last_update_notes") or "").strip()
        self.update_toast.show_toast(
            f"Uygulama güncellendi (v{APP_VERSION})",
            duration_ms=6500 if saved_notes else 4500,
            notes=saved_notes,
        )

    def _open_server_config_page(self):
        curr_name = (self.client_core.config.get("server_name") or "").strip()
        if curr_name in ("Tanımlanmadı", "Tanimlanmadi", "-"):
            curr_name = ""
        curr_code = normalize_server_key(self.client_core.config.get("server_code", ""))
        curr_admin_key = self.client_core.config.get("admin_key", "")
        self.page_config.load_data(
            self.client_core.saved_servers,
            curr_name,
            curr_code,
            curr_admin_key,
        )
        self.stack.slide_to(1)

    def _on_servers_updated_immediately(self, name: str, code: str, admin_key: str, saved_servers: list):
        """Called immediately when the user deletes a saved server so deletion persists even if they press 'Geri'."""
        self.client_core.save_server_config(name, code, admin_key, saved_servers)
        self._refresh_server_card_labels()
        if not code:
            self.status_label.set_smooth_text("Sunucu seçilmedi. Bağlanmak için bir sunucu ekleyin.")

    def _on_server_saved(self, name: str, code: str, admin_key: str, saved_servers: list):
        self.client_core.save_server_config(name, code, admin_key, saved_servers)
        self._refresh_server_card_labels()
        self.stack.slide_to(0)

        display_name = name.strip() or code.strip() or "-"
        if code:
            self.status_label.set_smooth_text(f"{display_name} seçildi. Bağlanmak için anahtara dokunun.")
        else:
            self.status_label.set_smooth_text("Sunucu seçilmedi. Bağlanmak için bir sunucu ekleyin.")

    def _on_action_button_clicked(self):
        if self._is_connecting:
            return
        if self.client_core.is_connected:
            self._on_disconnect_clicked()
        else:
            self._on_connect_clicked()

    def _on_connect_clicked(self):
        cfg_code = normalize_server_key(self.client_core.config.get("server_code") or "")
        if not cfg_code:
            self._open_server_config_page()
            return

        self._is_connecting = True
        self.tunnel_switch.setEnabled(False)
        self.btn_edit_server.setEnabled(False)
        self.lbl_status_title.set_smooth_text("Bağlanıyor...")
        self._apply_ui_state("connecting")
        self.status_label.set_smooth_text("Sunucu ile bağlantı kuruluyor...")

        thread = threading.Thread(target=self._run_client_thread, daemon=True)
        thread.start()

    def _on_disconnect_clicked(self):
        self.tunnel_switch.setEnabled(False)
        self.lbl_status_title.set_smooth_text("Kesiliyor...")
        self.status_label.set_smooth_text("Bağlantı sonlandırılıyor...")
        self._set_address_pill_visible(False)
        if self.client_core.loop and self.client_core.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.client_core.disconnect_async(), self.client_core.loop)

    def _run_client_thread(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.client_core.loop = loop
        loop.run_until_complete(self.client_core.connect_async())

    def _handle_state_changed(self, text: str):
        self.status_label.set_smooth_text(text)

    def _handle_connected(self, role: int, rtt: float):
        self._is_connecting = False
        self.tunnel_switch.setEnabled(True)
        self.btn_edit_server.setEnabled(False)
        self.server_node_icon.set_connected(True)
        self.lbl_status_title.set_smooth_text("Bağlı")
        self._apply_ui_state("disconnect")

        assigned_addr = self.client_core.active_connection_address
        self._set_address_pill_visible(True, assigned_addr)

        self.lbl_role_badge.setVisible(True)
        if role == 2:  # Role.ADMIN
            self.lbl_role_badge.setText("YÖNETİCİ")
            self.status_label.set_smooth_text("Yönetici bağlantısı aktif.")
        else:
            self.lbl_role_badge.setText("OYUNCU")
            self.status_label.set_smooth_text("Bağlantı aktif. Adresi kopyalayıp bağlanabilirsiniz.")
        self.ping_badge.update_ping(rtt, force=True)
        if hasattr(self, "tray_menu") and self.tray_menu and self.tray_menu.isVisible():
            self.tray_menu.refresh_state()

    def _handle_disconnected(self):
        self._is_connecting = False
        self.tunnel_switch.setEnabled(True)
        self.btn_edit_server.setEnabled(True)
        self.server_node_icon.set_connected(False)
        self.lbl_status_title.set_smooth_text("Bağlı Değil")
        self.lbl_role_badge.setVisible(False)
        self._set_address_pill_visible(False)
        self._apply_ui_state("normal")
        self.ping_badge.update_ping(-1)
        self.status_label.set_smooth_text("Bağlanmak için anahtara dokunun.")
        if hasattr(self, "tray_menu") and self.tray_menu and self.tray_menu.isVisible():
            self.tray_menu.refresh_state()

    def _copy_assigned_address(self):
        addr = self.client_core.active_connection_address
        clipboard = QApplication.clipboard()
        clipboard.setText(addr)

        self.btn_copy_ip.setText("Kopyalandı ✓")
        self.btn_copy_ip.set_variant("copied")

        def _reset_copy_btn():
            self.btn_copy_ip.setText("Kopyala")
            self.btn_copy_ip.set_variant("dock_action")

        QTimer.singleShot(1400, _reset_copy_btn)

    def _handle_ping_updated(self, rtt: float):
        self.ping_badge.update_ping(rtt)

    def _handle_error(self, err_msg: str):
        self._is_connecting = False
        self.tunnel_switch.setEnabled(True)
        self.btn_edit_server.setEnabled(True)
        self.server_node_icon.set_connected(False)
        self.lbl_status_title.set_smooth_text("Bağlantı Hatası")
        self.lbl_role_badge.setVisible(False)
        self._set_address_pill_visible(False)
        self._apply_ui_state("error")

        if "OUTDATED" in err_msg or "güncelle" in err_msg.lower():
            clean_msg = err_msg.replace("OUTDATED:", "").strip()
            self.status_label.set_smooth_text(clean_msg)
            self.update_toast.show_toast(clean_msg, duration_ms=8000)
            if not getattr(self, "_pending_update", None):
                threading.Thread(target=self._check_updates_worker, daemon=True).start()
        else:
            self.status_label.set_smooth_text(err_msg)
        if hasattr(self, "tray_menu") and self.tray_menu and self.tray_menu.isVisible():
            self.tray_menu.refresh_state()

    # System Tray Management & Minimize-to-Tray
    def _init_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)

        ico_path = get_asset_path("app_icon.ico")
        png_path = get_asset_path("app_icon.png")
        if os.path.exists(ico_path):
            self.tray_icon.setIcon(QIcon(ico_path))
        elif os.path.exists(png_path):
            self.tray_icon.setIcon(QIcon(png_path))
        else:
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(20, 20, 23))
            self.tray_icon.setIcon(QIcon(pixmap))

        self.tray_icon.setToolTip("P2P Tunnel")
        self.tray_menu = ModernTrayMenu(self)

        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                event.ignore()
                QTimer.singleShot(0, self._minimize_to_tray)
                return
        super().changeEvent(event)

    def _minimize_to_tray(self):
        self.hide()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Context:
            if hasattr(self, "tray_menu") and self.tray_menu:
                self.tray_menu.popup_at_cursor()
        elif reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._restore_from_tray()

    def _restore_from_tray(self):
        self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        self.show()
        self.showNormal()
        self.activateWindow()
        self.raise_()
        self._apply_windows_titlebar_theme()

    def _quit_from_tray(self):
        self._force_quit = True
        self.close()

    def closeEvent(self, event):
        if getattr(self, "_is_updating", False):
            event.ignore()
            return

        if hasattr(self, "tray_menu") and self.tray_menu:
            self.tray_menu.hide()

        if hasattr(self, "tray_icon") and self.tray_icon:
            self.tray_icon.hide()

        if self.client_core.is_connected and self.client_core.loop and self.client_core.loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self.client_core.disconnect_async(), self.client_core.loop)
                future.result(timeout=0.4)
            except Exception:
                pass

        if getattr(self, "_downloaded_update", None) and not getattr(self, "_is_updating", False):
            try:
                dest_file, target_filename = self._downloaded_update
                apply_update_and_restart(dest_file, target_filename=target_filename or None)
            except Exception:
                pass

        event.accept()
        QApplication.quit()


def run_gui(config_path: str = None):
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("p2ptunnel.client.v2")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setApplicationName("P2PTunnel")
    app.setApplicationDisplayName("P2P Tunnel")

    ico_path = get_asset_path("app_icon.ico")
    png_path = get_asset_path("app_icon.png")
    if os.path.exists(ico_path):
        app.setWindowIcon(QIcon(ico_path))
    elif os.path.exists(png_path):
        app.setWindowIcon(QIcon(png_path))

    window = P2PMCMainWindow(config_path=config_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()
