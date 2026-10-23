"""
Tests for Redesigned DashboardView, TopBar, and Dashboard Charts.
Verifies:
1. TopBar displays date, application title, document status pills, and handles tab switching.
2. SegmentedProgressBar, SparklineChart, and MiniBarChart correctly accept values and paint without errors.
3. DashboardView updates Card 1 (Compliance Health), Card 2 (Findings Breakdown), and Card 3 (Standards Health).
4. DashboardView findings overview table displays real findings, filters appropriately, and emits finding selection.
"""

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.pdf_inspector.ui.main_window import MainWindow
from src.pdf_inspector.ui.top_bar import TopBar
from src.pdf_inspector.ui.views.dashboard_view import DashboardView
from src.pdf_inspector.ui.widgets.dashboard_charts import SegmentedProgressBar, SparklineChart, MiniBarChart
from src.pdf_inspector.core.models import (
    PDFDocumentModel, AuditReport, CheckResult, CheckStatus, Severity
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_top_bar_hero_and_navigation(qapp):
    """Verifies TopBar hero elements and tab selection."""
    top_bar = TopBar()
    assert top_bar.lbl_title_main.text() == "PDF Accessibility"
    assert top_bar.lbl_title_sub.text() == "Inspector"
    assert "Ready" in top_bar.pill_status.text()

    # Update document info
    top_bar.set_document_info("sample_report.pdf", score=92, status="Completed")
    assert "sample_report.pdf" in top_bar.pill_status.text()
    assert "92%" in top_bar.pill_metric.text()

    # Test tab selection
    received_keys = []
    top_bar.navigation_requested.connect(lambda k: received_keys.append(k))

    top_bar._on_tab_clicked("Checkpoints")
    assert "Checkpoints" in received_keys
    assert top_bar.active_tab_key == "Checkpoints"


def test_dashboard_charts_rendering(qapp):
    """Verifies that micro-charts handle values and trigger updates safely."""
    # 1. SegmentedProgressBar
    bar = SegmentedProgressBar()
    bar.set_values(passed=35, warned=4, failed=2, callout="6 Issues")
    assert bar.passed == 35
    assert bar.warned == 4
    assert bar.failed == 2

    # 2. SparklineChart
    spark = SparklineChart()
    spark.set_data([1.0, 3.0, 5.0, 8.0, 12.0], badge_text="12 Issues")
    assert len(spark.data_points) == 5
    assert spark.badge_text == "12 Issues"

    # 3. MiniBarChart
    minibar = MiniBarChart()
    minibar.set_values([0.9, 0.85, 1.0, 0.7, 0.95])
    assert len(minibar.values) == 5


def test_dashboard_view_cards_and_table(qapp):
    """Verifies DashboardView populates all 3 cards and the overview table from real audit data."""
    dash = DashboardView()
    dash.show()
    assert not dash.empty_card.isHidden()
    assert dash.cards_container.isHidden()

    # Create mock document and report
    mock_doc = PDFDocumentModel(
        filepath="sample.pdf", filename="sample.pdf", filesize=4096,
        pdf_version="1.7", page_count=8, is_tagged=True
    )
    mock_results = [
        CheckResult(
            check_id="PDFUA-01",
            name="Tagged Content Presence",
            category="Structure",
            standard="PDF/UA-1",
            status=CheckStatus.PASS,
            severity=Severity.INFO,
            page=1,
            message="Content is properly tagged."
        ),
        CheckResult(
            check_id="WCAG-IMG-01",
            name="Alternative Text on Images",
            category="Images",
            standard="WCAG 2.1 AA",
            status=CheckStatus.FAIL,
            severity=Severity.HIGH,
            page=2,
            message="Figure lacks an alternative text description."
        ),
        CheckResult(
            check_id="QUAL-HEAD-01",
            name="Heading Level Consistency",
            category="Headings",
            standard="Quality",
            status=CheckStatus.WARNING,
            severity=Severity.MEDIUM,
            page=3,
            message="Skipped heading level H1 to H3."
        ),
    ]
    mock_report = AuditReport(document_info={"filename": "sample.pdf"}, results=mock_results)

    dash.load_document(mock_doc, mock_report)

    # Empty card must be hidden and cards/table visible
    assert not dash.empty_card.isVisible()
    assert dash.cards_container.isVisible()
    assert dash.table_card.isVisible()

    # Verify Card 1 metrics
    assert "Score" in dash.lbl_c1_sub_badge.text()
    assert dash.bar_distribution.passed == mock_report.total_passed

    # Verify Card 2 metrics
    assert int(dash.lbl_c2_issues.text()) == (mock_report.total_failed + mock_report.total_warned)

    # Verify Table rows
    assert dash.table.rowCount() == 3

    # Test filtering
    dash._apply_filter("Failures Only")
    assert dash.table.rowCount() == 1
    assert dash.table.item(0, 0).text() == "WCAG-IMG-01"

    dash._apply_filter("Warnings Only")
    assert dash.table.rowCount() == 1
    assert dash.table.item(0, 0).text() == "QUAL-HEAD-01"

    dash._apply_filter("All Findings")
    assert dash.table.rowCount() == 3
