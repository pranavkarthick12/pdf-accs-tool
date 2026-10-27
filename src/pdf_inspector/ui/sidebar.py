"""
Sidebar Navigation
Left navigation panel providing access to Dashboard, Checkpoints, Tag Tree,
Screen Reader preview, Metadata, Statistics, Elements, and Reports.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel,
    QFrame
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QIcon, QFont


class Sidebar(QWidget):
    """Sidebar navigation list widget."""

    page_selected = Signal(str)

    NAV_ITEMS = [
        ("Dashboard", "🏠 Dashboard"),
        ("Checkpoints", "✅ Checkpoints (PAC Matrix)"),
        ("Detailed Findings", "📋 Detailed Results"),
        ("PDF Viewer", "🔍 Integrated PDF Viewer"),
        ("Document Metadata", "ℹ️ Document & Metadata"),
        ("Statistics", "📊 Statistics & Health"),
        ("Fonts", "🔤 Font Assets"),
        ("Images", "🖼️ Image & Figures"),
        ("Tables", "📊 Table Structures"),
        ("Links", "🔗 Hyperlinks"),
        ("Forms", "📝 Form Fields"),
        ("Bookmarks", "🔖 Bookmarks & Outline"),
        ("Batch Scan", "📁 Batch Folder Scanner"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("leftSidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._init_ui()

    def _init_ui(self):
        self.setMinimumWidth(220)
        self.setMaximumWidth(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header section
        lbl_section = QLabel("NAVIGATION")
        lbl_section.setObjectName("sidebarHeaderLabel")
        layout.addWidget(lbl_section)

        divider = QFrame()
        divider.setObjectName("sidebarDivider")
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("sidebarList")
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollPerPixel)

        for key, label in self.NAV_ITEMS:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            self.list_widget.addItem(item)

        self.list_widget.setCurrentRow(0)
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self.list_widget)

    def _on_row_changed(self, row: int):
        item = self.list_widget.item(row)
        if item:
            key = item.data(Qt.UserRole)
            self.page_selected.emit(key)

    def select_page(self, key_name: str):
        """Programmatically selects a navigation item."""
        target = "Semantic Reading Preview" if key_name == "Screen Reader" else key_name
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item and item.data(Qt.UserRole) in (target, key_name):
                if self.list_widget.currentRow() != row:
                    self.list_widget.setCurrentRow(row)
                break
