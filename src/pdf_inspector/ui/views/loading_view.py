"""
Loading View
Enterprise loading & validation view displayed in the center of the application
while a PDF document is actively being analyzed and audited.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QFrame, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QFont


class LoadingSpinner(QWidget):
    """
    High-performance, anti-aliased rotating spinner.
    Renders an elegant circular track and rotating arc matching the application theme.
    """

    def __init__(self, parent=None, size: int = 56):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(25)  # 40 fps for smooth rotation
        self._timer.timeout.connect(self._rotate)

    def _rotate(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def start(self):
        self._angle = 0
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        side = min(width, height)
        pen_width = 4.0
        rect = QRectF(pen_width, pen_width, side - 2 * pen_width, side - 2 * pen_width)

        # Muted circular track
        track_pen = QPen(QColor("#e2e8f0"), pen_width)
        track_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(track_pen)
        painter.drawEllipse(rect)

        # Active rotating arc
        arc_pen = QPen(QColor("#2563eb"), pen_width)
        arc_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(arc_pen)

        # Start and span angles in 1/16th of a degree
        start_angle = int(-self._angle * 16)
        span_angle = int(-100 * 16)
        painter.drawArc(rect, start_angle, span_angle)

        painter.end()


class LoadingView(QWidget):
    """
    Enterprise Loading & Validation View.
    Displayed prominently in the center of the application while a PDF document
    is actively being analyzed and audited.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        self.setObjectName("loadingView")
        self.setStyleSheet("QWidget#loadingView { background-color: #f8fafc; }")

        # Root layout centering the card vertically & horizontally
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setAlignment(Qt.AlignCenter)

        # Elevated Card Frame
        self.card = QFrame()
        self.card.setObjectName("loadingCard")
        self.card.setMinimumWidth(440)
        self.card.setMaximumWidth(520)
        self.card.setStyleSheet("""
            QFrame#loadingCard {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }
        """)

        # Soft, modern drop shadow
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(15, 23, 42, 22))
        shadow.setOffset(0, 8)
        self.card.setGraphicsEffect(shadow)

        # Card Content Layout
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(36, 32, 36, 32)
        card_layout.setSpacing(14)
        card_layout.setAlignment(Qt.AlignCenter)

        # 1. Animated Spinner
        self.spinner = LoadingSpinner(self.card, size=56)
        card_layout.addWidget(self.spinner, alignment=Qt.AlignCenter)

        # 2. Title & Subtitle
        self.lbl_title = QLabel("Validating Document")
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet("font-size: 19px; font-weight: 700; color: #0f172a; margin-top: 4px;")
        card_layout.addWidget(self.lbl_title)

        self.lbl_subtitle = QLabel("PDF Accessibility & Standards Inspection")
        self.lbl_subtitle.setAlignment(Qt.AlignCenter)
        self.lbl_subtitle.setStyleSheet("font-size: 12px; color: #64748b; margin-bottom: 2px;")
        card_layout.addWidget(self.lbl_subtitle)

        # 3. Filename Chip
        self.lbl_filename = QLabel("📄 document.pdf")
        self.lbl_filename.setAlignment(Qt.AlignCenter)
        self.lbl_filename.setStyleSheet("""
            QLabel {
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 12px;
                padding: 4px 14px;
                font-size: 12px;
                font-weight: 600;
                color: #334155;
            }
        """)
        card_layout.addWidget(self.lbl_filename, alignment=Qt.AlignCenter)

        card_layout.addSpacing(6)

        # 4. Status Stage Message
        self.lbl_stage = QLabel("Parsing PDF structure and dictionaries...")
        self.lbl_stage.setAlignment(Qt.AlignCenter)
        self.lbl_stage.setStyleSheet("font-size: 13px; font-weight: 500; color: #334155;")
        self.lbl_stage.setWordWrap(True)
        card_layout.addWidget(self.lbl_stage)

        # 5. Progress Header (Label + Percentage)
        progress_header = QHBoxLayout()
        progress_header.setContentsMargins(0, 4, 0, 0)

        lbl_progress_title = QLabel("VALIDATION PROGRESS")
        lbl_progress_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b; letter-spacing: 0.5px;")
        progress_header.addWidget(lbl_progress_title)
        progress_header.addStretch()

        self.lbl_percent = QLabel("0%")
        self.lbl_percent.setStyleSheet("font-size: 13px; font-weight: 700; color: #2563eb;")
        progress_header.addWidget(self.lbl_percent)
        card_layout.addLayout(progress_header)

        # 6. High-Contrast Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 10)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #e2e8f0;
                border: none;
                border-radius: 5px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6);
                border-radius: 5px;
            }
        """)
        card_layout.addWidget(self.progress_bar)

        card_layout.addSpacing(6)

        # 7. Checkpoint Standard Badges
        badges_layout = QHBoxLayout()
        badges_layout.setSpacing(6)
        badges_layout.setAlignment(Qt.AlignCenter)

        standards = [
            ("🛡️ PDF/UA-1", "ISO 14289-1 Standard"),
            ("♿ WCAG 2.1 AA", "Web Content Accessibility Guidelines"),
            ("📋 Quality", "Matterhorn Protocol Quality Rules"),
        ]
        for name, tip in standards:
            badge = QLabel(name)
            badge.setToolTip(tip)
            badge.setStyleSheet("""
                QLabel {
                    background-color: #eff6ff;
                    border: 1px solid #bfdbfe;
                    border-radius: 6px;
                    padding: 3px 8px;
                    font-size: 11px;
                    font-weight: 600;
                    color: #1e40af;
                }
            """)
            badges_layout.addWidget(badge)

        card_layout.addLayout(badges_layout)

        # 8. Micro-subtext reassurance
        lbl_hint = QLabel("Evaluating 41 comprehensive accessibility checkpoints...")
        lbl_hint.setAlignment(Qt.AlignCenter)
        lbl_hint.setStyleSheet("font-size: 11px; color: #94a3b8;")
        card_layout.addWidget(lbl_hint)

        main_layout.addWidget(self.card)

    def start(self, filename: str):
        """Starts spinner animation and initializes progress display."""
        display_name = filename if len(filename) <= 40 else filename[:20] + "..." + filename[-17:]
        self.lbl_filename.setText(f"📄 {display_name}")
        self.lbl_stage.setText("Initializing accessibility audit...")
        self.lbl_percent.setText("0%")
        self.progress_bar.setRange(0, 10)
        self.progress_bar.setValue(0)
        self.spinner.start()

    def set_progress(self, current: int, total: int, msg: str):
        """Updates the progress bar, percentage label, and stage message."""
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            pct = int(min(1.0, max(0.0, current / total)) * 100)
            self.lbl_percent.setText(f"{pct}%")
        self.lbl_stage.setText(msg)

    def stop(self):
        """Stops the animated spinner."""
        self.spinner.stop()
