"""
Tests for Quality Checkpoints Aggregation & Presentation Layer.
Verifies that existing and newly implemented engine findings
are correctly mapped and presented in the Quality tab without duplicate engine rules.
"""

import pytest
from PySide6.QtWidgets import QApplication
from src.pdf_inspector.core.models import PDFDocumentModel, AuditReport, CheckResult, CheckStatus, Severity
from src.pdf_inspector.ui.views.checkpoints_view import CheckpointsView
from src.pdf_inspector.ui.views.detailed_results_view import DetailedResultsView


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_quality_category_rule_mappings_coverage():
    """Verify all 15 defined Quality checkpoints map to registered engine rule IDs matching PAC."""
    expected_categories = [
        "Validity of document title",
        "Artifacted content on page body",
        "Tagged text consists of only whitespace",
        "Tagged content exists outside of the page boundaries",
        "Presence of headings",
        "Presence of bookmarks (document outline) if there are headings",
        '"TOCI" elements contain "Link" elements',
        '"TOCI" elements correctly linked to headings',
        "Alternative text on text elements",
        "Validity of alternate text",
        'Completeness of "Link" elements',
        'Formal correctness of "LI" elements',
        'Completeness of "Table" elements',
        '"Note" elements are referenced',
        '"Note" elements contain "Lbl" elements',
        '"P" elements contain "Note" elements',
    ]
    assert CheckpointsView.QUALITY_CATEGORIES == expected_categories
    assert len(CheckpointsView.QUALITY_CATEGORIES) == 16

    for cat in expected_categories:
        assert cat in CheckpointsView.QUALITY_RULE_MAPPINGS
        rule_ids = CheckpointsView.QUALITY_RULE_MAPPINGS[cat]
        assert len(rule_ids) > 0


def test_quality_checkpoints_view_aggregation(qapp):
    """Verify Quality matrix accurately counts findings mapped from existing and new engine checks."""
    doc = PDFDocumentModel(
        filepath="/test/sample.pdf",
        filename="sample.pdf",
        filesize=1024,
        pdf_version="1.7",
        page_count=5,
        title="Valid Title",
        is_tagged=True
    )

    results = [
        # Validity of document title
        CheckResult(
            check_id="QUAL-TITLE-001",
            name="Validity of Document Title",
            category="Validity of document title",
            standard="Quality",
            status=CheckStatus.PASS,
            severity=Severity.HIGH,
            message="Title is valid"
        ),

        # Presence of headings
        CheckResult(
            check_id="QUAL-HEAD-001",
            name="Heading Hierarchy Integrity",
            category="Heading Structure",
            standard="Quality",
            status=CheckStatus.WARNING,
            severity=Severity.MEDIUM,
            message="Skipped heading level"
        ),
        # Completeness of "Link" elements
        CheckResult(
            check_id="QUAL-LINK-001",
            name="Meaningful Link Labels",
            category="Link Quality",
            standard="Quality",
            status=CheckStatus.PASS,
            severity=Severity.LOW,
            message="All links meaningful"
        ),
        # Completeness of "Table" elements
        CheckResult(
            check_id="QUAL-TABLE-001",
            name="Table Regularity & Symmetry",
            category="Table Quality",
            standard="Quality",
            status=CheckStatus.PASS,
            severity=Severity.LOW,
            message="Tables regular"
        ),
        # Tagged content exists outside the page boundaries
        CheckResult(
            check_id="QUAL-BOUND-001",
            name="Tagged Content Page Boundaries",
            category="Content Quality",
            standard="Quality",
            status=CheckStatus.PASS,
            severity=Severity.HIGH,
            message="All content in bounds"
        ),
    ]

    report = AuditReport(document_info={"filename": doc.filename}, results=results)

    view = CheckpointsView()
    view.update_report(report, doc)

    # 1. Validity of document title (row 0): 1 passed (META-002)
    item_title_name = view.table_quality.item(0, 0).text()
    item_title_pass = view.table_quality.item(0, 1).text()
    item_title_warn = view.table_quality.item(0, 2).text()
    item_title_fail = view.table_quality.item(0, 3).text()
    assert "✅" in item_title_name
    assert item_title_pass == "1"
    assert item_title_warn == "-"
    assert item_title_fail == "-"

    # 4. Tagged content exists outside the page boundaries (row 3): 1 passed
    item_bound_name = view.table_quality.item(3, 0).text()
    item_bound_pass = view.table_quality.item(3, 1).text()
    assert "✅" in item_bound_name
    assert item_bound_pass == "1"

    # 5. Presence of headings (row 4): 1 warned (QUAL-HEAD-001)
    item_head_name = view.table_quality.item(4, 0).text()
    item_head_pass = view.table_quality.item(4, 1).text()
    item_head_warn = view.table_quality.item(4, 2).text()
    item_head_fail = view.table_quality.item(4, 3).text()
    assert "⚠️" in item_head_name
    assert item_head_pass == "-"
    assert item_head_warn == "1"
    assert item_head_fail == "-"

    # Unpopulated checkpoint shows '-' and '⊘' (e.g. row 6: TOCI elements contain Link elements)
    item_toci_name = view.table_quality.item(6, 0).text()
    item_toci_pass = view.table_quality.item(6, 1).text()
    item_toci_warn = view.table_quality.item(6, 2).text()
    item_toci_fail = view.table_quality.item(6, 3).text()
    assert "⊘" in item_toci_name
    assert item_toci_pass == "-"
    assert item_toci_warn == "-"
    assert item_toci_fail == "-"


def test_detailed_results_filter_by_rule_ids(qapp):
    """Verify DetailedResultsView can filter directly by rule IDs when navigating from Quality checkpoint."""
    results = [
        CheckResult(
            check_id="QUAL-TITLE-001",
            name="Validity of Document Title",
            category="Validity of document title",
            standard="Quality",
            status=CheckStatus.PASS,
            severity=Severity.HIGH,
            message="Title is valid"
        ),
        CheckResult(
            check_id="PDFUA-FIG-001",
            name="Figure Bounding Box",
            category="Graphics",
            standard="PDF/UA",
            status=CheckStatus.PASS,
            severity=Severity.HIGH,
            message="Figure BBox valid"
        ),
        CheckResult(
            check_id="QUAL-HEAD-001",
            name="Heading Hierarchy Integrity",
            category="Heading Structure",
            standard="Quality",
            status=CheckStatus.WARNING,
            severity=Severity.MEDIUM,
            message="Skipped heading level"
        ),
    ]

    view = DetailedResultsView()
    view.set_findings(results)
    assert len(view.filtered_findings) == 3

    # Filter by "Validity of document title" mapped rule IDs
    title_rules = CheckpointsView.QUALITY_RULE_MAPPINGS["Validity of document title"]
    view.filter_by_rule_ids(title_rules, standard="All Standards", category_label="Validity of document title")

    assert len(view.filtered_findings) == 1
    assert view.filtered_findings[0].check_id == "QUAL-TITLE-001"


def test_quality_tab_switching_and_category_sync(qapp):
    """Verify switching to the Quality tab auto-selects the first issue/pass and emits category_clicked."""
    view = CheckpointsView()
    doc = PDFDocumentModel(
        filepath="/test/sample.pdf",
        filename="sample.pdf",
        filesize=1024,
        pdf_version="1.7",
        page_count=5,
        title="Valid Title",
        is_tagged=True
    )
    results = [
        CheckResult(
            check_id="QUAL-WHITE-001",
            name="Tagged text consists of only whitespace",
            category="Content Quality",
            standard="Quality",
            status=CheckStatus.WARNING,
            severity=Severity.MEDIUM,
            message="4 whitespace elements found",
            items_count=4
        ),
    ]
    report = AuditReport(document_info={"filename": doc.filename}, results=results)
    view.update_report(report, doc)

    emitted_signals = []
    view.category_clicked.connect(lambda std, cat: emitted_signals.append((std, cat)))

    # Switch to Quality tab (index 2)
    view.tab_widget.setCurrentIndex(2)

    assert len(emitted_signals) > 0
    std, cat = emitted_signals[-1]
    assert std == "Quality"
    assert cat == "Tagged text consists of only whitespace"
    assert view.table_quality.currentRow() == 2


def test_btn_detail_clicked_navigates_to_quality_checkpoint(qapp):
    """Verify clicking 'Results in detail' on Quality tab emits category_selected for the active checkpoint."""
    view = CheckpointsView()
    doc = PDFDocumentModel(
        filepath="/test/sample.pdf",
        filename="sample.pdf",
        filesize=1024,
        pdf_version="1.7",
        page_count=5,
        title="Valid Title",
        is_tagged=True
    )
    report = AuditReport(document_info={"filename": doc.filename}, results=[])
    view.update_report(report, doc)

    # Switch to Quality tab
    view.tab_widget.setCurrentIndex(2)
    view.table_quality.setCurrentCell(0, 0)
    view.table_quality.selectRow(0)

    selected_signals = []
    view.category_selected.connect(lambda std, cat: selected_signals.append((std, cat)))

    # Trigger Results in detail
    view._on_btn_detail_clicked()

    assert len(selected_signals) == 1
    std, cat = selected_signals[0]
    assert std == "Quality"
    assert cat == "Validity of document title"


def test_quality_filter_by_rule_ids_with_quality_standard(qapp):
    """Verify DetailedResultsView correctly filters by rule IDs with standard='Quality'."""
    results = [
        CheckResult(
            check_id="QUAL-WHITE-001",
            name="Tagged text consists of only whitespace",
            category="Content Quality",
            standard="Quality",
            status=CheckStatus.WARNING,
            severity=Severity.MEDIUM,
            message="4 whitespace elements"
        ),
        CheckResult(
            check_id="PDFUA-CONTENT-001",
            name="Artifacted content",
            category="Content",
            standard="PDF/UA",
            status=CheckStatus.FAIL,
            severity=Severity.HIGH,
            message="Untagged content"
        ),
    ]

    view = DetailedResultsView()
    view.set_findings(results)

    # Filter with standard="Quality"
    view.filter_by_rule_ids(["QUAL-WHITE-001"], standard="Quality", category_label="Tagged text consists of only whitespace")

    assert len(view.filtered_findings) == 1
    assert view.filtered_findings[0].check_id == "QUAL-WHITE-001"
    assert view.combo_std.currentText() == "Quality"


def test_validity_of_alternate_text_mapping_and_navigation(qapp):
    """Verify Validity of alternate text checkpoint maps to QUAL-ALT-001 and integrates with Quality UI table."""
    assert "Validity of alternate text" in CheckpointsView.QUALITY_RULE_MAPPINGS
    assert CheckpointsView.QUALITY_RULE_MAPPINGS["Validity of alternate text"] == ["QUAL-ALT-001"]

    row_index = CheckpointsView.QUALITY_CATEGORIES.index("Validity of alternate text")
    assert row_index == 9

    doc = PDFDocumentModel(
        filepath="/test/sample.pdf",
        filename="sample.pdf",
        filesize=1024,
        pdf_version="1.7",
        page_count=3,
        title="Valid Title",
        is_tagged=True
    )

    # 1. Test when QUAL-ALT-001 has valid descriptions (PASS) and placeholder descriptions (WARNING)
    results = [
        CheckResult(
            check_id="QUAL-ALT-001",
            name="Validity of Alternate Text",
            category="Alternative Text Quality",
            standard="Quality",
            status=CheckStatus.WARNING,
            severity=Severity.MEDIUM,
            message="Alternative text for <Figure> on page 1 is a generic placeholder: 'image'.",
            items_count=1,
            page=1
        ),
        CheckResult(
            check_id="QUAL-ALT-001",
            name="Validity of Alternate Text",
            category="Alternative Text Quality",
            standard="Quality",
            status=CheckStatus.PASS,
            severity=Severity.HIGH,
            message="2 alternative text description(s) are valid and meaningful.",
            items_count=2,
            page=2
        ),
    ]

    report = AuditReport(document_info={"filename": doc.filename}, results=results)
    counts = report.get_category_counts("Quality")
    assert counts["Validity of alternate text"]["warned"] == 1
    assert counts["Validity of alternate text"]["passed"] == 2
    assert counts["Validity of alternate text"]["failed"] == 0

    view = CheckpointsView()
    view.update_report(report, doc)

    item_name = view.table_quality.item(row_index, 0).text()
    item_pass = view.table_quality.item(row_index, 1).text()
    item_warn = view.table_quality.item(row_index, 2).text()
    item_fail = view.table_quality.item(row_index, 3).text()

    assert "⚠️" in item_name
    assert "Validity of alternate text" in item_name
    assert item_pass == "2"
    assert item_warn == "1"
    assert item_fail == "-"

    # Test filtering in DetailedResultsView
    d_view = DetailedResultsView()
    d_view.set_findings(results)
    rule_ids = CheckpointsView.QUALITY_RULE_MAPPINGS["Validity of alternate text"]
    d_view.filter_by_rule_ids(rule_ids, standard="Quality", category_label="Validity of alternate text")
    assert len(d_view.filtered_findings) == 2
    assert all(f.check_id == "QUAL-ALT-001" for f in d_view.filtered_findings)


def test_quality_banner_sad_emoji_when_artifact_error_pops(qapp):
    """Verify sad emoji (🙁) is displayed on Quality heading when 'Artifacted content on page body' pops."""
    doc = PDFDocumentModel(filepath="", filename="test.pdf", filesize=10, pdf_version="1.7", page_count=1)
    results = [
        CheckResult(
            check_id="QUAL-ART-001",
            name="Artifacted Content on Page Body",
            category="Content Quality",
            standard="Quality",
            status=CheckStatus.WARNING,
            severity=Severity.HIGH,
            message="Artifact on page body contains text.",
            items_count=2,
            page=1
        )
    ]
    report = AuditReport(document_info={"filename": doc.filename}, results=results)
    view = CheckpointsView()
    view.update_report(report, doc)

    assert "🙁" in view.lbl_quality_banner.text()
    assert "This document has potential quality issues." in view.lbl_quality_banner.text()


def test_quality_banner_no_sad_emoji_when_no_artifact_error(qapp):
    """Verify sad emoji is NOT displayed when 'Artifacted content on page body' does not pop."""
    doc = PDFDocumentModel(filepath="", filename="test.pdf", filesize=10, pdf_version="1.7", page_count=1)
    # Case A: Another quality error pops (e.g. title) -> heading banner shows standard text without emoji
    results_title = [
        CheckResult(
            check_id="QUAL-TITLE-001",
            name="Validity of Document Title",
            category="Document Title Quality",
            standard="Quality",
            status=CheckStatus.WARNING,
            severity=Severity.HIGH,
            message="Document title is missing.",
            items_count=1,
            page=1
        )
    ]
    report_title = AuditReport(document_info={"filename": doc.filename}, results=results_title)
    view = CheckpointsView()
    view.update_report(report_title, doc)
    assert "🙁" not in view.lbl_quality_banner.text()
    assert view.lbl_quality_banner.text() == "This document has potential quality issues."

    # Case B: Document has no quality issues
    results_pass = [
        CheckResult(
            check_id="QUAL-TITLE-001",
            name="Validity of Document Title",
            category="Document Title Quality",
            standard="Quality",
            status=CheckStatus.PASS,
            severity=Severity.HIGH,
            message="Document title is valid.",
            items_count=1,
            page=1
        )
    ]
    report_pass = AuditReport(document_info={"filename": doc.filename}, results=results_pass)
    view.update_report(report_pass, doc)
    assert "🙁" not in view.lbl_quality_banner.text()
    assert view.lbl_quality_banner.text() == "This document has no quality issues."
