"""
Dashboard Chart Widgets
Custom high-DPI micro-visualizations inspired by the analytics dashboard reference:
- SegmentedProgressBar (Horizontal progress/distribution bar with lime-green, amber, coral)
- SparklineChart (Smooth trend/curve chart with purple accent line and gradient fill)
- MiniBarChart (Vertical category distribution bars with lime-green highlights)
"""

from typing import List, Tuple, Optional
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QColor, QBrush, QLinearGradient, QPainterPath,
    QFont, QFontMetrics
)


class SegmentedProgressBar(QWidget):
    """
    Horizontal distribution bar rendering Pass (lime-green), Warning (amber),
    and Failure (coral) segments with a custom floating pill callout tag.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.passed: int = 0
        self.warned: int = 0
        self.failed: int = 0
        self.callout_text: str = ""

    def set_values(self, passed: int, warned: int, failed: int, callout: str = ""):
        self.passed = max(0, passed)
        self.warned = max(0, warned)
        self.failed = max(0, failed)
        self.callout_text = callout
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        bar_h = 14.0
        bar_y = 6.0

        total = self.passed + self.warned + self.failed
        if total == 0:
            # Empty / placeholder track
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, bar_y, w, bar_h), 7.0, 7.0)
            painter.fillPath(path, QColor("#e2e8f0"))
            painter.end()
            return

        pass_w = (self.passed / total) * w
        warn_w = (self.warned / total) * w
        fail_w = (self.failed / total) * w

        # Draw rounded clip path for the whole bar
        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(0, bar_y, w, bar_h), 7.0, 7.0)
        painter.setClipPath(clip_path)

        # 1. Pass segment: vibrant lime-green (#84cc16 to #65a30d)
        curr_x = 0.0
        if pass_w > 0:
            grad_pass = QLinearGradient(curr_x, bar_y, curr_x + pass_w, bar_y)
            grad_pass.setColorAt(0.0, QColor("#84cc16"))
            grad_pass.setColorAt(1.0, QColor("#65a30d"))
            painter.fillRect(QRectF(curr_x, bar_y, pass_w, bar_h), grad_pass)
            curr_x += pass_w

        # 2. Warning segment: warm amber/gold (#f59e0b)
        if warn_w > 0:
            painter.fillRect(QRectF(curr_x, bar_y, warn_w, bar_h), QColor("#fbbf24"))
            curr_x += warn_w

        # 3. Fail segment: coral/soft red (#f87171)
        if fail_w > 0:
            painter.fillRect(QRectF(curr_x, bar_y, fail_w, bar_h), QColor("#f87171"))

        painter.setClipping(False)

        # Small tick marks / scale underneath
        painter.setPen(QPen(QColor("#94a3b8"), 1))
        tick_y = bar_y + bar_h + 3
        for i in range(5):
            tx = i * (w / 4)
            painter.drawLine(int(tx), int(tick_y), int(tx), int(tick_y + 3))

        painter.end()


class SparklineChart(QWidget):
    """
    Smooth curve / step chart with purple accent line (#8b5cf6), gradient area fill,
    and a styled callout pill badge matching Card 2 in the reference design.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(95)
        self.data_points: List[float] = [10, 15, 22, 28, 45, 62, 78, 92]
        self.badge_text: str = ""

    def set_data(self, points: List[float], badge_text: str = ""):
        if points:
            self.data_points = points
        self.badge_text = badge_text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        margin_x = 8.0
        margin_y = 12.0
        plot_w = w - (margin_x * 2)
        plot_h = h - (margin_y * 2)

        if len(self.data_points) < 2:
            painter.end()
            return

        min_val = min(self.data_points)
        max_val = max(self.data_points)
        if max_val == min_val:
            max_val += 1.0

        pts: List[QPointF] = []
        n = len(self.data_points)
        for i, val in enumerate(self.data_points):
            x = margin_x + (i / (n - 1)) * plot_w
            norm = (val - min_val) / (max_val - min_val)
            y = (margin_y + plot_h) - (norm * plot_h)
            pts.append(QPointF(x, y))

        # Build smooth path
        path = QPainterPath()
        path.moveTo(pts[0])
        for i in range(len(pts) - 1):
            p0 = pts[i]
            p1 = pts[i + 1]
            c1 = QPointF((p0.x() + p1.x()) / 2, p0.y())
            c2 = QPointF((p0.x() + p1.x()) / 2, p1.y())
            path.cubicTo(c1, c2, p1)

        # Gradient area fill underneath curve
        fill_path = QPainterPath(path)
        fill_path.lineTo(pts[-1].x(), h - margin_y)
        fill_path.lineTo(pts[0].x(), h - margin_y)
        fill_path.closeSubpath()

        grad = QLinearGradient(0, margin_y, 0, h - margin_y)
        grad.setColorAt(0.0, QColor(139, 92, 246, 60))   # Purple with alpha
        grad.setColorAt(1.0, QColor(139, 92, 246, 2))
        painter.fillPath(fill_path, grad)

        # Purple curve line
        pen = QPen(QColor("#8b5cf6"), 2.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

        # Draw highlight dot at the last point
        last_pt = pts[-1]
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#7c3aed"), 2.5))
        painter.drawEllipse(last_pt, 4.0, 4.0)

        # Draw callout pill badge if available
        if self.badge_text:
            font = QFont("Segoe UI", 8, QFont.Bold)
            painter.setFont(font)
            fm = QFontMetrics(font)
            bw = fm.horizontalAdvance(self.badge_text) + 14
            bh = 20.0
            bx = max(margin_x, min(w - bw - margin_x, last_pt.x() - bw / 2))
            by = max(4.0, last_pt.y() - bh - 6)

            badge_rect = QRectF(bx, by, bw, bh)
            badge_path = QPainterPath()
            badge_path.addRoundedRect(badge_rect, 10.0, 10.0)
            painter.fillPath(badge_path, QColor("#1e1b4b"))  # Dark indigo
            painter.setPen(QColor("#c4b5fd"))               # Soft lavender
            painter.drawText(badge_rect, Qt.AlignCenter, self.badge_text)

        painter.end()


class MiniBarChart(QWidget):
    """
    Vertical bar chart with lime-green gradient bars to soft grey
    representing category health, matching Card 3 in the reference design.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(95)
        self.values: List[float] = [0.4, 0.6, 0.75, 0.85, 0.95, 0.8, 0.9, 0.7, 0.5]

    def set_values(self, values: List[float]):
        if values:
            self.values = values
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        margin_x = 6.0
        margin_b = 6.0
        margin_t = 10.0
        avail_h = h - margin_t - margin_b

        n = len(self.values)
        if n == 0:
            painter.end()
            return

        spacing = 5.0
        total_spacing = spacing * (n - 1)
        bar_w = max(5.0, (w - 2 * margin_x - total_spacing) / n)

        for i, val in enumerate(self.values):
            norm = min(1.0, max(0.05, float(val)))
            bh = norm * avail_h
            bx = margin_x + i * (bar_w + spacing)
            by = h - margin_b - bh

            rect = QRectF(bx, by, bar_w, bh)
            b_path = QPainterPath()
            b_path.addRoundedRect(rect, 3.0, 3.0)

            # Highlight higher values in lime green, lower in muted slate
            if norm >= 0.7:
                grad = QLinearGradient(bx, by, bx, by + bh)
                grad.setColorAt(0.0, QColor("#a3e635"))  # Lime 400
                grad.setColorAt(1.0, QColor("#65a30d"))  # Lime 600
                painter.fillPath(b_path, grad)
            elif norm >= 0.4:
                painter.fillPath(b_path, QColor("#cbd5e1"))
            else:
                painter.fillPath(b_path, QColor("#e2e8f0"))

        painter.end()
