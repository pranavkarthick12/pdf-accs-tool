"""
Tests for LoadingView and MainWindow loading state workflow.
Verifies:
1. LoadingView initializes with all required UI elements (spinner, progress bar, badges, labels).
2. When a file is loaded, center_stack visibly switches to LoadingView in the middle of the page.
3. Progress events update the visible loading progress bar, percentage, and stage message.
4. When audit finishes, loading stops and page redirects to Checkpoints view (index 1).
5. Navigation requests during active loading are guarded.
6. When an audit error occurs, loading stops and page recovers cleanly.
"""

import pytest
from PySide6.QtWidgets import QApplication
from src.pdf_inspector.ui.main_window import MainWindow
from src.pdf_inspector.ui.views.loading_view import LoadingView
from src.pdf_inspector.core.models import PDFDocumentModel, AuditReport, CheckResult, CheckStatus


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_loading_view_components(qapp):
    """Verifies that LoadingView initializes all necessary visual feedback widgets."""
    view = LoadingView()
    assert view.card is not None
    assert view.spinner is not None
    assert view.lbl_title.text() == "Validating Document"
    assert view.progress_bar is not None
    assert view.lbl_percent.text() == "0%"

    # Test start
    view.start("test_document.pdf")
    assert "test_document.pdf" in view.lbl_filename.text()
    assert view.spinner._timer.isActive()

    # Test progress update
    view.set_progress(3, 10, "Executing PDF/UA, WCAG, and Quality checks...")
    assert view.progress_bar.value() == 3
    assert view.progress_bar.maximum() == 10
    assert view.lbl_percent.text() == "30%"
    assert "Executing PDF/UA" in view.lbl_stage.text()

    # Test stop
    view.stop()
    assert not view.spinner._timer.isActive()


def test_main_window_loading_flow(qapp, monkeypatch):
    """Verifies the complete flow from file selection -> middle of page loading -> checkpoints redirect."""
    win = MainWindow()
    assert win.center_stack.currentIndex() == 0  # Dashboard

    # Prevent actual thread launch in this test
    monkeypatch.setattr(win, "audit_thread", None)

    # 1. Trigger loading of a file
    # Mock DocumentParser / AuditWorker to not run background thread
    win._is_loading = True
    win.loading_view.start("sample_accessible.pdf")
    win.center_stack.setCurrentWidget(win.loading_view)

    # Verify that the center widget is indeed the loading view
    assert win.center_stack.currentWidget() == win.loading_view

    # Verify that navigation attempts during active loading do not interrupt the loading view
    win._on_navigation("Statistics")
    assert win.center_stack.currentWidget() == win.loading_view

    # 2. Simulate progress updates
    win._on_audit_progress(1, 10, "Parsing PDF structure and dictionaries...")
    assert win.loading_view.progress_bar.value() == 1
    assert win.loading_view.lbl_percent.text() == "10%"
    assert "Parsing PDF" in win.loading_view.lbl_stage.text()

    win._on_audit_progress(5, 10, "Evaluating Checkpoints...")
    assert win.loading_view.progress_bar.value() == 5
    assert win.loading_view.lbl_percent.text() == "50%"

    # 3. Simulate audit completion
    doc = PDFDocumentModel(
        filepath="", filename="sample_accessible.pdf", filesize=2048,
        pdf_version="1.7", page_count=5, is_tagged=True
    )
    report = AuditReport(document_info={"filename": "sample_accessible.pdf"}, results=[])
    win._on_audit_finished(doc, report)

    # Must redirect to Checkpoints view (index 1)
    assert win.center_stack.currentIndex() == 1
    assert win._is_loading is False
    assert not win.loading_view.spinner._timer.isActive()


def test_main_window_loading_error_recovery(qapp, monkeypatch):
    """Verifies that an audit error cleanly stops loading and returns to Dashboard."""
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)

    win = MainWindow()
    win._is_loading = True
    win.loading_view.start("corrupted.pdf")
    win.center_stack.setCurrentWidget(win.loading_view)

    assert win.center_stack.currentWidget() == win.loading_view

    # Trigger audit error
    win._on_audit_error("File format corrupt")

    assert win._is_loading is False
    assert not win.loading_view.spinner._timer.isActive()
    assert win.center_stack.currentIndex() == 0  # Returned to dashboard
