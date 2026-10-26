"""
Dashboard View
Redesigned modern analytics dashboard inspired by the reference design.
Features:
- Responsive 3-card summary grid matching reference visual style:
  - Card 1: Compliance Health with SegmentedProgressBar
  - Card 2: Findings Breakdown with purple SparklineChart
  - Card 3: Standards Health with vertical MiniBarChart
- Polished "Audit Findings Overview" table matching reference's Product Overview
- Filter controls and black pill Export CSV / Report button
- Clean initial drop zone state before document analysis
"""

from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QScrollArea, QComboBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from ...core.models import AuditReport, PDFDocumentModel, CheckResult, CheckStatus, Severity
from ..widgets.dashboard_charts import SegmentedProgressBar, SparklineChart, MiniBarChart


class DashboardView(QWidget):
    """Executive analytics dashboard view."""

    open_pdf_requested = Signal()
    view_details_requested = Signal()
    view_pdf_requested = Signal()
    export_report_requested = Signal()
    finding_selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_doc: Optional[PDFDocumentModel] = None
        self.current_report: Optional[AuditReport] = None
        self._all_findings: List[CheckResult] = []
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            DashboardView {
                background-color: #f4f6f8;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: #f4f6f8; border: none; }")

        container = QWidget()
        container.setStyleSheet("background-color: #f4f6f8;")
        self.content_layout = QVBoxLayout(container)
        self.content_layout.setContentsMargins(24, 20, 24, 24)
        self.content_layout.setSpacing(20)

        # ---------------------------------------------------------
        # 1. Welcome / Empty Drop Zone Card (visible when no PDF loaded)
        # ---------------------------------------------------------
        self.empty_card = QFrame()
        self.empty_card.setObjectName("dashboardEmptyCard")
        self.empty_card.setStyleSheet("""
            QFrame#dashboardEmptyCard {
                background-color: #ffffff;
                border: 2px dashed #cbd5e1;
                border-radius: 16px;
                padding: 40px;
            }
        """)
        empty_layout = QVBoxLayout(self.empty_card)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(12)

        lbl_icon = QLabel("📄")
        lbl_icon.setStyleSheet("font-size: 46px;")
        lbl_icon.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(lbl_icon)

        self.lbl_empty_title = QLabel("Open a PDF or Drag and Drop Here")
        self.lbl_empty_title.setStyleSheet("font-size: 19px; font-weight: 700; color: #0f172a;")
        self.lbl_empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.lbl_empty_title)

        lbl_empty_sub = QLabel("Analyzes internal PDF structure, PDF/UA (ISO 14289-1), WCAG 2.1/2.2 AA, and generates compliance audits.")
        lbl_empty_sub.setStyleSheet("font-size: 13px; color: #64748b; max-width: 580px;")
        lbl_empty_sub.setAlignment(Qt.AlignCenter)
        lbl_empty_sub.setWordWrap(True)
        empty_layout.addWidget(lbl_empty_sub)

        empty_layout.addSpacing(6)
        self.btn_empty_open = QPushButton("📂 Open PDF Document")
        self.btn_empty_open.setStyleSheet("""
            QPushButton {
                background-color: #0c2b1c;
                border: 1px solid #0c2b1c;
                border-radius: 18px;
                color: #ffffff;
                font-size: 13px;
                font-weight: 700;
                padding: 8px 24px;
            }
            QPushButton:hover {
                background-color: #164e32;
            }
        """)
        self.btn_empty_open.clicked.connect(self.open_pdf_requested)
        empty_layout.addWidget(self.btn_empty_open, alignment=Qt.AlignCenter)

        self.content_layout.addWidget(self.empty_card)

        # ---------------------------------------------------------
        # 2. Top Summary Cards Row (3 Cards matching reference design)
        # ---------------------------------------------------------
        self.cards_row = QHBoxLayout()
        self.cards_row.setSpacing(16)

        card_qss = """
            QFrame.summaryCard {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 14px;
                padding: 16px;
            }
        """

        # Card 1: Compliance Health
        self.card1 = QFrame()
        self.card1.setProperty("class", "summaryCard")
        self.card1.setStyleSheet(card_qss)
        c1_layout = QVBoxLayout(self.card1)
        c1_layout.setContentsMargins(18, 16, 18, 16)
        c1_layout.setSpacing(8)

        c1_header = QHBoxLayout()
        lbl_c1_title = QLabel("🔥 Compliance Health")
        lbl_c1_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #64748b;")
        c1_header.addWidget(lbl_c1_title)
        c1_header.addStretch()
        self.lbl_c1_sub_badge = QLabel("Avg 94%")
        self.lbl_c1_sub_badge.setStyleSheet("font-size: 11px; font-weight: 600; color: #475569;")
        c1_header.addWidget(self.lbl_c1_sub_badge)
        c1_layout.addLayout(c1_header)

        c1_metric_row = QHBoxLayout()
        self.lbl_c1_score = QLabel("0%")
        self.lbl_c1_score.setStyleSheet("font-size: 32px; font-weight: 800; color: #0f172a;")
        c1_metric_row.addWidget(self.lbl_c1_score)

        self.pill_c1_status = QLabel("Ready")
        self.pill_c1_status.setStyleSheet("background-color: #f1f5f9; border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600; color: #334155;")
        c1_metric_row.addWidget(self.pill_c1_status)
        c1_metric_row.addStretch()

        lbl_sun = QLabel("☀️")
        lbl_sun.setStyleSheet("font-size: 18px;")
        c1_metric_row.addWidget(lbl_sun)
        c1_layout.addLayout(c1_metric_row)

        self.lbl_c1_subtitle = QLabel("Evaluated across 41 canonical accessibility checkpoints")
        self.lbl_c1_subtitle.setStyleSheet("font-size: 11px; color: #64748b;")
        c1_layout.addWidget(self.lbl_c1_subtitle)

        # Segmented distribution bar
        self.bar_distribution = SegmentedProgressBar()
        c1_layout.addWidget(self.bar_distribution)

        c1_layout.addSpacing(4)
        c1_stats = QHBoxLayout()
        self.lbl_c1_stat1 = self._create_stat_column("Total Checks", "0")
        self.lbl_c1_stat2 = self._create_stat_column("Passed", "0")
        self.lbl_c1_stat3 = self._create_stat_column("Issues", "0", is_pill=True)
        c1_stats.addLayout(self.lbl_c1_stat1)
        c1_stats.addLayout(self.lbl_c1_stat2)
        c1_stats.addLayout(self.lbl_c1_stat3)
        c1_layout.addLayout(c1_stats)

        self.cards_row.addWidget(self.card1)

        # Card 2: Findings Breakdown (with purple sparkline)
        self.card2 = QFrame()
        self.card2.setProperty("class", "summaryCard")
        self.card2.setStyleSheet(card_qss)
        c2_layout = QVBoxLayout(self.card2)
        c2_layout.setContentsMargins(18, 16, 18, 16)
        c2_layout.setSpacing(8)

        c2_header = QHBoxLayout()
        lbl_c2_title = QLabel("👑 Findings Breakdown")
        lbl_c2_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #64748b;")
        c2_header.addWidget(lbl_c2_title)
        c2_header.addStretch()
        self.lbl_c2_sub_badge = QLabel("Issues")
        self.lbl_c2_sub_badge.setStyleSheet("font-size: 11px; font-weight: 600; color: #475569;")
        c2_header.addWidget(self.lbl_c2_sub_badge)
        c2_layout.addLayout(c2_header)

        c2_metric_row = QHBoxLayout()
        self.lbl_c2_issues = QLabel("0")
        self.lbl_c2_issues.setStyleSheet("font-size: 32px; font-weight: 800; color: #0f172a;")
        c2_metric_row.addWidget(self.lbl_c2_issues)

        self.pill_c2_trend = QLabel("Active")
        self.pill_c2_trend.setStyleSheet("background-color: #f1f5f9; border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600; color: #475569;")
        c2_metric_row.addWidget(self.pill_c2_trend)
        c2_metric_row.addStretch()

        lbl_crown = QLabel("🛡️")
        lbl_crown.setStyleSheet("font-size: 18px;")
        c2_metric_row.addWidget(lbl_crown)
        c2_layout.addLayout(c2_metric_row)

        self.lbl_c2_subtitle = QLabel("Technical items requiring attention or remediation")
        self.lbl_c2_subtitle.setStyleSheet("font-size: 11px; color: #64748b;")
        c2_layout.addWidget(self.lbl_c2_subtitle)

        # Purple curve chart
        self.chart_sparkline = SparklineChart()
        c2_layout.addWidget(self.chart_sparkline)

        c2_layout.addSpacing(4)
        c2_stats = QHBoxLayout()
        self.lbl_c2_stat1 = self._create_stat_column("Failures", "0")
        self.lbl_c2_stat2 = self._create_stat_column("Warnings", "0")
        self.lbl_c2_stat3 = self._create_stat_column("Manual", "0")
        c2_stats.addLayout(self.lbl_c2_stat1)
        c2_stats.addLayout(self.lbl_c2_stat2)
        c2_stats.addLayout(self.lbl_c2_stat3)
        c2_layout.addLayout(c2_stats)

        self.cards_row.addWidget(self.card2)

        # Card 3: Standards Health (with vertical bar chart)
        self.card3 = QFrame()
        self.card3.setProperty("class", "summaryCard")
        self.card3.setStyleSheet(card_qss)
        c3_layout = QVBoxLayout(self.card3)
        c3_layout.setContentsMargins(18, 16, 18, 16)
        c3_layout.setSpacing(8)

        c3_header = QHBoxLayout()
        lbl_c3_title = QLabel("👤 Standards Conformance")
        lbl_c3_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #64748b;")
        c3_header.addWidget(lbl_c3_title)
        c3_header.addStretch()
        self.lbl_c3_sub_badge = QLabel("ISO & WCAG")
        self.lbl_c3_sub_badge.setStyleSheet("font-size: 11px; font-weight: 600; color: #475569;")
        c3_header.addWidget(self.lbl_c3_sub_badge)
        c3_layout.addLayout(c3_header)

        c3_metric_row = QHBoxLayout()
        self.lbl_c3_rate = QLabel("97%")
        self.lbl_c3_rate.setStyleSheet("font-size: 32px; font-weight: 800; color: #0f172a;")
        c3_metric_row.addWidget(self.lbl_c3_rate)

        self.pill_c3_status = QLabel("High")
        self.pill_c3_status.setStyleSheet("background-color: #ecfccb; border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600; color: #3f6212;")
        c3_metric_row.addWidget(self.pill_c3_status)
        c3_metric_row.addStretch()
        c3_layout.addLayout(c3_metric_row)

        self.lbl_c3_subtitle = QLabel("PDF/UA-1 • WCAG 2.1 AA • Quality Checkpoints")
        self.lbl_c3_subtitle.setStyleSheet("font-size: 11px; color: #64748b;")
        c3_layout.addWidget(self.lbl_c3_subtitle)

        # Vertical bars chart
        self.chart_minibars = MiniBarChart()
        c3_layout.addWidget(self.chart_minibars)

        c3_layout.addSpacing(4)
        c3_stats = QHBoxLayout()
        self.lbl_c3_stat1 = self._create_stat_column("PDF/UA-1", "Pass")
        self.lbl_c3_stat2 = self._create_stat_column("WCAG 2.1", "Pass")
        self.lbl_c3_stat3 = self._create_stat_column("Quality", "Excellent")
        c3_stats.addLayout(self.lbl_c3_stat1)
        c3_stats.addLayout(self.lbl_c3_stat2)
        c3_stats.addLayout(self.lbl_c3_stat3)
        c3_layout.addLayout(c3_stats)

        self.cards_row.addWidget(self.card3)

        self.cards_container = QWidget()
        self.cards_container.setLayout(self.cards_row)
        self.cards_container.setVisible(False)
        self.content_layout.addWidget(self.cards_container)

        # ---------------------------------------------------------
        # 3. Product Overview Table Card (matching reference design)
        # ---------------------------------------------------------
        self.table_card = QFrame()
        self.table_card.setObjectName("dashboardTableCard")
        self.table_card.setStyleSheet("""
            QFrame#dashboardTableCard {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 14px;
                padding: 16px;
            }
        """)
        tc_layout = QVBoxLayout(self.table_card)
        tc_layout.setContentsMargins(20, 18, 20, 18)
        tc_layout.setSpacing(14)

        # Table Header Row: Title on Left, Filter + Export on Right
        table_top_row = QHBoxLayout()
        lbl_tbl_title = QLabel("Audit Findings Overview")
        lbl_tbl_title.setStyleSheet("font-size: 17px; font-weight: 700; color: #0f172a;")
        table_top_row.addWidget(lbl_tbl_title)
        table_top_row.addStretch()

        # Filter Pill Dropdown
        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["All Findings", "Failures Only", "Warnings Only", "PDF/UA Rules", "WCAG Rules", "Quality Rules"])
        self.combo_filter.setStyleSheet("""
            QComboBox {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 14px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 600;
                color: #334155;
                min-width: 120px;
            }
            QComboBox:hover {
                border-color: #94a3b8;
            }
        """)
        self.combo_filter.currentTextChanged.connect(self._apply_filter)
        table_top_row.addWidget(self.combo_filter)

        # Black Pill "Export CSV / Report" Button
        self.btn_export_csv = QPushButton("☁️ Export CSV")
        self.btn_export_csv.setStyleSheet("""
            QPushButton {
                background-color: #0f172a;
                border: 1px solid #0f172a;
                border-radius: 15px;
                color: #ffffff;
                font-size: 12px;
                font-weight: 700;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #1e293b;
            }
        """)
        self.btn_export_csv.clicked.connect(self.export_report_requested)
        table_top_row.addWidget(self.btn_export_csv)

        tc_layout.addLayout(table_top_row)

        # Polished Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Rule ID", "Checkpoint / Issue", "Standard", "Status", "Page", "Message / Evidence"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 240)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(280)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #f1f5f9;
                gridline-color: #f8fafc;
                font-size: 12px;
                color: #1e293b;
            }
            QTableWidget::item {
                padding: 8px 10px;
                border-bottom: 1px solid #f1f5f9;
            }
            QTableWidget::item:selected {
                background-color: #f1f5f9;
                color: #0f172a;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #64748b;
                font-size: 11px;
                font-weight: 700;
                padding: 8px 10px;
                border: none;
                border-bottom: 1px solid #e2e8f0;
            }
        """)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        tc_layout.addWidget(self.table)

        self.table_card.setVisible(False)
        self.content_layout.addWidget(self.table_card)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _create_stat_column(self, title: str, val: str, is_pill: bool = False) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 10px; color: #94a3b8; font-weight: 600; text-transform: uppercase;")
        col.addWidget(lbl_t)

        lbl_v = QLabel(val)
        lbl_v.setObjectName("valLabel")
        if is_pill:
            lbl_v.setStyleSheet("font-size: 13px; font-weight: 700; color: #b45309;")
        else:
            lbl_v.setStyleSheet("font-size: 13px; font-weight: 700; color: #0f172a;")
        col.addWidget(lbl_v)
        return col

    def _set_col_val(self, col_layout: QVBoxLayout, text: str, color: Optional[str] = None):
        lbl = col_layout.findChild(QLabel, "valLabel")
        if lbl:
            lbl.setText(text)
            if color:
                lbl.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {color};")

    def load_document(self, doc: PDFDocumentModel, report: AuditReport):
        """Displays loaded document summary on dashboard."""
        self.current_doc = doc
        self.current_report = report
        self._all_findings = report.results

        self.empty_card.setVisible(False)
        self.cards_container.setVisible(True)
        self.table_card.setVisible(True)

        # 1. Update Card 1 (Compliance Health)
        score = report.compliance_score
        self.lbl_c1_score.setText(f"{score}%")
        self.lbl_c1_sub_badge.setText(f"Score {score}%")
        if score >= 90:
            self.pill_c1_status.setText("High Conformance")
            self.pill_c1_status.setStyleSheet("background-color: #ecfccb; border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600; color: #3f6212;")
        elif score >= 70:
            self.pill_c1_status.setText("Moderate")
            self.pill_c1_status.setStyleSheet("background-color: #fef3c7; border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600; color: #92400e;")
        else:
            self.pill_c1_status.setText("Needs Remediation")
            self.pill_c1_status.setStyleSheet("background-color: #fee2e2; border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600; color: #991b1b;")

        total_rules = report.total_passed + report.total_warned + report.total_failed
        self.bar_distribution.set_values(report.total_passed, report.total_warned, report.total_failed)
        self._set_col_val(self.lbl_c1_stat1, str(total_rules))
        self._set_col_val(self.lbl_c1_stat2, str(report.total_passed), "#15803d")
        self._set_col_val(self.lbl_c1_stat3, str(report.total_warned + report.total_failed), "#b45309" if (report.total_warned + report.total_failed) > 0 else "#15803d")

        # 2. Update Card 2 (Findings Breakdown)
        total_issues = report.total_failed + report.total_warned
        self.lbl_c2_issues.setText(str(total_issues))
        self.lbl_c2_sub_badge.setText(f"{len(report.results)} Evaluated")

        # Sparkline points generated from category findings
        cat_counts = [len([r for r in report.results if r.status != CheckStatus.PASS and r.page == p]) for p in range(1, min(10, doc.page_count + 1))]
        if not any(cat_counts):
            cat_counts = [report.total_failed, report.total_warned, total_issues, max(0, total_issues - 1), total_issues]
        self.chart_sparkline.set_data(
            [float(c) for c in cat_counts],
            badge_text=f"Issues: {total_issues}"
        )
        self._set_col_val(self.lbl_c2_stat1, str(report.total_failed), "#b91c1c" if report.total_failed > 0 else "#64748b")
        self._set_col_val(self.lbl_c2_stat2, str(report.total_warned), "#d97706" if report.total_warned > 0 else "#64748b")
        self._set_col_val(self.lbl_c2_stat3, str(getattr(report, "total_manual", 0)))

        # 3. Update Card 3 (Standards Conformance)
        pdfua_data = report.get_category_counts("PDF/UA")
        pdfua_fails = sum(c.get("failed", 0) for c in pdfua_data.values())
        wcag_data = report.get_category_counts("WCAG")
        wcag_fails = sum(c.get("failed", 0) for c in wcag_data.values())

        rate = max(10, min(100, int(score)))
        self.lbl_c3_rate.setText(f"{rate}%")

        # Generate bar heights from category pass rates
        bar_vals = []
        for cat, data in list(pdfua_data.items())[:5] + list(wcag_data.items())[:4]:
            t = data.get("passed", 0) + data.get("warned", 0) + data.get("failed", 0)
            if t > 0:
                bar_vals.append(data.get("passed", 0) / t)
            else:
                bar_vals.append(1.0)
        if not bar_vals:
            bar_vals = [0.8, 0.9, 0.95, 0.7, 0.85, 0.9, 0.6]
        self.chart_minibars.set_values(bar_vals)

        self._set_col_val(self.lbl_c3_stat1, "Pass" if pdfua_fails == 0 else f"{pdfua_fails} issues", "#15803d" if pdfua_fails == 0 else "#b91c1c")
        self._set_col_val(self.lbl_c3_stat2, "Pass" if wcag_fails == 0 else f"{wcag_fails} issues", "#15803d" if wcag_fails == 0 else "#b91c1c")
        self._set_col_val(self.lbl_c3_stat3, "Excellent" if score >= 85 else "Moderate", "#15803d")

        # 4. Populate Findings Table
        self._populate_table(self._all_findings)

    def _apply_filter(self, filter_text: str):
        if not self._all_findings:
            return

        filtered = []
        for r in self._all_findings:
            if filter_text == "All Findings":
                filtered.append(r)
            elif filter_text == "Failures Only" and r.status == CheckStatus.FAIL:
                filtered.append(r)
            elif filter_text == "Warnings Only" and r.status == CheckStatus.WARNING:
                filtered.append(r)
            elif filter_text == "PDF/UA Rules" and r.standard.upper().startswith("PDF/UA"):
                filtered.append(r)
            elif filter_text == "WCAG Rules" and "WCAG" in r.standard.upper():
                filtered.append(r)
            elif filter_text == "Quality Rules" and "QUALITY" in r.standard.upper():
                filtered.append(r)

        self._populate_table(filtered)

    def _populate_table(self, findings: List[CheckResult]):
        self.table.setRowCount(0)
        # Limit initial render to top 150 items for snappy responsiveness
        display_list = findings[:150]
        self.table.setRowCount(len(display_list))

        for row, f in enumerate(display_list):
            item_id = QTableWidgetItem(f.check_id)
            item_id.setFont(QFont("Segoe UI", 9, QFont.Bold))
            item_id.setData(Qt.UserRole, f)
            self.table.setItem(row, 0, item_id)

            item_title = QTableWidgetItem(getattr(f, "name", "") or getattr(f, "title", "") or f.check_id)
            self.table.setItem(row, 1, item_title)

            item_std = QTableWidgetItem(f.standard)
            self.table.setItem(row, 2, item_std)

            # Styled Status Pill
            item_status = QTableWidgetItem(f.status.value)
            if f.status == CheckStatus.PASS:
                item_status.setForeground(QColor("#15803d"))
            elif f.status in (CheckStatus.FAIL, CheckStatus.ERROR):
                item_status.setForeground(QColor("#b91c1c"))
            elif f.status == CheckStatus.WARNING:
                item_status.setForeground(QColor("#b45309"))
            item_status.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.table.setItem(row, 3, item_status)

            item_page = QTableWidgetItem(f"p. {f.page}" if f.page else "Doc")
            item_page.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, item_page)

            msg = f.evidence or f.message or "-"
            item_msg = QTableWidgetItem(msg)
            self.table.setItem(row, 5, item_msg)

    def _on_row_double_clicked(self, item: QTableWidgetItem):
        row = item.row()
        id_item = self.table.item(row, 0)
        if id_item:
            finding = id_item.data(Qt.UserRole)
            if finding:
                self.finding_selected.emit(finding)
                self.view_details_requested.emit()
