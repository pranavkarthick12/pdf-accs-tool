"""
Batch Scan View
Scans multiple PDF documents in a directory and produces an aggregated compliance report.
"""

from typing import List, Dict, Any, Optional
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QProgressBar, QLabel
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from ...core.document_parser import DocumentParser
from ...core.models import CheckStatus
from ...engine.runner import AuditRunner
from ..widgets.status_badge import StatusColors


class BatchScanView(QWidget):
    """View for scanning folders of PDF documents."""

    document_opened = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.runner = AuditRunner()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Top bar
        top_layout = QHBoxLayout()
        self.btn_select_folder = QPushButton("📁 Select Folder to Batch Scan")
        self.btn_select_folder.setObjectName("primaryBtn")
        self.btn_select_folder.clicked.connect(self._select_folder)
        top_layout.addWidget(self.btn_select_folder)

        self.lbl_status = QLabel("Select a directory containing PDF files.")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 12px;")
        top_layout.addWidget(self.lbl_status)
        top_layout.addStretch()

        layout.addLayout(top_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Batch results table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Filename", "Score", "Tagged", "Passed", "Warnings", "Failures"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.itemDoubleClicked.connect(self._on_row_double_click)
        layout.addWidget(self.table)

    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing PDFs")
        if folder:
            self.scan_folder(folder)

    def scan_folder(self, folder: str) -> List[Dict[str, Any]]:
        """Scans a directory of PDF files and displays aggregate results."""
        if not os.path.exists(folder):
            self.lbl_status.setText(f"Directory not found: {folder}")
            return []

        pdf_files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".pdf")]
        results = []
        if not pdf_files:
            self.lbl_status.setText(f"No PDF files found in {folder}.")
            return results

        self.lbl_status.setText(f"Scanning {len(pdf_files)} PDF file(s)...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(pdf_files))
        self.progress_bar.setValue(0)

        self.table.setRowCount(len(pdf_files))
        for idx, pdf_path in enumerate(pdf_files):
            filename = os.path.basename(pdf_path)
            res_item = {"filename": filename, "filepath": pdf_path}
            try:
                parser = DocumentParser(pdf_path)
                doc = parser.parse()
                report = self.runner.run(doc)

                res_item.update({
                    "score": report.compliance_score,
                    "is_tagged": doc.is_tagged,
                    "passed": report.total_passed,
                    "warned": report.total_warned,
                    "failed": report.total_failed,
                    "status": "Success"
                })

                self.table.setItem(idx, 0, QTableWidgetItem(filename))
                
                item_score = QTableWidgetItem(f"{report.compliance_score}%")
                item_score.setTextAlignment(Qt.AlignCenter)
                item_score.setFont(QFont("Segoe UI", 9, QFont.Bold))
                self.table.setItem(idx, 1, item_score)

                item_tagged = QTableWidgetItem("Yes" if doc.is_tagged else "No")
                item_tagged.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(idx, 2, item_tagged)

                item_p = QTableWidgetItem(str(report.total_passed))
                item_p.setTextAlignment(Qt.AlignCenter)
                item_p.setForeground(StatusColors.get_status_color(CheckStatus.PASS))
                item_p.setFont(QFont("Segoe UI", 9, QFont.Bold))
                self.table.setItem(idx, 3, item_p)

                item_w = QTableWidgetItem(str(report.total_warned))
                item_w.setTextAlignment(Qt.AlignCenter)
                item_w.setForeground(StatusColors.get_status_color(CheckStatus.WARNING))
                item_w.setFont(QFont("Segoe UI", 9, QFont.Bold))
                self.table.setItem(idx, 4, item_w)

                item_f = QTableWidgetItem(str(report.total_failed))
                item_f.setTextAlignment(Qt.AlignCenter)
                item_f.setForeground(StatusColors.get_status_color(CheckStatus.FAIL))
                item_f.setFont(QFont("Segoe UI", 9, QFont.Bold))
                self.table.setItem(idx, 5, item_f)

                self.table.item(idx, 0).setData(Qt.UserRole, pdf_path)
            except Exception as e:
                res_item.update({"status": f"Error: {e}", "score": 0.0, "is_tagged": False, "passed": 0, "warned": 0, "failed": 0})
                self.table.setItem(idx, 0, QTableWidgetItem(f"{filename} (Error)"))
                self.table.setItem(idx, 1, QTableWidgetItem("Err"))
                self.table.setItem(idx, 2, QTableWidgetItem("N/A"))
                self.table.setItem(idx, 3, QTableWidgetItem("0"))
                self.table.setItem(idx, 4, QTableWidgetItem("0"))
                self.table.setItem(idx, 5, QTableWidgetItem("0"))

            results.append(res_item)
            self.progress_bar.setValue(idx + 1)

        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"Completed scanning {len(pdf_files)} PDF file(s). Double-click a row to open.")
        return results

    def _on_row_double_click(self, item):
        row = item.row()
        item_zero = self.table.item(row, 0)
        if item_zero:
            pdf_path = item_zero.data(Qt.UserRole)
            if pdf_path and os.path.exists(pdf_path):
                self.document_opened.emit(pdf_path)
