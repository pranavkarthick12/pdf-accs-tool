"""
Statistics View
Displays compliance metrics, category score breakdowns, and document element inventories.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QProgressBar, QFrame, QScrollArea
)
from PySide6.QtCore import Qt
from ...core.models import AuditReport, PDFDocumentModel, CheckStatus
from ..widgets.status_badge import StatusColors


class StatCard(QFrame):
    """Visual summary statistic card."""

    def __init__(self, title: str, value: str, subtext: str = "", color: str = "#2563eb", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            StatCard {{
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 12px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        lbl_title = QLabel(title.upper())
        lbl_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.5px;")
        layout.addWidget(lbl_title)

        lbl_val = QLabel(value)
        lbl_val.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {color};")
        layout.addWidget(lbl_val)

        if subtext:
            lbl_sub = QLabel(subtext)
            lbl_sub.setStyleSheet("font-size: 11px; color: #94a3b8;")
            layout.addWidget(lbl_sub)


class StatisticsView(QWidget):
    """View rendering comprehensive document health metrics and statistics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # 1. Main Score Header
        self.score_banner = QFrame()
        self.score_banner.setStyleSheet("""
            QFrame {
                background: linear-gradient(135deg, #1e293b, #0f172a);
                background-color: #0f172a;
                border-radius: 10px;
                padding: 16px;
                color: #ffffff;
            }
        """)
        sb_layout = QHBoxLayout(self.score_banner)

        score_left = QVBoxLayout()
        self.lbl_compliance_title = QLabel("Overall Accessibility Compliance")
        self.lbl_compliance_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        score_left.addWidget(self.lbl_compliance_title)

        self.lbl_compliance_desc = QLabel("Comprehensive rating evaluated across PDF/UA and WCAG rules.")
        self.lbl_compliance_desc.setStyleSheet("font-size: 12px; color: #94a3b8;")
        score_left.addWidget(self.lbl_compliance_desc)
        sb_layout.addLayout(score_left)

        sb_layout.addStretch()

        self.lbl_score_num = QLabel("0%")
        self.lbl_score_num.setStyleSheet("font-size: 38px; font-weight: 800; color: #10b981;")
        sb_layout.addWidget(self.lbl_score_num)

        layout.addWidget(self.score_banner)

        # 2. Key Metrics Grid
        self.metrics_grid = QGridLayout()
        self.metrics_grid.setSpacing(10)

        self.card_passed = StatCard("Passed Checks", "0", "Standard satisfied", StatusColors.get_status_style(CheckStatus.PASS)["fg"])
        self.card_warned = StatCard("Warnings", "0", "Potential issues", StatusColors.get_status_style(CheckStatus.WARNING)["fg"])
        self.card_failed = StatCard("Failed Issues", "0", "Violations detected", StatusColors.get_status_style(CheckStatus.FAIL)["fg"])
        self.card_manual = StatCard("Manual Review", "0", "Human audit required", StatusColors.get_status_style(CheckStatus.MANUAL_REVIEW)["fg"])

        self.metrics_grid.addWidget(self.card_passed, 0, 0)
        self.metrics_grid.addWidget(self.card_warned, 0, 1)
        self.metrics_grid.addWidget(self.card_failed, 0, 2)
        self.metrics_grid.addWidget(self.card_manual, 0, 3)

        layout.addLayout(self.metrics_grid)

        # 3. Standards Compliance Bars
        bars_frame = QFrame()
        bars_frame.setStyleSheet("background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;")
        bf_layout = QVBoxLayout(bars_frame)

        lbl_bars = QLabel("Standards Adherence Breakdown")
        lbl_bars.setStyleSheet("font-weight: 700; font-size: 13px; color: #1e293b; margin-bottom: 8px;")
        bf_layout.addWidget(lbl_bars)

        # PDF/UA bar
        bf_layout.addWidget(QLabel("<b>PDF/UA-1 (ISO 14289-1)</b>"))
        self.bar_pdfua = QProgressBar()
        self.bar_pdfua.setStyleSheet("QProgressBar::chunk { background-color: #2563eb; border-radius: 3px; }")
        self.bar_pdfua.setValue(0)
        bf_layout.addWidget(self.bar_pdfua)

        # WCAG bar
        bf_layout.addWidget(QLabel("<b>WCAG 2.1 / 2.2 AA</b>"))
        self.bar_wcag = QProgressBar()
        self.bar_wcag.setStyleSheet("QProgressBar::chunk { background-color: #10b981; border-radius: 3px; }")
        self.bar_wcag.setValue(0)
        bf_layout.addWidget(self.bar_wcag)

        # Quality bar
        bf_layout.addWidget(QLabel("<b>Authoring Quality & Best Practices</b>"))
        self.bar_quality = QProgressBar()
        self.bar_quality.setStyleSheet("QProgressBar::chunk { background-color: #8b5cf6; border-radius: 3px; }")
        self.bar_quality.setValue(0)
        bf_layout.addWidget(self.bar_quality)

        layout.addWidget(bars_frame)

        # 4. Document Element Inventory
        inv_frame = QFrame()
        inv_frame.setStyleSheet("background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;")
        inv_layout = QVBoxLayout(inv_frame)

        lbl_inv = QLabel("Document Structure & Elements Inventory")
        lbl_inv.setStyleSheet("font-weight: 700; font-size: 13px; color: #1e293b; margin-bottom: 6px;")
        inv_layout.addWidget(lbl_inv)

        self.inv_grid = QGridLayout()
        self.inv_grid.setSpacing(10)

        self.lbl_inv_pages = QLabel("Pages: 0")
        self.lbl_inv_fonts = QLabel("Fonts: 0")
        self.lbl_inv_images = QLabel("Images: 0")
        self.lbl_inv_tables = QLabel("Tables: 0")
        self.lbl_inv_links = QLabel("Links: 0")
        self.lbl_inv_forms = QLabel("Form Fields: 0")
        self.lbl_inv_bookmarks = QLabel("Bookmarks: 0")
        self.lbl_inv_headings = QLabel("Headings: 0")

        self.inv_grid.addWidget(self.lbl_inv_pages, 0, 0)
        self.inv_grid.addWidget(self.lbl_inv_fonts, 0, 1)
        self.inv_grid.addWidget(self.lbl_inv_images, 0, 2)
        self.inv_grid.addWidget(self.lbl_inv_tables, 0, 3)
        self.inv_grid.addWidget(self.lbl_inv_links, 1, 0)
        self.inv_grid.addWidget(self.lbl_inv_forms, 1, 1)
        self.inv_grid.addWidget(self.lbl_inv_bookmarks, 1, 2)
        self.inv_grid.addWidget(self.lbl_inv_headings, 1, 3)

        inv_layout.addLayout(self.inv_grid)
        layout.addWidget(inv_frame)

        layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def load_report(self, report: AuditReport, doc: PDFDocumentModel):
        """Refreshes statistics with the latest audit figures."""
        score = report.compliance_score
        self.lbl_score_num.setText(f"{score}%")

        if score >= 90:
            self.lbl_score_num.setStyleSheet("font-size: 38px; font-weight: 800; color: #10b981;")
        elif score >= 70:
            self.lbl_score_num.setStyleSheet("font-size: 38px; font-weight: 800; color: #f59e0b;")
        else:
            self.lbl_score_num.setStyleSheet("font-size: 38px; font-weight: 800; color: #ef4444;")

        # Update metric cards
        self._update_card(self.card_passed, str(report.total_passed))
        self._update_card(self.card_warned, str(report.total_warned))
        self._update_card(self.card_failed, str(report.total_failed))
        self._update_card(self.card_manual, str(report.total_manual))

        # Standard score percentages
        self.bar_pdfua.setValue(self._calc_std_score(report, "PDF/UA"))
        self.bar_wcag.setValue(self._calc_std_score(report, "WCAG"))
        self.bar_quality.setValue(self._calc_std_score(report, "Quality"))

        # Inventory
        self.lbl_inv_pages.setText(f"📄 <b>Pages:</b> {doc.page_count}")
        self.lbl_inv_fonts.setText(f"🔤 <b>Fonts:</b> {len(doc.fonts)}")
        self.lbl_inv_images.setText(f"🖼️ <b>Images:</b> {len(doc.images)}")
        self.lbl_inv_tables.setText(f"📊 <b>Tables:</b> {len(doc.tables)}")
        self.lbl_inv_links.setText(f"🔗 <b>Links:</b> {len(doc.links)}")
        self.lbl_inv_forms.setText(f"📝 <b>Form Fields:</b> {len(doc.form_fields)}")
        self.lbl_inv_bookmarks.setText(f"🔖 <b>Bookmarks:</b> {len(doc.bookmarks)}")

        heading_count = 0
        if doc.structure_tree:
            heading_count = len([n for n in doc.structure_tree.find_all_nodes() if n.standard_tag.upper() in ("H", "H1", "H2", "H3", "H4", "H5", "H6")])
        self.lbl_inv_headings.setText(f"📑 <b>Headings:</b> {heading_count}")

    def _update_card(self, card: StatCard, value: str):
        lbl = card.findChild(QLabel, "")
        # Find the second label which is the value label
        labels = card.findChildren(QLabel)
        if len(labels) >= 2:
            labels[1].setText(value)

    def _calc_std_score(self, report: AuditReport, std: str) -> int:
        res = report.get_results_by_standard(std)
        if not res:
            return 100
        passed = sum(1 for r in res if r.status == CheckStatus.PASS)
        total = sum(1 for r in res if r.status in (CheckStatus.PASS, CheckStatus.WARNING, CheckStatus.FAIL, CheckStatus.ERROR))
        return int((passed / total * 100)) if total > 0 else 100
