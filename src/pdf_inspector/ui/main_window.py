"""
Main Window
Enterprise desktop application window integrating top ribbon, sidebar navigation,
central stacked views, PDF viewer canvas, and right finding inspector panel.
"""

from typing import Optional
import os
import sys
import subprocess
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QFileDialog, QMessageBox, QProgressBar, QLabel, QSplitter,
    QStatusBar, QApplication, QInputDialog, QLineEdit
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QEvent
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon

from ..core.models import PDFDocumentModel, AuditReport, CheckResult, CheckStatus
from ..core.document_parser import DocumentParser
from ..engine.runner import AuditRunner
from ..reporting.pdf_report import PDFReportGenerator
from ..reporting.html_report import HTMLReportGenerator
from ..reporting.json_exporter import JSONExporter, CSVExporter

from .top_bar import TopBar
from .sidebar import Sidebar
from .widgets.finding_details_panel import FindingDetailsPanel
from .widgets.pdf_canvas import PDFCanvas
from .views.dashboard_view import DashboardView
from .views.checkpoints_view import CheckpointsView
from .views.detailed_results_view import DetailedResultsView
from .views.tag_tree_view import TagTreeView
from .views.screen_reader_view import ScreenReaderView
from .views.metadata_view import MetadataView
from .views.statistics_view import StatisticsView
from .views.elements_view import ElementsView
from .views.batch_view import BatchScanView
from .views.loading_view import LoadingView
from .dialogs.about_dialog import AboutDialog
from .dialogs.settings_dialog import SettingsDialog
from .dialogs.export_dialog import ExportDialog


class AuditWorker(QObject):
    """Background worker thread for parsing and auditing PDFs without blocking UI."""

    finished = Signal(object, object)  # (PDFDocumentModel, AuditReport)
    progress = Signal(int, int, str)   # (current, total, message)
    error = Signal(str)

    def __init__(self, filepath: str, password: Optional[str] = None):
        super().__init__()
        self.filepath = filepath
        self.password = password

    def run(self):
        try:
            self.progress.emit(1, 10, "Parsing PDF structure and dictionaries...")
            parser = DocumentParser(self.filepath, password=self.password)
            doc_model = parser.parse()

            self.progress.emit(3, 10, "Executing PDF/UA, WCAG, and Quality checks...")
            runner = AuditRunner()

            def on_progress(cur, tot, msg):
                self.progress.emit(3 + int(cur / tot * 6), 10, msg)

            report = runner.run(doc_model, progress_callback=on_progress)
            self.progress.emit(10, 10, "Audit completed successfully.")
            self.finished.emit(doc_model, report)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """Primary application window for PDF Accessibility Inspector."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Accessibility Inspector")
        self.setAcceptDrops(True)
        self.setMinimumSize(960, 580)

        # Screen-aware default dimensions centered safely on the current display
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            init_w = min(1200, max(960, int(avail.width() * 0.90)))
            init_h = min(780, max(580, int(avail.height() * 0.90)))
            self.resize(init_w, init_h)
            pos_x = avail.x() + (avail.width() - init_w) // 2
            pos_y = avail.y() + (avail.height() - init_h) // 2
            self.move(max(avail.x(), pos_x), max(avail.y(), pos_y))
        else:
            self.resize(1100, 700)

        self.current_filepath: Optional[str] = None
        self.current_password: Optional[str] = None
        self.current_doc: Optional[PDFDocumentModel] = None
        self.current_report: Optional[AuditReport] = None
        self.audit_thread: Optional[QThread] = None
        self._is_loading: bool = False

        self._init_ui()
        self._apply_theme()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Top Bar
        self.top_bar = TopBar()
        self.top_bar.open_pdf_requested.connect(self.action_open_pdf)
        self.top_bar.batch_scan_requested.connect(lambda: self.sidebar.select_page("Batch Scan"))
        self.top_bar.rescan_requested.connect(self.action_rescan)
        self.top_bar.export_report_requested.connect(self.action_export_report)
        self.top_bar.settings_requested.connect(self.action_show_settings)
        self.top_bar.about_requested.connect(self.action_show_about)
        self.top_bar.help_requested.connect(self.action_show_help)
        self.top_bar.navigation_requested.connect(self._on_navigation)
        root_layout.addWidget(self.top_bar)

        # 2. Main Horizontal Splitter (Sidebar | Center Stack | Right Panel)
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setHandleWidth(1)
        self.main_splitter.setChildrenCollapsible(False)

        # Left Sidebar
        self.sidebar = Sidebar()
        self.sidebar.setObjectName("leftSidebar")
        self.sidebar.page_selected.connect(self._on_navigation)
        self.main_splitter.addWidget(self.sidebar)
        self.main_splitter.setCollapsible(0, False)

        # Center Stacked Widget
        self.center_stack = QStackedWidget()

        # Views
        self.dashboard_view = DashboardView()
        self.dashboard_view.open_pdf_requested.connect(self.action_open_pdf)
        self.dashboard_view.view_details_requested.connect(lambda: self.sidebar.select_page("Detailed Findings"))
        self.dashboard_view.view_pdf_requested.connect(lambda: self.sidebar.select_page("PDF Viewer"))
        self.dashboard_view.export_report_requested.connect(self.action_export_report)
        self.dashboard_view.finding_selected.connect(self._on_finding_selected)
        self.center_stack.addWidget(self.dashboard_view)  # 0

        self.checkpoints_view = CheckpointsView()
        self.checkpoints_view.request_rescan.connect(self.action_rescan)
        self.checkpoints_view.request_detailed_results.connect(lambda: self.sidebar.select_page("Detailed Findings"))
        self.checkpoints_view.request_pdf_report.connect(self.action_export_report)
        self.checkpoints_view.request_tag_tree.connect(lambda: self.sidebar.select_page("Tag Tree"))
        self.checkpoints_view.request_statistics.connect(lambda: self.sidebar.select_page("Statistics"))
        self.checkpoints_view.request_preview.connect(lambda: self.sidebar.select_page("Semantic Reading Preview"))
        self.checkpoints_view.category_clicked.connect(self._on_checkpoint_category_clicked)
        self.checkpoints_view.category_selected.connect(self._on_checkpoint_category_selected)
        self.center_stack.addWidget(self.checkpoints_view)  # 1

        self.detailed_view = DetailedResultsView()
        self.detailed_view.finding_selected.connect(self._on_finding_selected)
        self.detailed_view.finding_double_clicked.connect(self._on_finding_double_clicked)
        self.center_stack.addWidget(self.detailed_view)  # 2

        self.pdf_viewer = PDFCanvas()
        self.pdf_viewer.finding_navigation_requested.connect(self._on_finding_navigate)
        self.center_stack.addWidget(self.pdf_viewer)  # 3


        self.tag_tree_view = TagTreeView()
        self.tag_tree_view.tag_selected.connect(self._on_tag_tree_selected)
        self.center_stack.addWidget(self.tag_tree_view)  # 4

        self.screen_reader_view = ScreenReaderView()
        self.center_stack.addWidget(self.screen_reader_view)  # 5

        self.metadata_view = MetadataView()
        self.center_stack.addWidget(self.metadata_view)  # 6

        self.statistics_view = StatisticsView()
        self.center_stack.addWidget(self.statistics_view)  # 7

        self.elements_view = ElementsView()
        self.elements_view.element_jump_requested.connect(self._on_element_jump_requested)
        self.center_stack.addWidget(self.elements_view)  # 8

        self.batch_view = BatchScanView()
        self.batch_view.document_opened.connect(self.load_pdf_file)
        self.center_stack.addWidget(self.batch_view)  # 9

        self.loading_view = LoadingView()
        self.center_stack.addWidget(self.loading_view)  # 10

        self.main_splitter.addWidget(self.center_stack)

        # Right Inspector Panel
        self.right_panel = FindingDetailsPanel()
        self.right_panel.setObjectName("findingDetailsPanel")
        self.right_panel.highlight_requested.connect(self._on_highlight_requested)
        self.main_splitter.addWidget(self.right_panel)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setCollapsible(2, False)

        # Set initial splitter stretch ratios and explicit proportions
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.main_splitter.setSizes([245, 625, 350])

        root_layout.addWidget(self.main_splitter)

        # 3. Status Bar with Progress
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.lbl_status = QLabel("Ready")
        self.status_bar.addWidget(self.lbl_status, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

    def _apply_theme(self):
        """Loads and applies the QSS theme."""
        theme_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "styles", "theme.qss")
        if os.path.exists(theme_path):
            with open(theme_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def _ensure_onscreen_geometry(self):
        """Guarantees window geometry stays fully visible and never placed off-screen."""
        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return
        avail = screen.availableGeometry()
        geo = self.geometry()

        # If window exceeds available screen size, clamp it
        new_w = min(geo.width(), avail.width())
        new_h = min(geo.height(), avail.height())
        if new_w != geo.width() or new_h != geo.height():
            self.resize(new_w, new_h)
            geo = self.geometry()

        new_x = geo.x()
        new_y = geo.y()

        # If right or bottom edge overflows screen, shift inwards
        if new_x + geo.width() > avail.right() + 1:
            new_x = avail.right() + 1 - geo.width()
        if new_y + geo.height() > avail.bottom() + 1:
            new_y = avail.bottom() + 1 - geo.height()

        # Left and top screen bounds take highest priority (never off-screen)
        if new_x < avail.x():
            new_x = avail.x()
        if new_y < avail.y():
            new_y = avail.y()

        if new_x != geo.x() or new_y != geo.y():
            self.move(new_x, new_y)

    def _ensure_splitter_proportions(self):
        """Guarantees the sidebar never collapses to 0 width on small or high-DPI screens."""
        sizes = self.main_splitter.sizes()
        if len(sizes) == 3:
            total = sum(sizes)
            if total > 0 and sizes[0] < 190:
                sb_w = 230
                rp_w = min(360, max(280, sizes[2])) if sizes[2] > 0 else 0
                cs_w = max(400, total - sb_w - rp_w)
                self.main_splitter.setSizes([sb_w, cs_w, rp_w])

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_splitter_proportions()
        self._ensure_onscreen_geometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ensure_splitter_proportions()

    def changeEvent(self, event: QEvent):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            # When unmaximizing, restoring down, or restoring from taskbar
            if not (self.windowState() & (Qt.WindowMaximized | Qt.WindowMinimized | Qt.WindowFullScreen)):
                self._ensure_onscreen_geometry()

    # --- Drag & Drop ---
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(".pdf") and os.path.exists(file_path):
                event.acceptProposedAction()
                self.load_pdf_file(file_path)
                return

    # --- Actions ---
    def action_open_pdf(self):
        if getattr(self, "_is_loading", False):
            return
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open PDF Document", "", "PDF Files (*.pdf);;All Files (*.*)"
        )
        if filepath:
            self.load_pdf_file(filepath)

    def action_rescan(self):
        if getattr(self, "_is_loading", False):
            return
        if self.current_filepath and os.path.exists(self.current_filepath):
            self.load_pdf_file(self.current_filepath)

    def load_pdf_file(self, filepath: str, password: Optional[str] = None):
        """Launches the background audit thread to inspect the PDF."""
        self._is_loading = True
        self.current_filepath = filepath
        self.current_password = password
        self.lbl_status.setText(f"Analyzing {os.path.basename(filepath)}...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.top_bar.set_document_info(os.path.basename(filepath), None, "Analyzing...")

        # Show prominent loading screen in middle of page
        self.loading_view.start(os.path.basename(filepath))
        self.center_stack.setCurrentWidget(self.loading_view)

        # Open in PDF viewer canvas for snappy feedback
        try:
            self.pdf_viewer.load_document(filepath, password=password)
        except Exception:
            pass

        # Start background worker
        self.audit_thread = QThread()
        self.worker = AuditWorker(filepath, password=password)
        self.worker.moveToThread(self.audit_thread)

        self.audit_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_audit_progress)
        self.worker.finished.connect(self._on_audit_finished)
        self.worker.error.connect(self._on_audit_error)

        self.worker.finished.connect(self.audit_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.audit_thread.finished.connect(self.audit_thread.deleteLater)

        self.audit_thread.start()

    def _on_audit_progress(self, current: int, total: int, msg: str):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.lbl_status.setText(msg)
        self.loading_view.set_progress(current, total, msg)

    def _on_audit_finished(self, doc: PDFDocumentModel, report: AuditReport):
        self._is_loading = False
        if hasattr(self, "loading_view"):
            self.loading_view.stop()

        self.current_doc = doc
        self.current_report = report

        # Load into PDF viewer with unlocked credentials if needed
        try:
            self.pdf_viewer.load_document(doc.filepath, password=self.current_password)
        except Exception:
            pass
        # Clear password from memory immediately
        self.current_password = None

        self.progress_bar.setVisible(False)
        self.lbl_status.setText(
            f"Audit Completed: {doc.filename} — Score: {report.compliance_score}% "
            f"({report.total_passed} Passed, {report.total_warned} Warnings, {report.total_failed} Failures)"
        )

        self.top_bar.set_document_loaded(True)
        self.top_bar.set_document_info(doc.filename, report.compliance_score, "Completed")

        # Populate all views
        self.dashboard_view.load_document(doc, report)
        self.checkpoints_view.update_report(report, doc)
        self.detailed_view.set_findings(report.results)
        self.tag_tree_view.load_structure_tree(doc.structure_tree)
        self.screen_reader_view.load_document(doc)
        self.metadata_view.load_document(doc)
        self.statistics_view.load_report(report, doc)
        self.elements_view.load_document(doc)

        # Switch to Checkpoints view to display PAC-style matrix
        self.sidebar.select_page("Checkpoints")

        # Auto-populate right details panel with primary finding or first non-compliant category
        pdfua_counts = report.get_category_counts("PDF/UA")
        selected_cat = None
        for cat in CheckpointsView.PDF_UA_CATEGORIES:
            c_data = pdfua_counts.get(cat, {})
            if c_data.get("failed", 0) > 0 or c_data.get("warned", 0) > 0:
                selected_cat = cat
                break
        if not selected_cat and CheckpointsView.PDF_UA_CATEGORIES:
            selected_cat = CheckpointsView.PDF_UA_CATEGORIES[0]
        if selected_cat:
            self._on_checkpoint_category_clicked("PDF/UA", selected_cat)

    def _on_audit_error(self, err_msg: str):
        self._is_loading = False
        if hasattr(self, "loading_view"):
            self.loading_view.stop()

        self.top_bar.set_document_info(os.path.basename(self.current_filepath) if self.current_filepath else "-", None, "Failed")
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("Audit failed.")

        # Password required prompt
        if "Password required" in err_msg and self.current_filepath:
            pwd, ok = QInputDialog.getText(
                self, "Password Required",
                "Password required — analysis cannot continue until the document is unlocked.\n\nEnter document password:",
                QLineEdit.Password
            )
            if ok and pwd:
                self.load_pdf_file(self.current_filepath, password=pwd)
                return
            else:
                QMessageBox.warning(
                    self, "Password Required",
                    "Password required — analysis cannot continue until the document is unlocked."
                )
                self.center_stack.setCurrentIndex(0)
                return

        QMessageBox.critical(self, "Audit Error", f"Failed to analyze PDF:\n{err_msg}")
        self.center_stack.setCurrentIndex(0)

    # --- Navigation & Inter-Widget Coordination ---
    def _on_navigation(self, key: str):
        if getattr(self, "_is_loading", False):
            # When actively analyzing a document, keep the loading view visible
            return

        self.top_bar.select_tab(key)
        self.sidebar.select_page(key)

        view_map = {
            "Dashboard": 0,
            "Checkpoints": 1,
            "Detailed Findings": 2,
            "PDF Viewer": 3,
            "Tag Tree": 4,
            "Semantic Reading Preview": 5,
            "Screen Reader": 5,
            "Document Metadata": 6,
            "Statistics": 7,
            "Batch Scan": 9,
        }

        element_keys = ["Fonts", "Images", "Tables", "Links", "Forms", "Bookmarks"]
        if key in element_keys:
            self.center_stack.setCurrentIndex(8)
            self.elements_view.select_tab(key)
        elif key in view_map:
            self.center_stack.setCurrentIndex(view_map[key])

    def _on_checkpoint_category_clicked(self, standard: str, category: str):
        """User single clicked a checkpoint category in Checkpoints view; preview in Right Panel."""
        if not self.current_report:
            return
        if standard.upper() == "QUALITY":
            rule_ids = CheckpointsView.QUALITY_RULE_MAPPINGS.get(category, [])
            cat_findings = [
                r for r in self.current_report.results
                if r.check_id in rule_ids
            ]
            p = sum(r.items_count for r in cat_findings if r.status == CheckStatus.PASS)
            w = sum(r.items_count for r in cat_findings if r.status == CheckStatus.WARNING)
            f = sum(r.items_count for r in cat_findings if r.status in (CheckStatus.FAIL, CheckStatus.ERROR))
            m = sum(r.items_count for r in cat_findings if r.status == CheckStatus.MANUAL_REVIEW)
            counts = {"passed": p, "warned": w, "failed": f, "manual": m}
        else:
            cat_findings = [
                r for r in self.current_report.results
                if r.standard.upper() == standard.upper() and self.detailed_view._matches_category(r, category)
            ]
            counts = self.current_report.get_category_counts(standard).get(
                category, {"passed": 0, "warned": 0, "failed": 0, "manual": 0}
            )
        self.right_panel.display_category_summary(standard, category, counts, cat_findings)

    def _on_checkpoint_category_selected(self, standard: str, category: str):
        """User clicked or selected a checkpoint category in Checkpoints view; jump to Detailed Findings."""
        if standard.upper() == "QUALITY":
            rule_ids = CheckpointsView.QUALITY_RULE_MAPPINGS.get(category, [])
            self.detailed_view.filter_by_rule_ids(rule_ids, standard="Quality", category_label=category)
        else:
            self.detailed_view.filter_by_category(standard, category)
        self.sidebar.select_page("Detailed Findings")

        if self.detailed_view.filtered_findings:
            self.detailed_view.table.selectRow(0)
            first_finding = self.detailed_view.filtered_findings[0]
            self.right_panel.display_finding(first_finding)
            if self.current_doc and first_finding.page:
                target_page = first_finding.page or 1
                self.pdf_viewer.go_to_page(
                    target_page,
                    first_finding.bounding_box,
                    finding=first_finding,
                    doc_model=self.current_doc
                )

    def _on_finding_selected(self, finding: CheckResult):
        """User clicked a finding in Detailed Findings table; display in right panel and navigate canvas to location."""
        self.right_panel.display_finding(finding)
        if self.current_doc and finding and finding.page:
            target_page = finding.page or 1
            self.pdf_viewer.go_to_page(
                target_page,
                finding.bounding_box,
                finding=finding,
                doc_model=self.current_doc
            )

    def _on_finding_double_clicked(self, finding: CheckResult):
        """User double clicked a finding; jump directly to page and highlight in PAC Visual Locator."""
        self.right_panel.display_finding(finding)
        self.sidebar.select_page("PDF Viewer")
        target_page = finding.page or 1
        self.pdf_viewer.go_to_page(target_page, finding.bounding_box, finding=finding, doc_model=self.current_doc)

    def _on_highlight_requested(self, page: int, bbox):
        """User clicked [Highlight on Page] button in Right Panel; display in PAC Visual Locator."""
        self.sidebar.select_page("PDF Viewer")
        finding = self.right_panel.current_finding
        target_page = page or (finding.page if finding else 1) or 1
        self.pdf_viewer.go_to_page(target_page, bbox, finding=finding, doc_model=self.current_doc)

    def _on_finding_navigate(self, offset: int):
        """Cycle to previous or next finding in PAC visual locator."""
        if not self.current_report or not self.current_report.results:
            return
        results = [r for r in self.current_report.results if r.status.is_problem or r.page is not None]
        if not results:
            results = self.current_report.results

        current = self.pdf_viewer.current_finding
        idx = 0
        if current in results:
            idx = results.index(current)
        new_idx = (idx + offset) % len(results)
        next_finding = results[new_idx]

        self.right_panel.display_finding(next_finding)
        target_page = next_finding.page or 1
        self.pdf_viewer.go_to_page(target_page, next_finding.bounding_box, finding=next_finding, doc_model=self.current_doc)

    def _on_tag_tree_selected(self, node):
        """User selected a node in the structure tag tree."""
        if node.page:
            self.pdf_viewer.go_to_page(node.page, node.bbox, doc_model=self.current_doc)

    def _on_element_jump_requested(self, page: int, bbox=None):
        """User double clicked an element in Elements view; navigate and illuminate."""
        if page:
            self.sidebar.select_page("PDF Viewer")
            self.pdf_viewer.go_to_page(page, bbox, doc_model=self.current_doc)


    def action_export_report(self):
        if not self.current_report or not self.current_doc:
            QMessageBox.information(self, "No Document", "Please open and audit a PDF document first.")
            return

        base_name = os.path.splitext(self.current_doc.filename)[0]
        dlg = ExportDialog(default_filename=base_name, parent=self)
        if dlg.exec():
            fmt = dlg.selected_format
            out_path = dlg.selected_filepath

            try:
                if fmt == "pdf":
                    PDFReportGenerator.generate(self.current_report, out_path)
                elif fmt == "html":
                    HTMLReportGenerator.generate(self.current_report, out_path)
                elif fmt == "json":
                    JSONExporter.export(self.current_report, out_path)
                elif fmt == "csv":
                    CSVExporter.export(self.current_report, out_path)

                reply = QMessageBox.question(
                    self, "Report Exported",
                    f"Report saved successfully to:\n{out_path}\n\nWould you like to open it now?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    if sys.platform == "win32":
                        os.startfile(out_path)
                    else:
                        subprocess.run(["xdg-open", out_path])
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Could not generate report:\n{str(e)}")

    def action_show_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def action_show_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    def action_show_help(self):
        QMessageBox.information(
            self, "Help & Documentation",
            "PDF Accessibility Inspector Guide:\n\n"
            "1. Open a PDF document using the 'Open PDF' button or by dragging and dropping it into the window.\n"
            "2. Inspect the Checkpoints matrix (PDF/UA, WCAG, Quality, AI) for category summaries.\n"
            "3. Click 'Results in detail' to inspect individual findings, technical evidence, and remediation advice.\n"
            "4. Click 'Highlight on Page' to jump directly to the PDF page and view the illuminated element.\n"
            "5. Explore the Logical Tag Tree and Screen Reader Preview to hear how assistive technology voices the file.\n"
            "6. Export publication-grade PDF, HTML, or machine-readable JSON reports."
        )
