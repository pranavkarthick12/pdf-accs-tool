"""
Top Navigation Ribbon & Hero Section
Premium, dark-green textured header hero section inspired by the reference design.
Features:
- Organic deep-green gradient background with procedural vertical lighting texture
- Real-time date and contextual greeting / document status
- High-visibility document status pill badges
- Circular glass icon action buttons (Settings, Rescan, Help, About)
- Integrated horizontal navigation strip with active rounded tabs
- Quick action pill buttons (Open PDF, Export Report)
"""

import datetime
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy
)
from PySide6.QtCore import Signal, Qt, QRectF
from PySide6.QtGui import (
    QFont, QPainter, QLinearGradient, QColor, QPen, QBrush
)


class TopBar(QWidget):
    """Modern dark-green hero header and integrated navigation strip."""

    open_pdf_requested = Signal()
    open_folder_requested = Signal()
    batch_scan_requested = Signal()
    rescan_requested = Signal()
    export_report_requested = Signal()
    settings_requested = Signal()
    about_requested = Signal()
    help_requested = Signal()
    navigation_requested = Signal(str)

    NAV_TABS = [
        ("Dashboard", "Overview"),
        ("Checkpoints", "Checkpoints"),
        ("Detailed Findings", "Detailed Findings"),
        ("PDF Viewer", "PDF Viewer"),
        ("Statistics", "Statistics"),
        ("Document Metadata", "Document Info"),
        ("Batch Scan", "Batch Scan"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_tab_key = "Dashboard"
        self._doc_filename: Optional[str] = None
        self._doc_score: Optional[int] = None
        self._doc_status: str = "Ready"
        self.nav_buttons = {}
        self._init_ui()

    def _init_ui(self):
        self.setFixedHeight(138)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 8, 24, 8)
        root_layout.setSpacing(5)

        # 1. Top Row: Date & Actions (Settings, Help, About, Rescan)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)

        now = datetime.datetime.now()
        self.lbl_date = QLabel(now.strftime("%A, %B %d, %Y"))
        self.lbl_date.setStyleSheet("color: rgba(255, 255, 255, 0.72); font-size: 11px; font-weight: 500;")
        top_row.addWidget(self.lbl_date)

        top_row.addStretch()

        # Circular/Pill Glass Action Buttons
        btn_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 14px;
                color: #ffffff;
                font-size: 11px;
                padding: 2px 10px;
                min-height: 24px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.22);
                border-color: rgba(255, 255, 255, 0.35);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.28);
            }
            QPushButton:disabled {
                background-color: rgba(255, 255, 255, 0.05);
                color: rgba(255, 255, 255, 0.3);
                border-color: transparent;
            }
        """

        self.btn_rescan = QPushButton("🔄 Rescan")
        self.btn_rescan.setStyleSheet(btn_style)
        self.btn_rescan.setEnabled(False)
        self.btn_rescan.clicked.connect(self.rescan_requested)
        top_row.addWidget(self.btn_rescan)

        self.btn_settings = QPushButton("⚙️ Settings")
        self.btn_settings.setStyleSheet(btn_style)
        self.btn_settings.clicked.connect(self.settings_requested)
        top_row.addWidget(self.btn_settings)

        self.btn_help = QPushButton("❓ Help")
        self.btn_help.setStyleSheet(btn_style)
        self.btn_help.clicked.connect(self.help_requested)
        top_row.addWidget(self.btn_help)

        self.btn_about = QPushButton("ℹ️ About")
        self.btn_about.setStyleSheet(btn_style)
        self.btn_about.clicked.connect(self.about_requested)
        top_row.addWidget(self.btn_about)

        root_layout.addLayout(top_row)

        # 2. Hero Middle: Title & Status Pills
        mid_row = QHBoxLayout()
        mid_row.setContentsMargins(0, 0, 0, 0)
        mid_row.setSpacing(16)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(1)

        self.lbl_title_main = QLabel("PDF Accessibility")
        self.lbl_title_main.setStyleSheet("color: #ffffff; font-size: 19px; font-weight: 700; line-height: 1.1;")
        title_layout.addWidget(self.lbl_title_main)

        self.lbl_title_sub = QLabel("Inspector")
        self.lbl_title_sub.setStyleSheet("color: #ffffff; font-size: 19px; font-weight: 800; font-style: italic;")
        title_layout.addWidget(self.lbl_title_sub)

        mid_row.addLayout(title_layout)
        mid_row.addSpacing(16)

        # Status Pills layout
        pills_layout = QHBoxLayout()
        pills_layout.setSpacing(8)

        pill_base_style = """
            QLabel {
                background-color: rgba(12, 40, 24, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 12px;
                padding: 4px 12px;
                color: #ffffff;
                font-size: 11px;
                font-weight: 600;
            }
        """

        self.pill_status = QLabel("✦ Status: Ready")
        self.pill_status.setStyleSheet(pill_base_style)
        pills_layout.addWidget(self.pill_status, alignment=Qt.AlignVCenter)

        self.pill_metric = QLabel("◎ 41 Standards Checkpoints")
        self.pill_metric.setStyleSheet(pill_base_style)
        pills_layout.addWidget(self.pill_metric, alignment=Qt.AlignVCenter)

        pills_layout.addStretch()
        mid_row.addLayout(pills_layout)
        mid_row.addStretch()

        root_layout.addLayout(mid_row)
        root_layout.addStretch()

        # 3. Bottom Row: Navigation Tabs (Left) & Quick Action Pills (Right)
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(6)

        # Navigation Bar Tabs Container
        nav_container = QHBoxLayout()
        nav_container.setSpacing(4)

        for key, label in self.NAV_TABS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("nav_key", key)
            if key == "Dashboard":
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, k=key: self._on_tab_clicked(k))
            self.nav_buttons[key] = btn
            nav_container.addWidget(btn)

        self._update_tab_styles()
        bottom_row.addLayout(nav_container)
        bottom_row.addStretch()

        # Right Quick Action Pills
        self.btn_export = QPushButton("📄 Export Report")
        self.btn_export.setEnabled(False)
        self.btn_export.setStyleSheet("""
            QPushButton {
                background-color: rgba(18, 55, 34, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.22);
                border-radius: 15px;
                color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: rgba(28, 75, 48, 0.95);
            }
            QPushButton:disabled {
                background-color: rgba(255, 255, 255, 0.08);
                color: rgba(255, 255, 255, 0.3);
                border-color: transparent;
            }
        """)
        self.btn_export.clicked.connect(self.export_report_requested)
        bottom_row.addWidget(self.btn_export)

        self.btn_open = QPushButton("📂 Open PDF")
        self.btn_open.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #ffffff;
                border-radius: 15px;
                color: #0c2b1c;
                font-size: 12px;
                font-weight: 700;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                color: #064e3b;
            }
            QPushButton:pressed {
                background-color: #e2e8f0;
            }
        """)
        self.btn_open.clicked.connect(self.open_pdf_requested)
        bottom_row.addWidget(self.btn_open)

        root_layout.addLayout(bottom_row)

    def _update_tab_styles(self):
        """Applies high-contrast dark green / semi-transparent active styles to tabs."""
        for key, btn in self.nav_buttons.items():
            if btn.isChecked():
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(10, 35, 20, 0.95);
                        border: 1px solid rgba(255, 255, 255, 0.32);
                        border-radius: 14px;
                        color: #ffffff;
                        font-size: 12px;
                        font-weight: 700;
                        padding: 5px 14px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        border: 1px solid transparent;
                        border-radius: 14px;
                        color: rgba(255, 255, 255, 0.78);
                        font-size: 12px;
                        font-weight: 500;
                        padding: 5px 12px;
                    }
                    QPushButton:hover {
                        background-color: rgba(255, 255, 255, 0.12);
                        color: #ffffff;
                    }
                """)

    def _on_tab_clicked(self, key: str):
        self.active_tab_key = key
        self._update_tab_styles()
        self.navigation_requested.emit(key)

    def select_tab(self, key_name: str):
        """Programmatically select tab without triggering extra recursive signals."""
        target = "Dashboard" if key_name in ("Overview", "Dashboard") else key_name
        if target in self.nav_buttons:
            self.nav_buttons[target].setChecked(True)
            self.active_tab_key = target
            self._update_tab_styles()

    def set_document_loaded(self, loaded: bool):
        self.btn_rescan.setEnabled(loaded)
        self.btn_export.setEnabled(loaded)

    def set_document_info(self, filename: str, score: Optional[int] = None, status: str = "Completed"):
        self._doc_filename = filename
        self._doc_score = score
        self._doc_status = status

        display_name = filename if len(filename) <= 24 else filename[:12] + "..." + filename[-9:]
        self.pill_status.setText(f"📄 {display_name} • {status}")

        if score is not None:
            self.pill_metric.setText(f"✦ Compliance Score: {score}%")
        else:
            self.pill_metric.setText("◎ 41 Standards Checkpoints")

    def paintEvent(self, event):
        """
        Paints a rich, organic dark-green gradient background with
        procedural vertical ribbed / lighting textures matching the reference image.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())

        # Base deep forest gradient (#071e13 -> #0f3521 -> #092015)
        base_grad = QLinearGradient(0, 0, w, h)
        base_grad.setColorAt(0.0, QColor("#082215"))
        base_grad.setColorAt(0.4, QColor("#123824"))
        base_grad.setColorAt(0.7, QColor("#18462d"))
        base_grad.setColorAt(1.0, QColor("#092215"))
        painter.fillRect(QRectF(0, 0, w, h), base_grad)

        # Procedural vertical warm golden-green lighting streaks
        # Mimics the vertical textured ribbing in the reference image
        streak_w = 4.0
        x = 0.0
        pattern = [0.08, 0.16, 0.05, 0.22, 0.12, 0.04, 0.18, 0.28, 0.15, 0.07]
        idx = 0
        while x < w:
            intensity = pattern[idx % len(pattern)]
            # Warm golden/lime highlight (#84cc16 / #65a30d)
            streak_color = QColor(132, 204, 22, int(intensity * 120))
            streak_grad = QLinearGradient(x, 0, x, h)
            streak_grad.setColorAt(0.0, QColor(0, 0, 0, 40))
            streak_grad.setColorAt(0.5, streak_color)
            streak_grad.setColorAt(1.0, QColor(0, 0, 0, 60))

            painter.fillRect(QRectF(x, 0, streak_w, h), streak_grad)
            x += streak_w + (3.0 if idx % 2 == 0 else 6.0)
            idx += 1

        # Subtle bottom vignette to make tabs pop
        bottom_grad = QLinearGradient(0, h - 50, 0, h)
        bottom_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        bottom_grad.setColorAt(1.0, QColor(0, 0, 0, 80))
        painter.fillRect(QRectF(0, h - 50, w, 50), bottom_grad)

        painter.end()
