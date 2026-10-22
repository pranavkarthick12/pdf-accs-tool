"""
Test DetailedResultsView and CheckpointsView redirection and category filtering.
Verifies that redirecting to Detailed Results for "Content" shows only Content findings
and does not incorrectly include Alternative Descriptions or Syntax findings whose
evidence or messages contain the word 'content'.
"""

import os
import sys
import pytest
from PySide6.QtWidgets import QApplication

# Ensure offscreen Qt platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"
app = QApplication.instance() or QApplication(sys.argv)

from src.pdf_inspector.core.models import CheckResult, CheckStatus, Severity
from src.pdf_inspector.ui.views.detailed_results_view import DetailedResultsView
from src.pdf_inspector.ui.views.checkpoints_view import CheckpointsView


def test_detailed_results_content_redirection_isolation():
    view = DetailedResultsView()

    findings = [
        # 1. Content failure (Untagged content)
        CheckResult(
            check_id="PDFUA-CONTENT-002",
            name="Real Content Tagged",
            category="Content",
            standard="PDF/UA",
            status=CheckStatus.FAIL,
            severity=Severity.HIGH,
            message="Page 227 contains real content that is neither enclosed in marked content (/MCID) nor marked as an Artifact.",
            evidence='Unmarked real content on page 227. Content: "XObject /Fm0 Do"',
            page=227
        ),
        # 2. Content failure on another page
        CheckResult(
            check_id="PDFUA-CONTENT-002",
            name="Real Content Tagged",
            category="Content",
            standard="PDF/UA",
            status=CheckStatus.FAIL,
            severity=Severity.HIGH,
            message="Page 265 contains real content that is neither enclosed in marked content (/MCID) nor marked as an Artifact.",
            evidence='Unmarked real content on page 265. Content: "text"',
            page=265
        ),
        # 3. Content pass
        CheckResult(
            check_id="PDFUA-CONTENT-001",
            name="Tagged PDF",
            category="Content",
            standard="PDF/UA",
            status=CheckStatus.PASS,
            severity=Severity.CRITICAL,
            message="Document is explicitly marked as a Tagged PDF with a structure tree.",
            evidence="Catalog /MarkInfo /Marked is true and /StructTreeRoot exists."
        ),
        # 4. Content artifact rule (Artifacts Tagged)
        CheckResult(
            check_id="PDFUA-ART-001",
            name="Artifacts Tagged",
            category="Content",
            standard="PDF/UA",
            status=CheckStatus.PASS,
            severity=Severity.MEDIUM,
            message="Artifacts are marked according to ISO 14289-1.",
            evidence="Artifact count: 12"
        ),
        # 5. Alternative Descriptions failure (contains 'Content: ...' in evidence)
        CheckResult(
            check_id="PDFUA-ALT-001",
            name="Alternative Descriptions",
            category="Alternative Descriptions",
            standard="PDF/UA",
            status=CheckStatus.FAIL,
            severity=Severity.HIGH,
            message='Alternative text missing for "Figure" structure element',
            evidence='<Figure> on page 389 lacks alternative text (/Alt). Content: "some image label"',
            page=389
        ),
        # 6. Syntax pass (contains 'content' in message)
        CheckResult(
            check_id="PDFUA-SYNTAX-001",
            name="PDF Syntax (ISO 32000-1) Core",
            category="PDF Syntax (ISO 32000-1)",
            standard="PDF/UA",
            status=CheckStatus.PASS,
            severity=Severity.CRITICAL,
            message="Page 1 content boundaries and geometry conform to ISO 32000-1 syntax rules.",
            evidence="Page 1 boundary geometry valid.",
            page=1
        ),
        # 7. Structure elements rule with category Tables (mapped to Structure elements)
        CheckResult(
            check_id="PDFUA-TABLE-001",
            name="Table Structure",
            category="Tables",
            standard="PDF/UA",
            status=CheckStatus.PASS,
            severity=Severity.MEDIUM,
            message="Table elements conform to ISO 14289-1 structure requirements.",
            evidence="Table count: 4"
        ),
        # 8. Document settings rule with category Annotations (mapped to Document settings)
        CheckResult(
            check_id="PDFUA-ANNOT-002",
            name="Page Tab Order",
            category="Annotations",
            standard="PDF/UA",
            status=CheckStatus.PASS,
            severity=Severity.HIGH,
            message="Page tabs conform to document structure.",
            evidence="/Tabs /S configured"
        ),
    ]

    view.set_findings(findings)

    # 1. Test Redirection to "Content" checkpoint
    view.filter_by_category("PDF/UA", "Content")

    # When "All" is active, should show exactly the 4 Content findings (2 FAIL, 1 PASS Tagged PDF, 1 PASS Artifacts Tagged = 4)
    assert len(view.filtered_findings) == 4
    for r in view.filtered_findings:
        assert r.category == "Content"
    assert not any(r.check_id == "PDFUA-ALT-001" for r in view.filtered_findings)
    assert not any(r.check_id == "PDFUA-SYNTAX-001" for r in view.filtered_findings)
    assert not any(r.check_id == "PDFUA-TABLE-001" for r in view.filtered_findings)

    # 2. When switching to "Failures", should show ONLY the 2 Content failures
    view.btn_fail.setChecked(True)
    view._apply_filters()
    assert len(view.filtered_findings) == 2
    assert all(r.status == CheckStatus.FAIL for r in view.filtered_findings)
    assert all(r.check_id == "PDFUA-CONTENT-002" for r in view.filtered_findings)

    # 3. Test Redirection to "Alternative Descriptions" checkpoint
    view.filter_by_category("PDF/UA", "Alternative Descriptions")
    assert len(view.filtered_findings) == 1
    assert view.filtered_findings[0].check_id == "PDFUA-ALT-001"

    # 4. Test Redirection to "Structure elements" (verifying Tables mapped correctly)
    view.filter_by_category("PDF/UA", "Structure elements")
    assert len(view.filtered_findings) == 1
    assert view.filtered_findings[0].check_id == "PDFUA-TABLE-001"

    # 5. Test Redirection to "Document settings" (verifying Annotation tab order mapped correctly)
    view.filter_by_category("PDF/UA", "Document settings")
    assert len(view.filtered_findings) == 1
    assert view.filtered_findings[0].check_id == "PDFUA-ANNOT-002"

    # 6. Test manual search query clearing resets filter
    view.search_input.clear()
    assert len(view.filtered_findings) == 8

    # 7. Test clicking "All" button resets category filter and standard filter to display all findings
    view.filter_by_category("PDF/UA", "Content")
    assert len(view.filtered_findings) == 4
    view.btn_all.click()
    assert len(view.filtered_findings) == 8
    assert view.category_filter is None
    assert view.combo_std.currentText() == "All Standards"
    assert view.search_input.text() == ""


def test_checkpoints_btn_detail_resolves_selected_category():
    checkpoints = CheckpointsView()
    received = []
    checkpoints.category_selected.connect(lambda std, cat: received.append((std, cat)))

    # Select row "Content" in PDF/UA table
    content_row = checkpoints.PDF_UA_CATEGORIES.index("Content")
    checkpoints.table_pdf_ua.setCurrentCell(content_row, 0)

    # Click "Results in detail"
    checkpoints.btn_detail.click()

    assert len(received) == 1
    assert received[0] == ("PDF/UA", "Content")
