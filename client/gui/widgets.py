"""
P2P Tunnel Custom 180Hz Animated UI Widgets.
High-refresh-rate tactile components rendered via hardware-accelerated QPainter
with zero per-frame CSS stylesheet re-parsing:
- HighHzAnimator: 5ms PreciseTimer delta-time animation driver (~180-200 FPS).
- TunnelSwitch: Central interactive toggle switch with polarity-inverting track/thumb, tactile press stretch, and orbital spinner.
- ThemeToggleButton: Header toggle button that smoothly morphs & rotates between vector Moon and Sun icons.
- ServerNodeIcon: Vector dual-blade server rack indicator with animated status LEDs.
- MarqueeLabel: Auto-scrolling single-line label for long server texts with soft edge fade.
- AnimatedButton: Pure QPainter color/border interpolated button.
- AnimatedLineEdit: QPainter focus/hover border-interpolated input field.
- DownwardDropdown: Strictly downward-opening animated dropdown menu.
- AnimatedStack: Dual-pixmap 180Hz slide + cross-fade page transition container (prevents background bleed).
- SmoothLabel & PingBadge: Pure QPainter status indicators.
"""

import math
import time
from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QPointF, QRect, QRectF, QSize,
    QObject, pyqtSignal
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QFont,
    QFontMetricsF, QLinearGradient, QPixmap
)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QLineEdit, QFrame,
    QVBoxLayout, QHBoxLayout, QStackedWidget
)


def lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    """Linearly interpolates between two QColors."""
    t = max(0.0, min(1.0, float(t)))
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue() + (c2.blue() - c1.blue()) * t),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
    )


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    inv = 1.0 - t
    return 1.0 - inv * inv * inv


def ease_out_quad(t: float) -> float:
    t = max(0.0, min(1.0, t))
    inv = 1.0 - t
    return 1.0 - inv * inv


def ease_out_back(t: float, overshoot: float = 1.35) -> float:
    t = max(0.0, min(1.0, t)) - 1.0
    return t * t * ((overshoot + 1.0) * t + overshoot) + 1.0


class HighHzAnimator(QObject):
    """
    180Hz-200Hz frame-rate-independent scalar animation driver using QTimer(PreciseTimer, 5ms)
    and time.perf_counter() delta timing.
    """
    valueChanged = pyqtSignal(float)
    finished = pyqtSignal()

    def __init__(self, duration_ms: int = 180, easing=ease_out_cubic, parent=None):
        super().__init__(parent)
        self._duration = max(1, duration_ms) / 1000.0
        self._easing = easing
        self._start_val = 0.0
        self._end_val = 1.0
        self._current_val = 0.0
        self._start_time = 0.0

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(5)  # ~200 Hz tick rate for 180Hz+ displays
        self._timer.timeout.connect(self._on_tick)

    def setDuration(self, duration_ms: int):
        self._duration = max(1, duration_ms) / 1000.0

    def isRunning(self) -> bool:
        return self._timer.isActive()

    def stop(self):
        self._timer.stop()

    def start(self, start_val: float, end_val: float):
        self._start_val = float(start_val)
        self._end_val = float(end_val)
        self._current_val = self._start_val
        if abs(self._end_val - self._start_val) < 1e-5:
            self._current_val = self._end_val
            self._timer.stop()
            self.valueChanged.emit(self._current_val)
            self.finished.emit()
            return
        self._start_time = time.perf_counter()
        if not self._timer.isActive():
            self._timer.start()

    def _on_tick(self):
        elapsed = time.perf_counter() - self._start_time
        raw_t = elapsed / self._duration
        if raw_t >= 1.0:
            self._timer.stop()
            self._current_val = self._end_val
            self.valueChanged.emit(self._current_val)
            self.finished.emit()
        else:
            eased_t = self._easing(raw_t)
            self._current_val = self._start_val + (self._end_val - self._start_val) * eased_t
            self.valueChanged.emit(self._current_val)


class SmoothLabel(QLabel):
    """
    QLabel with 180Hz opacity cross-fade when text changes.
    Renders via QPainter in paintEvent instead of re-parsing stylesheets every frame.
    """

    def __init__(self, text: str = "", color_rgb: str = "244, 244, 246", font_size: int = 12, font_weight: int = 500, parent=None):
        super().__init__(text, parent)
        self._color = self._parse_rgb(color_rgb)
        self._font_size = font_size
        self._font_weight = font_weight
        self._target_text = text
        self._alpha = 1.0

        f = self.font()
        f.setPixelSize(self._font_size)
        if self._font_weight >= 800:
            f.setWeight(QFont.Weight.ExtraBold)
        elif self._font_weight >= 700:
            f.setWeight(QFont.Weight.Bold)
        elif self._font_weight >= 600:
            f.setWeight(QFont.Weight.DemiBold)
        else:
            f.setWeight(QFont.Weight.Medium)
        self.setFont(f)

        self._fade_out_anim = HighHzAnimator(duration_ms=95, easing=ease_out_quad, parent=self)
        self._fade_out_anim.valueChanged.connect(self._on_alpha_step)
        self._fade_out_anim.finished.connect(self._on_fade_out_done)

        self._fade_in_anim = HighHzAnimator(duration_ms=130, easing=ease_out_cubic, parent=self)
        self._fade_in_anim.valueChanged.connect(self._on_alpha_step)

    @staticmethod
    def _parse_rgb(color_rgb: str) -> QColor:
        parts = [int(p.strip()) for p in color_rgb.split(",") if p.strip().isdigit()]
        if len(parts) >= 3:
            return QColor(parts[0], parts[1], parts[2])
        return QColor(244, 244, 246)

    def set_color_rgb(self, color_rgb: str):
        self._color = self._parse_rgb(color_rgb)
        self.update()

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self.update()

    def _on_alpha_step(self, val: float):
        self._alpha = max(0.0, min(1.0, val))
        self.update()

    def _on_fade_out_done(self):
        self.setText(self._target_text)
        self._fade_in_anim.start(self._alpha, 1.0)

    def set_smooth_text(self, new_text: str):
        if self.text() == new_text and self._target_text == new_text:
            return
        self._target_text = new_text
        self._fade_in_anim.stop()
        self._fade_out_anim.start(self._alpha, 0.0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self.font())
        c = QColor(self._color)
        c.setAlpha(int(255 * self._alpha))
        painter.setPen(c)
        flags = int(self.alignment())
        if self.wordWrap():
            flags |= int(Qt.TextFlag.TextWordWrap)
        painter.drawText(self.rect(), flags, self.text())


class MarqueeLabel(QWidget):
    """
    Single-line subtitle label that renders normally when text fits, and smoothly
    scrolls horizontally at 180Hz with soft edge fade when text exceeds available width.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._text = text
        self._color = QColor("#a1a1aa")
        self._offset = 0.0
        self._pause_until = 0.0
        self._last_tick = 0.0
        self._gap = 42.0
        self._speed = 38.0  # px per second

        self.setFixedHeight(18)
        f = self.font()
        f.setPixelSize(12)
        f.setWeight(QFont.Weight.Medium)
        self.setFont(f)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(5)
        self._timer.timeout.connect(self._on_tick)

    def setText(self, text: str):
        new_text = str(text or "")
        if self._text == new_text:
            return
        self._text = new_text
        self._offset = 0.0
        self._pause_until = time.perf_counter() + 1.2
        self._last_tick = time.perf_counter()
        self._update_scroll_state()
        self.update()

    def text(self) -> str:
        return self._text

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._offset = 0.0
        self._update_scroll_state()

    def _text_width(self) -> float:
        fm = QFontMetricsF(self.font())
        return fm.horizontalAdvance(self._text)

    def _update_scroll_state(self):
        if self.width() > 10 and self._text_width() > self.width() - 2:
            if not self._timer.isActive():
                self._last_tick = time.perf_counter()
                self._pause_until = self._last_tick + 1.2
                self._timer.start()
        else:
            self._timer.stop()
            self._offset = 0.0

    def _on_tick(self):
        now = time.perf_counter()
        dt = min(0.05, max(0.0, now - self._last_tick))
        self._last_tick = now

        tw = self._text_width()
        if tw <= self.width() - 2:
            self._timer.stop()
            self._offset = 0.0
            self.update()
            return

        if now < self._pause_until:
            return

        cycle = tw + self._gap
        self._offset += self._speed * dt
        if self._offset >= cycle:
            self._offset = 0.0
            self._pause_until = now + 1.4
        self.update()

    def paintEvent(self, event):
        if not self._text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self.font())

        w = float(self.width())
        h = float(self.height())
        tw = self._text_width()
        fm = QFontMetricsF(self.font())
        baseline_y = (h + fm.ascent() - fm.descent()) / 2.0

        painter.setPen(self._color)
        if tw <= w - 2:
            painter.drawText(QPointF(0.0, baseline_y), self._text)
            return

        # Scrolling marquee draw with soft edge fade
        pixmap = QPixmap(int(w), int(h))
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setFont(self.font())
        p.setPen(self._color)

        x1 = -self._offset
        x2 = x1 + tw + self._gap
        p.drawText(QPointF(x1, baseline_y), self._text)
        if x2 < w:
            p.drawText(QPointF(x2, baseline_y), self._text)

        # Soft fade at right edge (and left edge when scrolled)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        grad = QLinearGradient(0.0, 0.0, w, 0.0)
        if self._offset > 1.0:
            grad.setColorAt(0.0, QColor(0, 0, 0, 0))
            grad.setColorAt(0.08, QColor(0, 0, 0, 255))
        else:
            grad.setColorAt(0.0, QColor(0, 0, 0, 255))
        grad.setColorAt(0.88, QColor(0, 0, 0, 255))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(0.0, 0.0, w, h), grad)
        p.end()

        painter.drawPixmap(0, 0, pixmap)


class ServerNodeIcon(QWidget):
    """
    Crisp vector Server Rack / Stacked Nodes icon (36x36) replacing the broken glyph.
    Draws two sleek horizontal server blades with animated status LED dots.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 36)
        self._connected_t = 0.0
        self._anim = HighHzAnimator(duration_ms=240, easing=ease_out_cubic, parent=self)
        self._anim.valueChanged.connect(self._on_anim_step)

    def set_connected(self, connected: bool):
        target = 1.0 if connected else 0.0
        self._anim.start(self._connected_t, target)

    def _on_anim_step(self, val: float):
        self._connected_t = val
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Rounded container badge
        bg = lerp_color(QColor("#232329"), QColor("#27272f"), self._connected_t)
        border = lerp_color(QColor("#32323a"), QColor("#454552"), self._connected_t)
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(bg)
        painter.drawRoundedRect(QRectF(0.5, 0.5, 35.0, 35.0), 9.0, 9.0)

        # Two stacked server blades
        blade_pen_color = lerp_color(QColor("#d4d4dc"), QColor("#ffffff"), self._connected_t)
        blade_fill = lerp_color(QColor("#18181c"), QColor("#1f1f26"), self._connected_t)
        led_color = lerp_color(QColor("#71717a"), QColor("#10b981"), self._connected_t)
        vent_color = lerp_color(QColor("#52525b"), QColor("#a1a1aa"), self._connected_t)

        for row_y in (9.5, 19.0):
            blade_rect = QRectF(7.5, row_y, 21.0, 7.5)
            painter.setPen(QPen(blade_pen_color, 1.35))
            painter.setBrush(blade_fill)
            painter.drawRoundedRect(blade_rect, 2.4, 2.4)

            # Status LED dot on left of blade
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(led_color)
            painter.drawEllipse(QPointF(11.3, row_y + 3.75), 1.45, 1.45)

            # Subtle ventilation slot on right of blade
            painter.setPen(QPen(vent_color, 1.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(16.5, row_y + 3.75), QPointF(24.5, row_y + 3.75))


class ThemeToggleButton(QWidget):
    """
    Sleek header button that smoothly morphs & rotates between a crisp vector Moon (Dark Mode)
    and Sun (Light Mode) at 180Hz.
    """
    theme_toggled = pyqtSignal(str)

    def __init__(self, initial_theme: str = "dark", parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme = initial_theme if initial_theme in ("dark", "light") else "dark"
        # _morph_t: 0.0 = dark (moon), 1.0 = light (sun)
        self._morph_t = 1.0 if self._theme == "light" else 0.0
        self._hover_t = 0.0

        self._morph_anim = HighHzAnimator(duration_ms=260, easing=ease_out_back, parent=self)
        self._morph_anim.valueChanged.connect(self._on_morph_step)

        self._hover_anim = HighHzAnimator(duration_ms=150, easing=ease_out_cubic, parent=self)
        self._hover_anim.valueChanged.connect(self._on_hover_step)
        self._update_tooltip()

    def _update_tooltip(self):
        if self._theme == "dark":
            self.setToolTip("Açık Temaya Geç")
        else:
            self.setToolTip("Koyu Temaya Geç")

    def set_theme(self, theme: str, animate: bool = True):
        theme = "light" if theme == "light" else "dark"
        self._theme = theme
        target = 1.0 if theme == "light" else 0.0
        self._update_tooltip()
        if animate:
            self._morph_anim.start(self._morph_t, target)
        else:
            self._morph_anim.stop()
            self._morph_t = target
            self.update()

    def _on_morph_step(self, val: float):
        self._morph_t = val
        self.update()

    def _on_hover_step(self, val: float):
        self._hover_t = val
        self.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._hover_anim.start(self._hover_t, 1.0)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._hover_anim.start(self._hover_t, 0.0)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            next_theme = "light" if self._theme == "dark" else "dark"
            self.set_theme(next_theme, animate=True)
            self.theme_toggled.emit(next_theme)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        t_light = max(0.0, min(1.0, self._morph_t))
        bg_dark = lerp_color(QColor("#18181c"), QColor("#27272f"), self._hover_t)
        bg_light = lerp_color(QColor("#e4e4e7"), QColor("#d4d4d8"), self._hover_t)
        bg = lerp_color(bg_dark, bg_light, t_light)

        border_dark = lerp_color(QColor("#27272f"), QColor("#3f3f4a"), self._hover_t)
        border_light = lerp_color(QColor("#d4d4d8"), QColor("#a1a1aa"), self._hover_t)
        border = lerp_color(border_dark, border_light, t_light)

        fg = lerp_color(QColor("#f4f4f6"), QColor("#141417"), t_light)

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 7.0, 7.0)

        cx = self.width() / 2.0
        cy = self.height() / 2.0

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._morph_t * 180.0)

        # Draw Moon when t_light < 0.85
        moon_alpha = max(0.0, min(1.0, 1.0 - t_light * 1.35))
        if moon_alpha > 0.01:
            mc = QColor(fg)
            mc.setAlpha(int(255 * moon_alpha))
            painter.setPen(QPen(mc, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)

            outer = QPainterPath()
            outer.addEllipse(QPointF(0.0, 0.0), 5.2, 5.2)
            cutout = QPainterPath()
            cutout.addEllipse(QPointF(2.6, -2.2), 4.6, 4.6)
            crescent = outer.subtracted(cutout)
            painter.setBrush(mc)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(crescent)

        # Draw Sun when t_light > 0.15
        sun_alpha = max(0.0, min(1.0, (t_light - 0.15) / 0.85))
        if sun_alpha > 0.01:
            sc = QColor(fg)
            sc.setAlpha(int(255 * sun_alpha))
            painter.setPen(QPen(sc, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.setBrush(sc)
            core_r = 2.8 * sun_alpha
            painter.drawEllipse(QPointF(0.0, 0.0), core_r, core_r)

            ray_inner = 4.4
            ray_outer = 6.2
            for i in range(8):
                ang = i * (math.pi / 4.0)
                cos_a = math.cos(ang)
                sin_a = math.sin(ang)
                painter.drawLine(
                    QPointF(cos_a * ray_inner, sin_a * ray_inner),
                    QPointF(cos_a * ray_outer, sin_a * ray_outer),
                )

        painter.restore()


class PingBadge(QWidget):
    """
    Monochrome real-time latency badge with 180Hz QPainter background interpolation and EWMA smoothing.
    Zero setStyleSheet calls during animations.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PingBadge")
        self.setFixedHeight(24)
        self.setMinimumWidth(56)
        self._text = "-- ms"
        self._theme = "dark"
        self._current_smoothed = -1.0
        self._last_ui_update_time = 0.0
        self._active_progress = 0.0

        f = self.font()
        f.setPixelSize(11)
        f.setWeight(QFont.Weight.Bold)
        self.setFont(f)

        self._bg_anim = HighHzAnimator(duration_ms=220, easing=ease_out_cubic, parent=self)
        self._bg_anim.valueChanged.connect(self._on_anim_step)

    def set_theme(self, theme: str):
        self._theme = "light" if theme == "light" else "dark"
        self.update()

    def _on_anim_step(self, val: float):
        self._active_progress = float(val)
        self.update()

    def _set_text(self, text: str):
        if self._text != text:
            self._text = text
            fm = QFontMetricsF(self.font())
            w = max(56, int(fm.horizontalAdvance(self._text) + 22))
            self.setFixedWidth(w)
            self.update()

    def _animate_to(self, target: float):
        if abs(self._active_progress - target) < 0.01:
            return
        self._bg_anim.start(self._active_progress, target)

    def update_ping(self, ms: float, force: bool = False):
        if ms < 0:
            self._current_smoothed = -1.0
            self._set_text("-- ms")
            self._animate_to(0.0)
            return

        if self._current_smoothed < 0:
            self._current_smoothed = ms
        else:
            self._current_smoothed = 0.85 * self._current_smoothed + 0.15 * ms

        now = time.time()
        if not force and (now - self._last_ui_update_time < 1.5):
            return

        self._last_ui_update_time = now
        smoothed = self._current_smoothed

        if smoothed < 1.0:
            self._set_text("< 1 ms")
        else:
            self._set_text(f"{smoothed:.0f} ms")
        self._animate_to(1.0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        t = self._active_progress
        if self._theme == "dark":
            bg = lerp_color(QColor("#18181c"), QColor("#f4f4f6"), t)
            fg = lerp_color(QColor("#8e8e99"), QColor("#141417"), t)
            border = lerp_color(QColor("#27272f"), QColor("#f4f4f6"), t)
        else:
            bg = lerp_color(QColor("#e4e4e7"), QColor("#141417"), t)
            fg = lerp_color(QColor("#71717a"), QColor("#ffffff"), t)
            border = lerp_color(QColor("#d4d4d8"), QColor("#27272a"), t)

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 7.0, 7.0)

        painter.setFont(self.font())
        painter.setPen(fg)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._text)


class TunnelSwitch(QWidget):
    """
    Central tactile toggle switch with 180Hz hardware-accelerated QPainter animations:
    - Smooth thumb slide (ease_out_back)
    - Polarity inversion between Disconnected and Connected states
    - Hover halo expansion
    - Tactile mouse-press thumb stretch
    - Delta-timed connecting orbital spinner + pulse ripple
    """
    toggled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(164, 88)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._theme = "dark"
        self._state = "idle"  # "idle" | "connecting" | "connected" | "error"
        self._pos = 0.0       # 0.0 (left) -> 1.0 (right)
        self._hover = 0.0     # 0.0 -> 1.0
        self._press = 0.0     # 0.0 -> 1.0
        self._spin_angle = 0.0
        self._pulse_phase = 0.0
        self._last_tick = 0.0

        # 180Hz animations
        self._pos_anim = HighHzAnimator(duration_ms=320, easing=ease_out_back, parent=self)
        self._pos_anim.valueChanged.connect(self._on_pos_changed)

        self._hover_anim = HighHzAnimator(duration_ms=160, easing=ease_out_cubic, parent=self)
        self._hover_anim.valueChanged.connect(self._on_hover_changed)

        self._press_anim = HighHzAnimator(duration_ms=120, easing=ease_out_quad, parent=self)
        self._press_anim.valueChanged.connect(self._on_press_changed)

        # 180Hz continuous loop for connecting spinner & ambient pulse
        self._loop_timer = QTimer(self)
        self._loop_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._loop_timer.setInterval(5)
        self._loop_timer.timeout.connect(self._on_loop_tick)

    def set_theme(self, theme: str):
        self._theme = "light" if theme == "light" else "dark"
        self.update()

    def set_state(self, state: str):
        self._state = state
        target_pos = 1.0 if state in ("connecting", "connected") else 0.0
        self._pos_anim.start(self._pos, target_pos)

        if state == "connecting":
            self._last_tick = time.perf_counter()
            if not self._loop_timer.isActive():
                self._loop_timer.start()
        else:
            self._loop_timer.stop()
            self._pulse_phase = 0.0
        self.update()

    def _on_pos_changed(self, val: float):
        self._pos = float(val)
        self.update()

    def _on_hover_changed(self, val: float):
        self._hover = float(val)
        self.update()

    def _on_press_changed(self, val: float):
        self._press = float(val)
        self.update()

    def _on_loop_tick(self):
        now = time.perf_counter()
        dt = min(0.05, max(0.0, now - self._last_tick))
        self._last_tick = now
        self._spin_angle = (self._spin_angle + 450.0 * dt) % 360.0
        self._pulse_phase = (self._pulse_phase + 1.45 * dt) % 1.0
        self.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._hover_anim.start(self._hover, 1.0)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._hover_anim.start(self._hover, 0.0)
        if self._press > 0.0:
            self._press_anim.start(self._press, 0.0)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._press_anim.start(self._press, 1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_anim.start(self._press, 0.0)
            if self.isEnabled() and self.rect().contains(event.pos()):
                self.toggled.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        track_w, track_h = 140.0, 68.0
        track_x = (w - track_w) / 2.0
        track_y = (h - track_h) / 2.0
        track_rect = QRectF(track_x, track_y, track_w, track_h)
        radius = track_h / 2.0

        clamped_pos = max(0.0, min(1.0, self._pos))
        is_dark = (self._theme == "dark")

        # 1. Outer ambient hover / connecting pulse ring
        if self._state == "connecting":
            pulse_expand = 8.0 * self._pulse_phase
            pulse_alpha = int(105 * (1.0 - self._pulse_phase))
            pulse_rect = track_rect.adjusted(-pulse_expand, -pulse_expand, pulse_expand, pulse_expand)
            ring_rgb = QColor(244, 244, 246, pulse_alpha) if is_dark else QColor(20, 20, 23, pulse_alpha)
            painter.setPen(QPen(ring_rgb, 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(pulse_rect, radius + pulse_expand, radius + pulse_expand)

        if self._hover > 0.01:
            hover_expand = 4.0 * self._hover
            hover_alpha = int(32 * self._hover)
            hover_rect = track_rect.adjusted(-hover_expand, -hover_expand, hover_expand, hover_expand)
            painter.setPen(Qt.PenStyle.NoPen)
            halo_rgb = QColor(244, 244, 246, hover_alpha) if is_dark else QColor(20, 20, 23, hover_alpha)
            painter.setBrush(halo_rgb)
            painter.drawRoundedRect(hover_rect, radius + hover_expand, radius + hover_expand)

        # 2. Pill Track
        if is_dark:
            track_bg_off = lerp_color(QColor("#202026"), QColor("#27272f"), self._hover)
            track_bg_on = lerp_color(QColor("#f4f4f6"), QColor("#ffffff"), self._hover * 0.5)
            track_border_off = lerp_color(QColor("#2e2e38"), QColor("#3f3f4d"), self._hover)
            track_border_on = QColor("#ffffff")
        else:
            track_bg_off = lerp_color(QColor("#e4e4e7"), QColor("#dcdce2"), self._hover)
            track_bg_on = lerp_color(QColor("#141417"), QColor("#1f1f24"), self._hover * 0.5)
            track_border_off = lerp_color(QColor("#d0d0d7"), QColor("#b8b8c2"), self._hover)
            track_border_on = QColor("#141417")

        track_bg = lerp_color(track_bg_off, track_bg_on, clamped_pos)
        track_border = lerp_color(track_border_off, track_border_on, clamped_pos)

        painter.setPen(QPen(track_border, 1.5))
        painter.setBrush(track_bg)
        painter.drawRoundedRect(track_rect, radius, radius)

        # Subtle inner status markers on track
        dot_on_alpha = int(150 * clamped_pos)
        if dot_on_alpha > 5:
            line_col = QColor(20, 20, 23, dot_on_alpha) if is_dark else QColor(255, 255, 255, dot_on_alpha)
            painter.setPen(QPen(line_col, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            lx = track_x + 28.0
            painter.drawLine(QPointF(lx, track_y + 26.0), QPointF(lx, track_y + track_h - 26.0))

        circle_off_alpha = int(135 * (1.0 - clamped_pos))
        if circle_off_alpha > 5:
            circ_col = QColor(142, 142, 153, circle_off_alpha) if is_dark else QColor(82, 82, 91, circle_off_alpha)
            painter.setPen(QPen(circ_col, 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            rx = track_x + track_w - 28.0
            ry = track_y + track_h / 2.0
            painter.drawEllipse(QPointF(rx, ry), 6.5, 6.5)

        # 3. Tactile Thumb (with press stretch)
        padding = 6.0
        base_thumb_d = track_h - padding * 2.0  # 56.0 px
        stretch_w = 7.0 * self._press
        thumb_w = base_thumb_d + stretch_w
        thumb_h = base_thumb_d

        min_x = track_x + padding
        max_x = track_x + track_w - padding - thumb_w
        thumb_x = min_x + (max_x - min_x) * self._pos
        thumb_y = track_y + padding
        thumb_rect = QRectF(thumb_x, thumb_y, thumb_w, thumb_h)

        # Subtle thumb shadow
        shadow_rect = thumb_rect.translated(0, 2.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 50 if is_dark else 38))
        painter.drawRoundedRect(shadow_rect, thumb_h / 2.0, thumb_h / 2.0)

        # Thumb fill & icon color
        if is_dark:
            thumb_bg = lerp_color(QColor("#f4f4f6"), QColor("#141417"), clamped_pos)
            thumb_border = lerp_color(QColor("#ffffff"), QColor("#141417"), clamped_pos)
            icon_color = lerp_color(QColor("#141417"), QColor("#ffffff"), clamped_pos)
        else:
            thumb_bg = lerp_color(QColor("#141417"), QColor("#ffffff"), clamped_pos)
            thumb_border = lerp_color(QColor("#27272a"), QColor("#ffffff"), clamped_pos)
            icon_color = lerp_color(QColor("#ffffff"), QColor("#141417"), clamped_pos)

        painter.setBrush(thumb_bg)
        painter.setPen(QPen(thumb_border, 1.0))
        painter.drawRoundedRect(thumb_rect, thumb_h / 2.0, thumb_h / 2.0)

        # 4. Center Icon inside Thumb (Power Symbol or Connecting Spinner)
        cx = thumb_rect.center().x()
        cy = thumb_rect.center().y()

        if self._state == "connecting":
            spinner_rect = QRectF(cx - 11.0, cy - 11.0, 22.0, 22.0)
            pen = QPen(icon_color, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            start_angle = int(-self._spin_angle * 16)
            span_angle = int(250 * 16)
            painter.drawArc(spinner_rect, start_angle, span_angle)
        else:
            pen = QPen(icon_color, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            arc_r = 9.5
            arc_rect = QRectF(cx - arc_r, cy - arc_r + 1.0, arc_r * 2.0, arc_r * 2.0)
            painter.drawArc(arc_rect, int(130 * 16), int(280 * 16))
            painter.drawLine(QPointF(cx, cy - arc_r - 1.5), QPointF(cx, cy - 1.0))


class AnimatedButton(QPushButton):
    """
    PushButton with 180Hz QPainter hover and press color interpolation.
    Never calls setStyleSheet() on animation frames.
    """

    THEME_PALETTES = {
        "dark": {
            "dark": {
                "bg": QColor("#f4f4f6"),
                "bg_hover": QColor("#ffffff"),
                "bg_press": QColor("#d4d4d8"),
                "fg": QColor("#141417"),
                "fg_hover": QColor("#09090b"),
                "border": QColor("#f4f4f6"),
                "border_hover": QColor("#ffffff"),
            },
            "dock_action": {
                "bg": QColor("#232329"),
                "bg_hover": QColor("#f4f4f6"),
                "bg_press": QColor("#d4d4d8"),
                "fg": QColor("#f4f4f6"),
                "fg_hover": QColor("#141417"),
                "border": QColor("#34343d"),
                "border_hover": QColor("#f4f4f6"),
            },
            "light": {
                "bg": QColor("#232329"),
                "bg_hover": QColor("#f4f4f6"),
                "bg_press": QColor("#d4d4d8"),
                "fg": QColor("#f4f4f6"),
                "fg_hover": QColor("#141417"),
                "border": QColor("#34343d"),
                "border_hover": QColor("#f4f4f6"),
            },
            "subtle": {
                "bg": QColor("#1e1e24"),
                "bg_hover": QColor("#2c2c35"),
                "bg_press": QColor("#18181c"),
                "fg": QColor("#e4e4e7"),
                "fg_hover": QColor("#ffffff"),
                "border": QColor("#2e2e38"),
                "border_hover": QColor("#454552"),
            },
            "danger": {
                "bg": QColor("#1e1e24"),
                "bg_hover": QColor("#f4f4f6"),
                "bg_press": QColor("#d4d4d8"),
                "fg": QColor("#a1a1aa"),
                "fg_hover": QColor("#141417"),
                "border": QColor("#2e2e38"),
                "border_hover": QColor("#f4f4f6"),
            },
            "copied": {
                "bg": QColor("#ffffff"),
                "bg_hover": QColor("#ffffff"),
                "bg_press": QColor("#e4e4e7"),
                "fg": QColor("#141417"),
                "fg_hover": QColor("#141417"),
                "border": QColor("#ffffff"),
                "border_hover": QColor("#ffffff"),
            },
        },
        "light": {
            "dark": {
                "bg": QColor("#141417"),
                "bg_hover": QColor("#2c2c33"),
                "bg_press": QColor("#09090b"),
                "fg": QColor("#ffffff"),
                "fg_hover": QColor("#ffffff"),
                "border": QColor("#141417"),
                "border_hover": QColor("#3f3f46"),
            },
            "dock_action": {
                "bg": QColor("#232329"),
                "bg_hover": QColor("#ffffff"),
                "bg_press": QColor("#e4e4e7"),
                "fg": QColor("#f4f4f6"),
                "fg_hover": QColor("#141417"),
                "border": QColor("#34343d"),
                "border_hover": QColor("#ffffff"),
            },
            "light": {
                "bg": QColor("#f4f4f6"),
                "bg_hover": QColor("#141417"),
                "bg_press": QColor("#27272a"),
                "fg": QColor("#18181b"),
                "fg_hover": QColor("#ffffff"),
                "border": QColor("#d4d4d8"),
                "border_hover": QColor("#141417"),
            },
            "subtle": {
                "bg": QColor("#e4e4e7"),
                "bg_hover": QColor("#d4d4d8"),
                "bg_press": QColor("#c4c4cc"),
                "fg": QColor("#18181b"),
                "fg_hover": QColor("#111113"),
                "border": QColor("#d4d4d8"),
                "border_hover": QColor("#a1a1aa"),
            },
            "danger": {
                "bg": QColor("#f4f4f6"),
                "bg_hover": QColor("#141417"),
                "bg_press": QColor("#09090b"),
                "fg": QColor("#52525b"),
                "fg_hover": QColor("#ffffff"),
                "border": QColor("#d4d4d8"),
                "border_hover": QColor("#141417"),
            },
            "copied": {
                "bg": QColor("#ffffff"),
                "bg_hover": QColor("#ffffff"),
                "bg_press": QColor("#f4f4f6"),
                "fg": QColor("#141417"),
                "fg_hover": QColor("#141417"),
                "border": QColor("#ffffff"),
                "border_hover": QColor("#ffffff"),
            },
        },
    }

    def __init__(self, text: str = "", variant: str = "dark", radius: int = 8, font_size: int = 12, padding: str = "6px 14px", parent=None):
        super().__init__(text, parent)
        self._theme = "dark"
        self._variant = variant
        self._radius = float(radius)
        self._font_size = font_size
        self._hover_t = 0.0
        self._press_t = 0.0
        self._pad_v, self._pad_h = self._parse_padding(padding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        f = self.font()
        f.setPixelSize(self._font_size)
        f.setWeight(QFont.Weight.DemiBold)
        self.setFont(f)

        self._hover_anim = HighHzAnimator(duration_ms=150, easing=ease_out_cubic, parent=self)
        self._hover_anim.valueChanged.connect(self._on_hover_changed)

        self._press_anim = HighHzAnimator(duration_ms=90, easing=ease_out_quad, parent=self)
        self._press_anim.valueChanged.connect(self._on_press_changed)

    @staticmethod
    def _parse_padding(padding: str):
        parts = [p.replace("px", "").strip() for p in padding.split() if p.strip()]
        try:
            if len(parts) >= 2:
                return int(parts[0]), int(parts[1])
            if len(parts) == 1:
                return int(parts[0]), int(parts[0])
        except ValueError:
            pass
        return 6, 14

    def sizeHint(self) -> QSize:
        fm = QFontMetricsF(self.font())
        tw = int(math.ceil(fm.horizontalAdvance(self.text())))
        th = int(math.ceil(fm.height()))
        return QSize(tw + self._pad_h * 2 + 4, th + self._pad_v * 2 + 2)

    def set_theme(self, theme: str):
        self._theme = "light" if theme == "light" else "dark"
        self.update()

    def set_variant(self, variant: str):
        self._variant = variant
        self.update()

    def _on_hover_changed(self, val: float):
        self._hover_t = float(val)
        self.update()

    def _on_press_changed(self, val: float):
        self._press_t = float(val)
        self.update()

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        if not enabled:
            self._hover_anim.stop()
            self._press_anim.stop()
            self._hover_t = 0.0
            self._press_t = 0.0
        self.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.isEnabled():
            self._hover_anim.start(self._hover_t, 1.0)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._hover_anim.start(self._hover_t, 0.0)
        if self._press_t > 0.0:
            self._press_anim.start(self._press_t, 0.0)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._press_anim.start(self._press_t, 1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_anim.start(self._press_t, 0.0)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        theme_map = self.THEME_PALETTES.get(self._theme, self.THEME_PALETTES["dark"])
        pal = theme_map.get(self._variant, theme_map["dark"])

        if not self.isEnabled():
            if self._variant == "dock_action" or self._theme == "dark":
                bg = QColor("#18181c")
                fg = QColor("#52525b")
                border = QColor("#27272a")
            else:
                bg = QColor("#e4e4e7")
                fg = QColor("#a1a1aa")
                border = QColor("#d4d4d8")
        else:
            bg = lerp_color(pal["bg"], pal["bg_hover"], self._hover_t)
            if self._press_t > 0.01:
                bg = lerp_color(bg, pal["bg_press"], self._press_t)
            fg = lerp_color(pal["fg"], pal["fg_hover"], self._hover_t)
            border = lerp_color(pal["border"], pal["border_hover"], self._hover_t)

        painter.setPen(QPen(border, 1.0))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, self._radius, self._radius)

        painter.setFont(self.font())
        painter.setPen(fg)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())


class AnimatedLineEdit(QLineEdit):
    """
    Monochrome QLineEdit with 180Hz QPainter border & background transitions on hover and focus.
    Uses a static transparent stylesheet so focus/hover never trigger CSS re-parsing.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"
        self._focus_t = 0.0
        self._hover_t = 0.0

        self._focus_anim = HighHzAnimator(duration_ms=160, easing=ease_out_cubic, parent=self)
        self._focus_anim.valueChanged.connect(self._on_focus_changed)

        self._hover_anim = HighHzAnimator(duration_ms=140, easing=ease_out_cubic, parent=self)
        self._hover_anim.valueChanged.connect(self._on_hover_changed)

        self._apply_static_theme_qss()

    def set_theme(self, theme: str):
        self._theme = "light" if theme == "light" else "dark"
        self._apply_static_theme_qss()
        self.update()

    def _apply_static_theme_qss(self):
        if self._theme == "dark":
            self.setStyleSheet(
                "QLineEdit { background: transparent; color: #f4f4f6; border: none; "
                "padding: 6px 11px; font-size: 13px; font-weight: 500; "
                "selection-background-color: #f4f4f6; selection-color: #141417; }"
            )
        else:
            self.setStyleSheet(
                "QLineEdit { background: transparent; color: #141417; border: none; "
                "padding: 6px 11px; font-size: 13px; font-weight: 500; "
                "selection-background-color: #141417; selection-color: #ffffff; }"
            )

    def _on_focus_changed(self, val: float):
        self._focus_t = float(val)
        self.update()

    def _on_hover_changed(self, val: float):
        self._hover_t = float(val)
        self.update()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._focus_anim.start(self._focus_t, 1.0)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._focus_anim.start(self._focus_t, 0.0)

    def enterEvent(self, event):
        super().enterEvent(event)
        self._hover_anim.start(self._hover_t, 1.0)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._hover_anim.start(self._hover_t, 0.0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        t = max(self._focus_t, self._hover_t * 0.45)
        if self._theme == "dark":
            bg = lerp_color(QColor("#18181c"), QColor("#1f1f26"), self._focus_t)
            border = lerp_color(QColor("#2c2c35"), QColor("#f4f4f6"), t)
        else:
            bg = lerp_color(QColor("#f4f4f6"), QColor("#ffffff"), self._focus_t)
            border = lerp_color(QColor("#d4d4d8"), QColor("#141417"), t)

        rect = QRectF(0.75, 0.75, self.width() - 1.5, self.height() - 1.5)
        painter.setPen(QPen(border, 1.5))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 8.0, 8.0)
        painter.end()

        super().paintEvent(event)


class _DropdownItemButton(QPushButton):
    """Single item row inside DownwardDropdown popup rendered via 180Hz QPainter."""

    def __init__(self, text: str, index: int, is_selected: bool = False, theme: str = "dark", parent=None):
        super().__init__(text, parent)
        self.item_index = index
        self.is_selected = is_selected
        self._theme = theme
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover_t = 0.0

        f = self.font()
        f.setPixelSize(12)
        f.setWeight(QFont.Weight.Bold if is_selected else QFont.Weight.Medium)
        self.setFont(f)

        self._anim = HighHzAnimator(duration_ms=130, easing=ease_out_quad, parent=self)
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, val: float):
        self._hover_t = float(val)
        self.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._anim.start(self._hover_t, 1.0)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._anim.start(self._hover_t, 0.0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        t = self._hover_t
        if self._theme == "dark":
            if self.is_selected:
                bg = lerp_color(QColor("#f4f4f6"), QColor("#ffffff"), t)
                fg = QColor("#141417")
            else:
                bg = lerp_color(QColor("#18181c"), QColor("#27272f"), t)
                fg = QColor("#f4f4f6")
        else:
            if self.is_selected:
                bg = lerp_color(QColor("#141417"), QColor("#27272a"), t)
                fg = QColor("#ffffff")
            else:
                bg = lerp_color(QColor("#ffffff"), QColor("#efeff2"), t)
                fg = QColor("#18181b")

        rect = QRectF(0.0, 0.0, float(self.width()), float(self.height()))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 6.0, 6.0)

        painter.setFont(self.font())
        painter.setPen(fg)
        text_rect = QRectF(10.0, 0.0, self.width() - 20.0, float(self.height()))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())


class _DropdownBackdrop(QWidget):
    """Transparent full-window click catcher to close the downward dropdown when clicking outside."""
    clicked_outside = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.hide()

    def mousePressEvent(self, event):
        self.clicked_outside.emit()
        event.accept()


class _DropdownPopup(QFrame):
    """In-window overlay menu that strictly opens downwards below its anchor widget at 180Hz."""
    item_clicked = pyqtSignal(int)
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropdownPopupCard")
        self._theme = "dark"
        self.hide()

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(5, 5, 5, 5)
        self._layout.setSpacing(2)

        self._height_anim = HighHzAnimator(duration_ms=170, easing=ease_out_cubic, parent=self)
        self._height_anim.valueChanged.connect(self._on_height_step)
        self._target_w = 200
        self._backdrop = None
        self._apply_popup_theme()

    def set_theme(self, theme: str):
        self._theme = "light" if theme == "light" else "dark"
        self._apply_popup_theme()

    def _apply_popup_theme(self):
        if self._theme == "dark":
            self.setStyleSheet(
                "QFrame#DropdownPopupCard { background-color: #18181c; border: 1.5px solid #3f3f4a; border-radius: 9px; }"
            )
        else:
            self.setStyleSheet(
                "QFrame#DropdownPopupCard { background-color: #ffffff; border: 1.5px solid #141417; border-radius: 9px; }"
            )

    def _on_height_step(self, val: float):
        self.setFixedSize(self._target_w, max(1, int(val)))

    def show_below(self, anchor: QWidget, items: list, current_index: int):
        top_win = anchor.window()
        if self.parentWidget() != top_win:
            self.setParent(top_win)
        if not self._backdrop or self._backdrop.parentWidget() != top_win:
            self._backdrop = _DropdownBackdrop(top_win)
            self._backdrop.clicked_outside.connect(self.close_popup)

        self._backdrop.setGeometry(top_win.rect())
        self._backdrop.show()
        self._backdrop.raise_()

        while self._layout.count():
            child = self._layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for idx, text in enumerate(items):
            btn = _DropdownItemButton(text, idx, is_selected=(idx == current_index), theme=self._theme, parent=self)
            btn.clicked.connect(lambda checked=False, i=idx: self._select(i))
            self._layout.addWidget(btn)

        self._target_w = anchor.width()
        target_h = min(210, len(items) * 36 + 10)

        win_pos = anchor.mapTo(top_win, QPoint(0, anchor.height() + 4))
        self.move(win_pos)
        self.setFixedSize(self._target_w, 4)
        self.show()
        self.raise_()

        self._height_anim.start(4.0, float(target_h))

    def close_popup(self):
        self._height_anim.stop()
        if self._backdrop:
            self._backdrop.hide()
        self.hide()
        self.closed.emit()

    def _select(self, index: int):
        self.close_popup()
        self.item_clicked.emit(index)


class DownwardDropdown(QWidget):
    """
    Custom monochrome dropdown selector that strictly opens downwards with 180Hz animations.
    Drop-in replacement for QComboBox methods used in ServerConfigPage.
    """
    currentIndexChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._theme = "dark"
        self._items = []
        self._current_index = -1
        self._hover_t = 0.0
        self._chevron_t = 0.0  # 0.0 closed -> 1.0 open

        self._hover_anim = HighHzAnimator(duration_ms=150, easing=ease_out_cubic, parent=self)
        self._hover_anim.valueChanged.connect(self._on_hover_step)

        self._chevron_anim = HighHzAnimator(duration_ms=170, easing=ease_out_cubic, parent=self)
        self._chevron_anim.valueChanged.connect(self._on_chevron_step)

        self._popup = _DropdownPopup(self)
        self._popup.item_clicked.connect(self._on_popup_item_clicked)
        self._popup.closed.connect(self._on_popup_closed)

    def set_theme(self, theme: str):
        self._theme = "light" if theme == "light" else "dark"
        self._popup.set_theme(self._theme)
        self.update()

    def _on_hover_step(self, val: float):
        self._hover_t = float(val)
        self.update()

    def _on_chevron_step(self, val: float):
        self._chevron_t = float(val)
        self.update()

    def clear(self):
        self._items.clear()
        self._current_index = -1
        self.update()

    def addItem(self, text: str):
        self._items.append(str(text))
        if self._current_index < 0:
            self._current_index = 0
        self.update()

    def currentIndex(self) -> int:
        return self._current_index

    def setCurrentIndex(self, index: int):
        if 0 <= index < len(self._items):
            changed = (self._current_index != index)
            self._current_index = index
            self.update()
            if changed and not self.signalsBlocked():
                self.currentIndexChanged.emit(index)

    def _on_popup_item_clicked(self, index: int):
        self.setCurrentIndex(index)

    def _on_popup_closed(self):
        self._chevron_anim.start(self._chevron_t, 0.0)

    def enterEvent(self, event):
        super().enterEvent(event)
        self._hover_anim.start(self._hover_t, 1.0)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._hover_anim.start(self._hover_t, 0.0)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._items:
            if self._popup.isVisible():
                self._popup.close_popup()
            else:
                self._chevron_anim.start(self._chevron_t, 1.0)
                self._popup.show_below(self, self._items, self._current_index)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rect = QRectF(0.75, 0.75, self.width() - 1.5, self.height() - 1.5)
        t = max(self._hover_t * 0.6, self._chevron_t)
        if self._theme == "dark":
            bg = lerp_color(QColor("#18181c"), QColor("#1f1f26"), self._chevron_t)
            border = lerp_color(QColor("#2c2c35"), QColor("#f4f4f6"), t)
            fg = QColor("#f4f4f6")
        else:
            bg = lerp_color(QColor("#f4f4f6"), QColor("#ffffff"), self._chevron_t)
            border = lerp_color(QColor("#d4d4d8"), QColor("#141417"), t)
            fg = QColor("#141417")

        painter.setPen(QPen(border, 1.5))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 8.0, 8.0)

        # Current item text
        text = self._items[self._current_index] if (0 <= self._current_index < len(self._items)) else ""
        painter.setPen(fg)
        font = self.font()
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)

        text_rect = QRectF(12.0, 0.0, self.width() - 38.0, self.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

        # Animated Chevron
        cx = self.width() - 18.0
        cy = self.height() / 2.0
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(180.0 * self._chevron_t)
        pen = QPen(fg, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        path = QPainterPath()
        path.moveTo(-4.5, -2.0)
        path.lineTo(0.0, 2.5)
        path.lineTo(4.5, -2.0)
        painter.drawPath(path)
        painter.restore()


class _StackTransitionOverlay(QWidget):
    """
    180Hz dual-pixmap slide + cross-fade overlay for AnimatedStack.
    Paints a solid theme background first so the previous page's bottom dock NEVER bleeds through.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curr_pix = None
        self._next_pix = None
        self._direction = 1
        self._progress = 0.0
        self._bg_color = QColor("#0c0c0e")
        self.hide()

    def set_bg_color(self, color: QColor):
        self._bg_color = QColor(color)

    def start_frame(self, curr_pix: QPixmap, next_pix: QPixmap, direction: int):
        self._curr_pix = curr_pix
        self._next_pix = next_pix
        self._direction = direction
        self._progress = 0.0
        self.show()
        self.raise_()
        self.update()

    def set_progress(self, t: float):
        self._progress = max(0.0, min(1.0, float(t)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Solid window canvas background prevents any bleed-through
        painter.fillRect(self.rect(), self._bg_color)

        t = self._progress
        slide_dist = 28.0 * self._direction

        if self._curr_pix and not self._curr_pix.isNull():
            painter.save()
            painter.setOpacity(max(0.0, 1.0 - t * 1.15))
            curr_x = -slide_dist * t
            painter.drawPixmap(QPointF(curr_x, 0.0), self._curr_pix)
            painter.restore()

        if self._next_pix and not self._next_pix.isNull():
            painter.save()
            painter.setOpacity(min(1.0, t * 1.1))
            next_x = slide_dist * (1.0 - t)
            painter.drawPixmap(QPointF(next_x, 0.0), self._next_pix)
            painter.restore()


class AnimatedStack(QStackedWidget):
    """
    QStackedWidget with 180Hz dual-pixmap horizontal slide + opacity cross-fade transitions.
    Immediately switches the active page and composites snapshots over a solid canvas so
    widgets from the previous page (like server_card) never linger underneath.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._overlay = _StackTransitionOverlay(self)
        self._anim = HighHzAnimator(duration_ms=200, easing=ease_out_cubic, parent=self)
        self._anim.valueChanged.connect(self._overlay.set_progress)
        self._anim.finished.connect(self._on_transition_done)

    def set_theme(self, theme: str):
        bg = QColor("#efeff2") if theme == "light" else QColor("#0c0c0e")
        self._overlay.set_bg_color(bg)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())

    def slide_to(self, index: int):
        if index == self.currentIndex() or index < 0 or index >= self.count():
            return
        self._anim.stop()

        curr_w = self.currentWidget()
        next_w = self.widget(index)
        direction = 1 if index > self.currentIndex() else -1

        rect = self.rect()
        curr_w.setGeometry(rect)
        curr_pix = curr_w.grab()

        # Immediately switch to next_w so curr_w is hidden right away
        self.setCurrentIndex(index)
        next_w.setGeometry(rect)
        next_w.repaint()
        next_pix = next_w.grab()

        self._overlay.setGeometry(rect)
        self._overlay.start_frame(curr_pix, next_pix, direction)
        self._anim.start(0.0, 1.0)

    def _on_transition_done(self):
        self._overlay.hide()
