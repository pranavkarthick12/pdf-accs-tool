"""
Checkpoints View
Renders the primary tabbed inspection matrix matching the PAC reference screenshots:
- Document summary card with cover thumbnail, Title, Filename, Language, Pages, Tags, Size
- Tabs for [PDF/UA], [WCAG], [Quality], [AI] with status icons
- Clear compliance status banner ("This PDF file is not PDF/UA compliant.")
- Matrix columns: [Checkpoint], [Passed], [Warned], [Failed]
- Bottom navigation toolbar: Results in detail, PDF report, Tag Tree, Statistics, Preview.
"""

from typing import Optional, Dict, List, Any
import pymupdf
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QLabel, QFrame, QScrollArea
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QIcon, QColor, QFont, QPixmap, QImage
from ...core.models import AuditReport, PDFDocumentModel, CheckStatus
from ...engine.wcag.wcag_meta import WCAG_GUIDELINE_META
from ..widgets.status_badge import StatusColors


class CheckpointTableWidget(QTableWidget):
    """Custom table displaying checkpoint categories with counts and status icons."""

    category_selected = Signal(str, str)  # (standard, category_name) - on double click
    category_clicked = Signal(str, str)   # (standard, category_name) - on single click

    def __init__(self, categories: List[str], standard_name: str, parent=None):
        super().__init__(parent)
        self.categories = categories
        self.standard_name = standard_name
        self._init_ui()

    def _init_ui(self):
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["Checkpoint", "Passed", "Warned", "Failed"])
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setShowGrid(True)
        self.setAlternatingRowColors(True)

        header = self.horizontalHeader()
        header.setMinimumSectionSize(50)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.setColumnWidth(1, 68)
        self.setColumnWidth(2, 68)
        self.setColumnWidth(3, 68)

        self.setRowCount(len(self.categories))
        for row, cat in enumerate(self.categories):
            item_name = QTableWidgetItem(f"⊘  {cat}")
            item_name.setFont(QFont("Segoe UI", 10))
            item_name.setToolTip(cat)
            self.setItem(row, 0, item_name)

            for col in range(1, 4):
                item_cnt = QTableWidgetItem("-")
                item_cnt.setTextAlignment(Qt.AlignCenter)
                self.setItem(row, col, item_cnt)

        self.cellClicked.connect(self._on_row_click)
        self.cellDoubleClicked.connect(self._on_row_double_click)

    def update_counts(self, counts_by_cat: Dict[str, Dict[str, int]]):
        """Updates row numbers and status icons matching PAC."""
        for row, cat in enumerate(self.categories):
            c_data = counts_by_cat.get(cat, {"passed": 0, "warned": 0, "failed": 0, "manual": 0, "not_applicable": 0})
            p = c_data["passed"]
            w = c_data["warned"]
            f = c_data["failed"]

            # Choose icon matching PAC 2026
            if f > 0:
                icon_str = "❌"
            elif w > 0:
                icon_str = "⚠️"
            elif p > 0:
                icon_str = "✅"
            else:
                icon_str = "⊘"

            item_name = self.item(row, 0)
            if item_name:
                item_name.setText(f"{icon_str}  {cat}")
                wcag_meta = WCAG_GUIDELINE_META.get(cat) if self.standard_name.upper() in ("WCAG", "WCAG2", "WCAG 2.1", "WCAG 2.2") else None
                meta_prefix = f"{cat} [{wcag_meta['principle']} • {wcag_meta['criteria']}]" if wcag_meta else cat
                if p == 0 and w == 0 and f == 0:
                    item_name.setToolTip(f"{meta_prefix}\nStatus: Not applicable (⊘ no applicable objects found)")
                else:
                    item_name.setToolTip(f"{meta_prefix}\nStatus: {p} passed, {w} warned, {f} failed")

            # Passed column
            item_p = self.item(row, 1)
            if item_p:
                item_p.setText(str(p) if p > 0 else "-")
                if p > 0:
                    item_p.setForeground(StatusColors.get_status_color(CheckStatus.PASS))
                    item_p.setFont(QFont("Segoe UI", 10, QFont.Bold))
                else:
                    item_p.setForeground(QColor("#94a3b8"))
                    item_p.setFont(QFont("Segoe UI", 10))

            # Warned column
            item_w = self.item(row, 2)
            if item_w:
                item_w.setText(str(w) if w > 0 else "-")
                if w > 0:
                    item_w.setForeground(StatusColors.get_status_color(CheckStatus.WARNING))
                    item_w.setFont(QFont("Segoe UI", 10, QFont.Bold))
                else:
                    item_w.setForeground(QColor("#94a3b8"))
                    item_w.setFont(QFont("Segoe UI", 10))

            # Failed column
            item_f = self.item(row, 3)
            if item_f:
                item_f.setText(str(f) if f > 0 else "-")
                if f > 0:
                    item_f.setForeground(StatusColors.get_status_color(CheckStatus.FAIL))
                    item_f.setFont(QFont("Segoe UI", 10, QFont.Bold))
                else:
                    item_f.setForeground(QColor("#94a3b8"))
                    item_f.setFont(QFont("Segoe UI", 10))

    def _on_row_click(self, row: int, col: int):
        if 0 <= row < len(self.categories):
            cat_name = self.categories[row]
            self.category_selected.emit(self.standard_name, cat_name)

    def _on_row_double_click(self, row: int, col: int):
        if 0 <= row < len(self.categories):
            cat_name = self.categories[row]
            self.category_selected.emit(self.standard_name, cat_name)


class CheckpointsView(QWidget):
    """Container view providing the PAC inspection interface, header summary, and bottom action toolbar."""

    request_rescan = Signal()
    request_detailed_results = Signal()
    request_pdf_report = Signal()
    request_tag_tree = Signal()
    request_statistics = Signal()
    request_preview = Signal()
    category_selected = Signal(str, str)  # (standard, category) - on double click
    category_clicked = Signal(str, str)   # (standard, category) - on single click

    PDF_UA_CATEGORIES = [
        "PDF Syntax (ISO 32000-1)",
        "Fonts",
        "Content",
        "Embedded Files",
        "Natural language",
        "Structure elements",
        "Structure tree",
        "Role mapping",
        "Alternative Descriptions",
        "Metadata",
        "Document settings",
    ]

    WCAG_CATEGORIES = [
        "1.1 Text Alternatives",
        "1.2 Time-based Media",
        "1.3 Adaptable",
        "1.4 Distinguishable",
        "2.1 Keyboard Accessible",
        "2.2 Enough Time",
        "2.3 Seizures and Physical Reactions",
        "2.4 Navigable",
        "2.5 Input Modalities",
        "3.1 Readable",
        "3.2 Predictable",
        "3.3 Input Assistance",
        "4.1 Compatible",
    ]

    QUALITY_RULE_MAPPINGS = {
        "Validity of document title": ["QUAL-TITLE-001"],
        "Artifacted content on page body": ["QUAL-ART-001"],
        "Tagged text consists of only whitespace": ["QUAL-WHITE-001"],
        "Tagged content exists outside of the page boundaries": ["QUAL-BOUND-001"],
        "Presence of headings": ["QUAL-HEAD-001"],
        "Presence of bookmarks (document outline) if there are headings": ["QUAL-BOOKMARK-001"],
        '"TOCI" elements contain "Link" elements': ["QUAL-TOC-001"],
        '"TOCI" elements correctly linked to headings': ["QUAL-TOC-002"],
        "Alternative text on text elements": ["QUAL-TEXT-001"],
        "Validity of alternate text": ["QUAL-ALT-001"],
        'Completeness of "Link" elements': ["QUAL-LINK-002"],
        'Formal correctness of "LI" elements': ["QUAL-LIST-001"],
        'Completeness of "Table" elements': ["QUAL-TABLE-001"],
        '"Note" elements are referenced': ["QUAL-NOTE-001"],
        '"Note" elements contain "Lbl" elements': ["QUAL-NOTE-002"],
        '"P" elements contain "Note" elements': ["QUAL-NOTE-003"],
    }


    QUALITY_CATEGORIES = list(QUALITY_RULE_MAPPINGS.keys())

    AI_CATEGORIES = [
        "Classification of the elements",
        "Unrecognized structural elements",
        "Missing structural elements",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Document Header Card matching PAC screenshot
        self.header_card = QFrame()
        self.header_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-bottom: 1px solid #e2e8f0;
            }
        """)
        h_layout = QHBoxLayout(self.header_card)
        h_layout.setContentsMargins(16, 12, 16, 12)
        h_layout.setSpacing(20)

        # Cover Thumbnail
        self.lbl_thumb = QLabel()
        self.lbl_thumb.setFixedSize(84, 110)
        self.lbl_thumb.setAlignment(Qt.AlignCenter)
        self.lbl_thumb.setStyleSheet("background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 4px;")
        h_layout.addWidget(self.lbl_thumb)

        # Metadata Grid
        meta_grid = QGridLayout()
        meta_grid.setHorizontalSpacing(16)
        meta_grid.setVerticalSpacing(4)

        lbl_t_title = QLabel("Title")
        lbl_t_title.setStyleSheet("color: #64748b; font-size: 12px;")
        self.lbl_val_title = QLabel("-")
        self.lbl_val_title.setStyleSheet("color: #1e3a8a; font-weight: bold; font-size: 13px; background-color: #dbeafe; padding: 2px 6px; border-radius: 3px;")

        # Retained for programmatic access but omitted from visible UI layout matching PAC 2026
        self.lbl_val_author = QLabel("-")

        lbl_t_fn = QLabel("Filename")
        lbl_t_fn.setStyleSheet("color: #64748b; font-size: 12px;")
        self.lbl_val_fn = QLabel("-")
        self.lbl_val_fn.setStyleSheet("color: #0f172a; font-weight: bold; font-size: 13px;")

        lbl_t_lang = QLabel("Language")
        lbl_t_lang.setStyleSheet("color: #64748b; font-size: 12px;")
        self.lbl_val_lang = QLabel("-")
        self.lbl_val_lang.setStyleSheet("color: #0f172a; font-size: 13px;")

        lbl_t_pages = QLabel("Pages")
        lbl_t_pages.setStyleSheet("color: #64748b; font-size: 12px;")
        self.lbl_val_pages = QLabel("-")
        self.lbl_val_pages.setStyleSheet("color: #0f172a; font-weight: bold; font-size: 13px;")

        lbl_t_tags = QLabel("Tags")
        lbl_t_tags.setStyleSheet("color: #64748b; font-size: 12px;")
        self.lbl_val_tags = QLabel("-")
        self.lbl_val_tags.setStyleSheet("color: #0f172a; font-weight: bold; font-size: 13px;")

        lbl_t_size = QLabel("Size")
        lbl_t_size.setStyleSheet("color: #64748b; font-size: 12px;")
        self.lbl_val_size = QLabel("-")
        self.lbl_val_size.setStyleSheet("color: #0f172a; font-size: 13px;")

        meta_grid.addWidget(lbl_t_title, 0, 0)
        meta_grid.addWidget(self.lbl_val_title, 0, 1)
        meta_grid.addWidget(lbl_t_fn, 1, 0)
        meta_grid.addWidget(self.lbl_val_fn, 1, 1)
        meta_grid.addWidget(lbl_t_lang, 2, 0)
        meta_grid.addWidget(self.lbl_val_lang, 2, 1)
        meta_grid.addWidget(lbl_t_pages, 3, 0)
        meta_grid.addWidget(self.lbl_val_pages, 3, 1)
        meta_grid.addWidget(lbl_t_tags, 4, 0)
        meta_grid.addWidget(self.lbl_val_tags, 4, 1)
        meta_grid.addWidget(lbl_t_size, 5, 0)
        meta_grid.addWidget(self.lbl_val_size, 5, 1)

        h_layout.addLayout(meta_grid)
        h_layout.addStretch()
        main_layout.addWidget(self.header_card)

        # 2. Tabbed Checkpoints Section
        self.tab_widget = QTabWidget()

        # PDF/UA Page
        p_pdfua = QWidget()
        l_pdfua = QVBoxLayout(p_pdfua)
        l_pdfua.setContentsMargins(10, 8, 10, 0)
        l_pdfua.setSpacing(6)
        self.lbl_pdfua_banner = QLabel("This PDF file is not PDF/UA compliant.")
        self.lbl_pdfua_banner.setStyleSheet("font-size: 13px; font-weight: bold; color: #1e293b; padding: 4px 2px;")
        l_pdfua.addWidget(self.lbl_pdfua_banner)
        self.table_pdf_ua = CheckpointTableWidget(self.PDF_UA_CATEGORIES, "PDF/UA")
        self.table_pdf_ua.category_clicked.connect(self.category_clicked)
        self.table_pdf_ua.category_selected.connect(self.category_selected)
        l_pdfua.addWidget(self.table_pdf_ua)
        self.tab_widget.addTab(p_pdfua, "PDF/UA")

        # WCAG Page
        p_wcag = QWidget()
        l_wcag = QVBoxLayout(p_wcag)
        l_wcag.setContentsMargins(10, 8, 10, 0)
        l_wcag.setSpacing(6)
        self.lbl_wcag_banner = QLabel("WCAG 2.1/2.2 AA Accessibility Evaluation")
        self.lbl_wcag_banner.setStyleSheet("font-size: 13px; font-weight: bold; color: #1e293b; padding: 4px 2px;")
        l_wcag.addWidget(self.lbl_wcag_banner)
        self.table_wcag = CheckpointTableWidget(self.WCAG_CATEGORIES, "WCAG")
        self.table_wcag.category_clicked.connect(self.category_clicked)
        self.table_wcag.category_selected.connect(self.category_selected)
        l_wcag.addWidget(self.table_wcag)
        self.tab_widget.addTab(p_wcag, "WCAG")

        # Quality Page
        p_quality = QWidget()
        l_quality = QVBoxLayout(p_quality)
        l_quality.setContentsMargins(10, 8, 10, 0)
        l_quality.setSpacing(6)
        self.lbl_quality_banner = QLabel("Document Quality & Readability Evaluation")
        self.lbl_quality_banner.setStyleSheet("font-size: 13px; font-weight: bold; color: #1e293b; padding: 4px 2px;")
        l_quality.addWidget(self.lbl_quality_banner)
        self.table_quality = CheckpointTableWidget(self.QUALITY_CATEGORIES, "Quality")
        self.table_quality.category_clicked.connect(self.category_clicked)
        self.table_quality.category_selected.connect(self.category_selected)
        l_quality.addWidget(self.table_quality)
        self.tab_widget.addTab(p_quality, "Quality")

        # AI Page
        p_ai = QWidget()
        l_ai = QVBoxLayout(p_ai)
        l_ai.setContentsMargins(10, 8, 10, 0)
        l_ai.setSpacing(6)
        self.lbl_ai_banner = QLabel("AI Assisted Remediation & Heuristic Audit")
        self.lbl_ai_banner.setStyleSheet("font-size: 13px; font-weight: bold; color: #1e293b; padding: 4px 2px;")
        l_ai.addWidget(self.lbl_ai_banner)
        self.table_ai = CheckpointTableWidget(self.AI_CATEGORIES, "AI")
        self.table_ai.category_clicked.connect(self.category_clicked)
        self.table_ai.category_selected.connect(self.category_selected)
        l_ai.addWidget(self.table_ai)
        self.tab_widget.addTab(p_ai, "AI")

        # Refresh button in top right
        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setToolTip("Rescan Document")
        self.btn_refresh.setFixedSize(32, 28)
        self.btn_refresh.setStyleSheet("font-size: 14px; border-radius: 4px; background: #ffffff;")
        self.btn_refresh.clicked.connect(self.request_rescan)
        self.tab_widget.setCornerWidget(self.btn_refresh, Qt.TopRightCorner)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tab_widget)

        # 3. Bottom Toolbar matching PAC layout
        bottom_bar = QFrame()
        bottom_bar.setStyleSheet("background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 6px;")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(10, 4, 10, 4)
        bottom_layout.setSpacing(8)

        self.btn_detail = QPushButton("📋 Results in detail")
        self.btn_detail.clicked.connect(self._on_btn_detail_clicked)
        bottom_layout.addWidget(self.btn_detail)

        self.btn_report = QPushButton("📄 PDF report")
        self.btn_report.clicked.connect(self.request_pdf_report)
        bottom_layout.addWidget(self.btn_report)

        bottom_layout.addStretch()

        self.btn_stats = QPushButton("📊 Statistics")
        self.btn_stats.clicked.connect(self.request_statistics)
        bottom_layout.addWidget(self.btn_stats)

        main_layout.addWidget(bottom_bar)

    def _on_tab_changed(self, idx: int):
        """When switching standard tabs, automatically select the relevant category and sync details."""
        tables = [self.table_pdf_ua, self.table_wcag, self.table_quality, self.table_ai]
        if not (0 <= idx < len(tables)):
            return
        table = tables[idx]
        if not table.categories:
            return

        curr = table.currentRow()
        if 0 <= curr < len(table.categories):
            target_row = curr
        else:
            target_row = 0
            found = False
            for r in range(len(table.categories)):
                item_f = table.item(r, 3)
                item_w = table.item(r, 2)
                if item_f and item_f.text() not in ("-", "0"):
                    target_row = r
                    found = True
                    break
                if item_w and item_w.text() not in ("-", "0") and not found:
                    target_row = r
                    found = True

            if not found:
                for r in range(len(table.categories)):
                    item_p = table.item(r, 1)
                    if item_p and item_p.text() not in ("-", "0"):
                        target_row = r
                        break

        table.setCurrentCell(target_row, 0)
        table.selectRow(target_row)
        cat_name = table.categories[target_row]
        self.category_clicked.emit(table.standard_name, cat_name)

    def _on_btn_detail_clicked(self):
        """Dispatches detailed results request, resolving the currently active checkpoint selection."""
        curr_idx = self.tab_widget.currentIndex()
        tables = [self.table_pdf_ua, self.table_wcag, self.table_quality, self.table_ai]
        if 0 <= curr_idx < len(tables):
            table = tables[curr_idx]
            row = table.currentRow()
            if (row < 0 or row >= len(table.categories)) and len(table.categories) > 0:
                row = 0
                table.setCurrentCell(0, 0)
                table.selectRow(0)
            if 0 <= row < len(table.categories):
                cat_name = table.categories[row]
                self.category_selected.emit(table.standard_name, cat_name)
                return
        self.request_detailed_results.emit()

    def update_report(self, report: AuditReport, doc: Optional[PDFDocumentModel] = None):
        """Updates all tables, status banners, tab icons, and document metadata summary."""
        pdfua_counts = report.get_category_counts("PDF/UA")
        wcag_counts = report.get_category_counts("WCAG")
        quality_counts = report.get_category_counts("Quality")
        ai_counts = report.get_category_counts("AI")

        self.table_pdf_ua.update_counts(pdfua_counts)
        self.table_wcag.update_counts(wcag_counts)
        self.table_quality.update_counts(quality_counts)
        self.table_ai.update_counts(ai_counts)

        # Tab status indicators matching PAC
        def _get_status_icon(counts):
            failed = sum(c.get("failed", 0) for c in counts.values())
            warned = sum(c.get("warned", 0) for c in counts.values())
            passed = sum(c.get("passed", 0) for c in counts.values())
            if failed > 0:
                return "❌"
            elif warned > 0:
                return "⚠️"
            elif passed > 0:
                return "✅"
            return "⊘"

        ai_icon = _get_status_icon(ai_counts)
        self.tab_widget.setTabText(0, f"{_get_status_icon(pdfua_counts)} PDF/UA")
        self.tab_widget.setTabText(1, f"{_get_status_icon(wcag_counts)} WCAG")
        self.tab_widget.setTabText(2, f"{_get_status_icon(quality_counts)} Quality")
        self.tab_widget.setTabText(3, f"{ai_icon} AI" if ai_icon != "✅" else "AI")

        # Compliance Banner
        pdfua_failed = sum(c.get("failed", 0) for c in pdfua_counts.values())
        if pdfua_failed > 0:
            self.lbl_pdfua_banner.setText("This PDF file is not PDF/UA compliant.")
            self.lbl_pdfua_banner.setStyleSheet("font-size: 13px; font-weight: bold; color: #b91c1c; padding: 4px 2px;")
        else:
            self.lbl_pdfua_banner.setText("This PDF file is PDF/UA compliant.")
            self.lbl_pdfua_banner.setStyleSheet("font-size: 13px; font-weight: bold; color: #15803d; padding: 4px 2px;")

        art_body_counts = quality_counts.get("Artifacted content on page body", {})
        has_art_body_issue = (art_body_counts.get("warned", 0) > 0 or art_body_counts.get("failed", 0) > 0)
        sad_emoji = "🙁 " if has_art_body_issue else ""

        quality_failed = sum(c.get("failed", 0) for c in quality_counts.values())
        quality_warned = sum(c.get("warned", 0) for c in quality_counts.values())
        if quality_failed > 0 or quality_warned > 0:
            self.lbl_quality_banner.setText(f"{sad_emoji}This document has potential quality issues.")
            self.lbl_quality_banner.setStyleSheet("font-size: 13px; font-weight: bold; color: #b45309; padding: 4px 2px;")
        else:
            self.lbl_quality_banner.setText("This document has no quality issues.")
            self.lbl_quality_banner.setStyleSheet("font-size: 13px; font-weight: bold; color: #15803d; padding: 4px 2px;")

        ai_failed = sum(c.get("failed", 0) for c in ai_counts.values())
        ai_warned = sum(c.get("warned", 0) for c in ai_counts.values())
        if ai_failed > 0 or ai_warned > 0:
            self.lbl_ai_banner.setText("The AI has detected potential issues in this PDF document.")
            self.lbl_ai_banner.setStyleSheet("font-size: 13px; font-weight: bold; color: #1e293b; padding: 4px 2px;")
        else:
            self.lbl_ai_banner.setText("This document has no AI issues.")
            self.lbl_ai_banner.setStyleSheet("font-size: 13px; font-weight: bold; color: #15803d; padding: 4px 2px;")

        # Update metadata card if doc model provided
        if doc is not None:
            self.lbl_val_title.setText(doc.title.strip() if doc.title and doc.title.strip() else "No title")
            self.lbl_val_author.setText(doc.author.strip() if doc.author and doc.author.strip() else "No author")
            self.lbl_val_fn.setText(doc.filename)
            self.lbl_val_lang.setText(doc.language if doc.language else "-")
            self.lbl_val_pages.setText(str(doc.page_count))

            tag_count = len([n for n in doc.structure_tree.find_all_nodes() if n.tag != "StructTreeRoot"]) if doc.structure_tree else 0
            self.lbl_val_tags.setText(str(tag_count))

            if doc.filesize >= 1024 * 1024:
                size_str = f"{doc.filesize / (1024 * 1024):.0f} MB"
            elif doc.filesize > 0:
                size_str = f"{doc.filesize / 1024:.0f} KB"
            else:
                size_str = "-"
            self.lbl_val_size.setText(size_str)

            # Render page 1 thumbnail
            try:
                fitz_doc = pymupdf.open(doc.filepath)
                if len(fitz_doc) > 0:
                    pix = fitz_doc[0].get_pixmap(dpi=72)
                    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(qimg).scaled(84, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.lbl_thumb.setPixmap(pixmap)
                fitz_doc.close()
            except Exception:
                self.lbl_thumb.setText("📄")
