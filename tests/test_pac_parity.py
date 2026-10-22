"""
PAC Parity and Regression Tests
Verifies that the audit results, status badges, tag count, and checkpoint metrics
match PAC (PDF Accessibility Checker / Matterhorn Protocol) for benchmark PDFs.
"""

import os
import pytest
from src.pdf_inspector.core.document_parser import DocumentParser
from src.pdf_inspector.engine.runner import AuditRunner
from src.pdf_inspector.core.models import CheckStatus
from src.pdf_inspector.reporting.pdf_report import PDFReportGenerator
from src.pdf_inspector.reporting.html_report import HTMLReportGenerator

BENCHMARK_PDF = r"C:\Users\HBS\Downloads\58-78 (2).pdf"


@pytest.mark.skipif(not os.path.exists(BENCHMARK_PDF), reason="Benchmark PDF not found in Downloads")
def test_pac_parity_benchmark_58_78():
    doc = DocumentParser(BENCHMARK_PDF).parse()
    assert doc is not None

    # 1. Tags count must match PAC (454 tags, excluding StructTreeRoot)
    all_nodes = doc.structure_tree.find_all_nodes() if doc.structure_tree else []
    tag_nodes = [n for n in all_nodes if n.tag != "StructTreeRoot"]
    assert len(tag_nodes) == 454

    # 2. Run Audit
    runner = AuditRunner()
    report = runner.run(doc)

    # 3. PDF/UA Checkpoints Parity
    pdfua_counts = report.get_category_counts("PDF/UA")
    
    # Fonts: 1 failed (Times-Roman)
    assert pdfua_counts["Fonts"]["failed"] == 1
    font_failures = [
        r for r in report.results 
        if r.standard == "PDF/UA" and r.category == "Fonts" and r.status == CheckStatus.FAIL
    ]
    assert any("Times-Roman" in f.message for f in font_failures)

    # Structure elements: Passed 63, Failed 1 (LI containing Span)
    assert pdfua_counts["Structure elements"]["passed"] == 63
    assert pdfua_counts["Structure elements"]["failed"] == 1
    struct_failures = [
        r for r in report.results 
        if r.standard == "PDF/UA" and r.category == "Structure elements" and r.status == CheckStatus.FAIL
    ]
    assert any("LI" in f.message and "Span" in f.message for f in struct_failures)

    # Document settings: Passed 3, Failed 0
    assert pdfua_counts["Document settings"]["passed"] == 3
    assert pdfua_counts["Document settings"]["failed"] == 0

    # 4. WCAG & Quality Tab Status Badges
    wcag_counts = report.get_category_counts("WCAG")
    wcag_failed = sum(c.get("failed", 0) for c in wcag_counts.values())
    assert wcag_failed > 0  # ❌ WCAG

    qual_counts = report.get_category_counts("Quality")
    qual_failed = sum(c.get("failed", 0) for c in qual_counts.values())
    qual_warned = sum(c.get("warned", 0) for c in qual_counts.values())
    assert qual_failed == 0
    assert qual_warned > 0  # ⚠️ Quality (Heading hierarchy starts at H3)

    # 5. Report Generators must handle angle brackets (<LI>, <Span>, etc.) safely
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_out = os.path.join(tmpdir, "audit_report.pdf")
        html_out = os.path.join(tmpdir, "audit_report.html")
        PDFReportGenerator.generate(report, pdf_out)
        assert os.path.getsize(pdf_out) > 0
        HTMLReportGenerator.generate(report, html_out)
        assert os.path.getsize(html_out) > 0


def test_pac_exact_case_role_mapping():
    from src.pdf_inspector.engine.pdf_ua.role_map_rules import RoleMappingValidityRule
    from src.pdf_inspector.core.models import StructureNode, PDFDocumentModel, CheckStatus

    rule = RoleMappingValidityRule()

    # /LBody (proper camelcase standard tag) should pass
    root_valid = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    node_valid = StructureNode("n1", "LBody", "LBody")
    root_valid.children.append(node_valid)
    doc_valid = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_valid, role_map={}
    )
    res_valid = rule.evaluate(doc_valid)
    assert any(r.status == CheckStatus.PASS for r in res_valid)
    assert not any(r.status == CheckStatus.FAIL for r in res_valid)

    # /Lbody (lowercase b) is non-standard in ISO 32000-1 and unmapped -> must FAIL like PAC
    root_invalid = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    node_invalid = StructureNode("n2", "Lbody", "Lbody")
    root_invalid.children.append(node_invalid)
    doc_invalid = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_invalid, role_map={}
    )
    res_invalid = rule.evaluate(doc_invalid)
    assert any(r.status == CheckStatus.FAIL and "Non-standard structure type \"Lbody\"" in r.message for r in res_invalid)


def test_pac_structure_tree_heading_warnings():
    from src.pdf_inspector.engine.pdf_ua.structure_rules import StructureTreeIntegrityRule
    from src.pdf_inspector.core.models import StructureNode, PDFDocumentModel, CheckStatus

    rule = StructureTreeIntegrityRule()
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    # First heading starts at H2 (should generate warning like PAC)
    h2 = StructureNode("h2", "H2", "H2")
    # Skipped heading to H4 (should generate warning)
    h4 = StructureNode("h4", "H4", "H4")
    root.children.extend([h2, h4])

    doc = PDFDocumentModel(
        filepath="", filename="headings.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    res = rule.evaluate(doc)
    warnings = [r for r in res if r.status == CheckStatus.WARNING]
    assert len(warnings) >= 2
    assert any("First heading in structure tree is <H2>" in w.message for w in warnings)
    assert any("Structure tree heading hierarchy skips from H2 to H4" in w.message for w in warnings)


def test_pac_tab_order_fail():
    from src.pdf_inspector.engine.pdf_ua.annotation_rules import PageTabOrderRule
    from src.pdf_inspector.core.models import StructureNode, PageModel, PDFDocumentModel, CheckStatus

    rule = PageTabOrderRule()
    pg = PageModel(page_number=1, width=612.0, height=792.0, has_tab_order=False, tab_order_mode="None", annotations_count=1)
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    doc = PDFDocumentModel(
        filepath="", filename="taborder.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root, pages=[pg], display_doc_title=True
    )
    res = rule.evaluate(doc)
    tab_fails = [r for r in res if r.status == CheckStatus.FAIL and "tab order" in r.message.lower()]
    assert len(tab_fails) == 1


WORK_DOC_PDF = r"C:\Users\HBS\Downloads\Work_Documentation_Administrative_Fillable_1_accessible.pdf"


@pytest.mark.skipif(not os.path.exists(WORK_DOC_PDF), reason="Work_Documentation PDF not found in Downloads")
def test_pac_parity_artifacts_inside_tagged_content():
    """Verifies that PAI detects exactly 41 artifacts inside tagged content on Work_Documentation PDF matching PAC."""
    from src.pdf_inspector.engine.pdf_ua.artifact_rules import ArtifactInsideTaggedContentRule
    
    doc = DocumentParser(WORK_DOC_PDF).parse()
    assert doc is not None

    rule = ArtifactInsideTaggedContentRule()
    results = rule.evaluate(doc)

    fails = [r for r in results if r.status == CheckStatus.FAIL]
    passes = [r for r in results if r.status == CheckStatus.PASS]

    # PAC reports exactly 41 errors
    assert len(fails) == 41
    # Checkpoint passed count
    assert sum(r.items_count for r in passes) == 356

    # Verify failure pages match PAC (13 pages)
    expected_pages = {27, 29, 31, 33, 57, 59, 61, 63, 64, 65, 67, 69, 71}
    actual_pages = {r.page for r in fails}
    assert actual_pages == expected_pages

    # Check page 27 finding details (visual highlight rect and McGraw text)
    p27_fails = [r for r in fails if r.page == 27]
    assert len(p27_fails) == 3
    sample = p27_fails[0]
    assert sample.bounding_box is not None
    # Rect around (92.3, 170.18, 106.36, 379.87)
    assert abs(sample.bounding_box[0] - 92.30) < 1.0
    assert abs(sample.bounding_box[1] - 170.18) < 1.0
    assert "Figure" in sample.object_reference
    assert "Fm2" in sample.object_reference
    assert "McGraw" in sample.evidence

    # Run full AuditRunner and verify Content checkpoint counts
    runner = AuditRunner()
    report = runner.run(doc)
    pdfua_counts = report.get_category_counts("PDF/UA")
    assert pdfua_counts["Content"]["failed"] == 41
    assert pdfua_counts["Content"]["passed"] >= 356


def test_artifact_inside_tagged_content_synthetic():
    """Unit test for ArtifactInsideTaggedContentRule with synthetic document models."""
    from src.pdf_inspector.engine.pdf_ua.artifact_rules import ArtifactInsideTaggedContentRule
    from src.pdf_inspector.core.models import ArtifactOccurrenceModel, PageModel, PDFDocumentModel
    
    rule = ArtifactInsideTaggedContentRule()

    # 1. Clean document: all artifacts outside tagged content
    pg1 = PageModel(page_number=1, width=612.0, height=792.0, artifacts=[
        ArtifactOccurrenceModel(page_number=1, is_inside_tagged=False),
        ArtifactOccurrenceModel(page_number=1, is_inside_tagged=False),
    ])
    doc_clean = PDFDocumentModel(
        filepath="", filename="clean.pdf", filesize=100, pdf_version="1.7",
        page_count=1, pages=[pg1]
    )
    res_clean = rule.evaluate(doc_clean)
    assert all(r.status == CheckStatus.PASS for r in res_clean)
    assert not any(r.status == CheckStatus.FAIL for r in res_clean)

    # 2. Document with invalid artifact inside tagged content
    pg2 = PageModel(page_number=1, width=612.0, height=792.0, artifacts=[
        ArtifactOccurrenceModel(
            page_number=1,
            is_inside_tagged=True,
            parent_tag="P",
            parent_mcid=3,
            bbox=(50.0, 100.0, 200.0, 150.0),
            text_snippet="Decorative separator"
        )
    ])
    doc_invalid = PDFDocumentModel(
        filepath="", filename="invalid.pdf", filesize=100, pdf_version="1.7",
        page_count=1, pages=[pg2]
    )
    res_invalid = rule.evaluate(doc_invalid)
    fails = [r for r in res_invalid if r.status == CheckStatus.FAIL]
    assert len(fails) == 1
    assert fails[0].page == 1
    assert fails[0].bounding_box == (50.0, 100.0, 200.0, 150.0)
    assert "<P MCID=3>" in fails[0].object_reference
    assert "Decorative separator" in fails[0].evidence


IDEA_REPORT_PDF = r"C:\Users\defaultuser0\Downloads\IDEA Data Analysis Workbook v12_A11y_full file_PAC_UA_Report.pdf"


@pytest.mark.skipif(not os.path.exists(IDEA_REPORT_PDF), reason="IDEA PAC UA Report PDF not found in Downloads")
def test_pac_parity_idea_ua_report():
    """Verify complete PAC parity on axes4 PAC-generated test report PDF."""
    doc = DocumentParser(IDEA_REPORT_PDF).parse()
    assert doc is not None

    # 1. Tags count matches PAC exactly (114 tags)
    all_nodes = doc.structure_tree.find_all_nodes() if doc.structure_tree else []
    tag_nodes = [n for n in all_nodes if n.tag != "StructTreeRoot"]
    assert len(tag_nodes) == 114

    # 2. Run Audit
    runner = AuditRunner()
    report = runner.run(doc)

    # 3. PDF/UA must have 0 failures (matching PAC green check)
    pdfua_counts = report.get_category_counts("PDF/UA")
    pdfua_failed = sum(c.get("failed", 0) for c in pdfua_counts.values())
    assert pdfua_failed == 0

    # 4. WCAG must have 0 failures (matching PAC green check)
    wcag_counts = report.get_category_counts("WCAG")
    wcag_failed = sum(c.get("failed", 0) for c in wcag_counts.values())
    assert wcag_failed == 0

    # 5. Table regularity check passes without warnings
    table_findings = [r for r in report.results if r.check_id == "QUAL-TABLE-001"]
    assert all(r.status == CheckStatus.PASS for r in table_findings)

    # 6. Quality matrix verification matching PAC 2026 UI exactly
    from src.pdf_inspector.ui.views.checkpoints_view import CheckpointsView
    quality_counts = {}
    for cat, rule_ids in CheckpointsView.QUALITY_RULE_MAPPINGS.items():
        cat_results = [r for r in report.results if r.check_id in rule_ids]
        p = sum(r.items_count for r in cat_results if r.status == CheckStatus.PASS)
        w = sum(r.items_count for r in cat_results if r.status == CheckStatus.WARNING)
        f = sum(r.items_count for r in cat_results if r.status in (CheckStatus.FAIL, CheckStatus.ERROR))
        quality_counts[cat] = {"passed": p, "warned": w, "failed": f}

    # PAC 2026 verified counts
    assert quality_counts["Validity of document title"]["passed"] == 1
    assert quality_counts["Artifacted content on page body"]["passed"] == 0  # renders as '-'
    assert quality_counts["Tagged text consists of only whitespace"]["passed"] == 0  # renders as '-'
    assert quality_counts["Tagged content exists outside of the page boundaries"]["passed"] == 0  # renders as '-'
    assert quality_counts["Presence of headings"]["passed"] == 1
    assert quality_counts["Presence of bookmarks (document outline) if there are headings"]["passed"] == 1
    assert quality_counts['"TOCI" elements contain "Link" elements']["passed"] == 0  # renders as '-'
    assert quality_counts['"TOCI" elements correctly linked to headings']["passed"] == 0  # renders as '-'
    assert quality_counts["Alternative text on text elements"]["passed"] == 0  # renders as '-'
    assert quality_counts["Validity of alternate text"]["passed"] == 3  # 3 Figures with valid alt text
    assert quality_counts['Completeness of "Link" elements']["passed"] == 0  # renders as '-'
    assert quality_counts['Formal correctness of "LI" elements']["passed"] == 10  # 10 LI tags matching PAC exactly
    assert quality_counts['Completeness of "Table" elements']["passed"] == 1  # 1 Table matching PAC exactly
    assert quality_counts['"Note" elements are referenced']["passed"] == 0  # renders as '-'
    assert quality_counts['"Note" elements contain "Lbl" elements']["passed"] == 0  # renders as '-'
    assert quality_counts['"P" elements contain "Note" elements']["passed"] == 0  # renders as '-'

    # All Quality checks have 0 failures and 0 warnings
    assert sum(c["failed"] for c in quality_counts.values()) == 0
    assert sum(c["warned"] for c in quality_counts.values()) == 0


FRENCH_1A_PDF = os.path.expanduser(r"~\Downloads\French 1A_7654-1-17.pdf")


@pytest.mark.skipif(not os.path.exists(FRENCH_1A_PDF), reason="French 1A PDF not found in Downloads")
def test_pac_parity_french_1a():
    """Differential regression test verifying full PDF/UA and WCAG parity on French 1A against PAC reference reports."""
    doc = DocumentParser(FRENCH_1A_PDF).parse()
    assert doc is not None
    assert doc.page_count == 17
    assert doc.is_tagged is False

    runner = AuditRunner()
    report = runner.run(doc)

    # 1. PDF/UA Parity (French 1A_7654-1-17_PAC_UA_Report.pdf)
    ua_counts = report.get_category_counts("PDF/UA")
    assert ua_counts["PDF Syntax (ISO 32000-1)"]["passed"] == 36
    assert ua_counts["PDF Syntax (ISO 32000-1)"]["failed"] == 0
    assert ua_counts.get("Fonts", {}).get("passed", 0) == 0
    assert ua_counts.get("Fonts", {}).get("failed", 0) == 0
    assert ua_counts["Content"]["passed"] == 0
    assert ua_counts["Content"]["failed"] == 288
    assert ua_counts["Natural language"]["failed"] == 1
    assert ua_counts.get("Structure elements", {}).get("failed", 0) == 0
    assert ua_counts.get("Structure tree", {}).get("failed", 0) == 0
    assert ua_counts.get("Role mapping", {}).get("failed", 0) == 0
    assert ua_counts.get("Alternative Descriptions", {}).get("failed", 0) == 0
    assert ua_counts["Metadata"]["failed"] == 3
    assert ua_counts["Document settings"]["passed"] == 1
    assert ua_counts["Document settings"]["failed"] == 2

    # 2. WCAG 2.2 Parity (French 1A_7654-1-17_PAC_WCAG_Report.pdf)
    wcag_counts = report.get_category_counts("WCAG")
    # 1.1 Text Alternatives: '-' (0)
    assert wcag_counts.get("1.1 Text Alternatives", {}).get("passed", 0) == 0
    assert wcag_counts.get("1.1 Text Alternatives", {}).get("failed", 0) == 0
    # 1.3 Adaptable: 1 Passed, 289 Failed
    assert wcag_counts["1.3 Adaptable"]["passed"] == 1
    assert wcag_counts["1.3 Adaptable"]["failed"] == 289
    # 1.4 Distinguishable: '-' (0)
    assert wcag_counts.get("1.4 Distinguishable", {}).get("passed", 0) == 0
    assert wcag_counts.get("1.4 Distinguishable", {}).get("failed", 0) == 0
    # 2.4 Navigable: 3 Failed
    assert wcag_counts["2.4 Navigable"]["passed"] == 0
    assert wcag_counts["2.4 Navigable"]["failed"] == 3
    # 3.1 Readable: 1 Failed
    assert wcag_counts["3.1 Readable"]["failed"] == 1
    # 4.1 Compatible: 36 Passed
    assert wcag_counts["4.1 Compatible"]["passed"] == 36
    assert wcag_counts["4.1 Compatible"]["failed"] == 0


def test_repeated_image_resources_unique_ids():
    """Verify that repeated image XObjects on the same page receive distinct occurrence IDs and distinct bboxes."""
    from unittest.mock import MagicMock
    from src.pdf_inspector.core.document_parser import DocumentParser

    parser = DocumentParser("dummy.pdf")
    # Mock pymupdf document with a page having the same image XObject (xref=42) placed twice
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 1
    mock_page = MagicMock()
    # get_images returns 2 occurrences of xref 42
    mock_page.get_images.return_value = [
        (42, 0, 100, 100, 8, "DeviceRGB", "", "Im1", 0),
        (42, 0, 100, 100, 8, "DeviceRGB", "", "Im1", 0),
    ]
    rect1 = MagicMock(x0=10.0, y0=20.0, x1=110.0, y1=120.0)
    rect2 = MagicMock(x0=200.0, y0=250.0, x1=300.0, y1=350.0)
    mock_page.get_image_rects.return_value = [rect1, rect2]
    mock_doc.__getitem__.return_value = mock_page

    images = parser._extract_images(mock_doc, None)
    assert len(images) == 2
    assert images[0].id == "img_p1_42"
    assert images[1].id == "img_p1_42_2"
    assert images[0].bbox == (10.0, 20.0, 110.0, 120.0)
    assert images[1].bbox == (200.0, 250.0, 300.0, 350.0)


PDF01_PDF = os.path.expanduser(r"~\Downloads\PDF01.pdf")
PDF02_PDF = os.path.expanduser(r"~\Downloads\PDF02.pdf")
PDF03_PDF = os.path.expanduser(r"~\Downloads\PDF03.pdf")
PDF04_PDF = os.path.expanduser(r"~\Downloads\PDF04.pdf")
PDF10_PDF = os.path.expanduser(r"~\Downloads\PDF10.pdf")


@pytest.mark.skipif(not os.path.exists(PDF03_PDF), reason="PDF03.pdf not found in Downloads")
def test_pac_parity_pdf03_syntax():
    """Verifies that PDF03 syntax evaluation validates 208 Form XObjects and ParentTree."""
    from src.pdf_inspector.engine.pdf_ua.syntax_rules import PDFSyntaxBasicRule

    doc = DocumentParser(PDF03_PDF).parse()
    assert doc is not None
    assert len(doc.form_xobjects) == 208
    assert doc.has_parent_tree is True
    assert doc.parent_tree_valid is True

    rule = PDFSyntaxBasicRule()
    results = rule.evaluate(doc)
    passed_items = sum(r.items_count for r in results if r.status == CheckStatus.PASS)
    # PAC reports 1,274 syntax checks for PDF03. Our evidence-based parser yields 1,272.
    assert passed_items == 1272
    # Check that Form XObjects were validated
    form_results = [r for r in results if "Form XObject" in r.message]
    assert len(form_results) == 1
    assert form_results[0].items_count == 208
    # Check that parent tree was validated
    pt_results = [r for r in results if "parent tree" in r.message.lower()]
    assert len(pt_results) == 1


@pytest.mark.skipif(not os.path.exists(PDF01_PDF), reason="PDF01.pdf not found in Downloads")
def test_pac_parity_pdf01_syntax():
    """Verifies that PDF01 achieves exact PAC parity for syntax checks (2,280)."""
    from src.pdf_inspector.engine.pdf_ua.syntax_rules import PDFSyntaxBasicRule

    doc = DocumentParser(PDF01_PDF).parse()
    assert doc is not None
    assert doc.page_count == 8
    rule = PDFSyntaxBasicRule()
    results = rule.evaluate(doc)
    passed_items = sum(r.items_count for r in results if r.status == CheckStatus.PASS)
    assert passed_items == 2280


@pytest.mark.skipif(not os.path.exists(PDF02_PDF), reason="PDF02.pdf not found in Downloads")
def test_pac_parity_pdf02_syntax():
    """Verifies that PDF02 achieves exact PAC parity for syntax checks (813)."""
    from src.pdf_inspector.engine.pdf_ua.syntax_rules import PDFSyntaxBasicRule

    doc = DocumentParser(PDF02_PDF).parse()
    assert doc is not None
    assert doc.page_count == 10
    rule = PDFSyntaxBasicRule()
    results = rule.evaluate(doc)
    passed_items = sum(r.items_count for r in results if r.status == CheckStatus.PASS)
    assert passed_items == 813


@pytest.mark.skipif(not os.path.exists(PDF04_PDF), reason="PDF04.pdf not found in Downloads")
def test_pac_parity_pdf04_syntax():
    """Verifies that PDF04 achieves exact PAC parity for syntax checks (309) with reachable Form XObjects."""
    from src.pdf_inspector.engine.pdf_ua.syntax_rules import PDFSyntaxBasicRule

    doc = DocumentParser(PDF04_PDF).parse()
    assert doc is not None
    assert doc.page_count == 5
    assert len(doc.form_xobjects) == 10  # 10 reachable Form XObjects (excluding 2 unreferenced orphans)
    rule = PDFSyntaxBasicRule()
    results = rule.evaluate(doc)
    passed_items = sum(r.items_count for r in results if r.status == CheckStatus.PASS)
    assert passed_items == 309


@pytest.mark.skipif(not os.path.exists(PDF10_PDF), reason="PDF10.pdf not found in Downloads")
def test_pac_parity_pdf10_marked_content():
    """
    Verifies that PDF10 evaluates verified marked-content sequences and figure bounding boxes.
    - Page content streams contain exactly 661 marked-content sequences (BDC ... EMC with /MCID).
    - ParentTree contains 668 non-null entries across pages (661 referenced + 7 unreferenced slots).
    - Unreferenced ParentTree entries are not injected into PageModel.mcids.
    - Exactly 3 Figure elements lack bounding box geometry (node_257, node_329, node_657).
    """
    from src.pdf_inspector.engine.wcag.wcag_rules import WCAGAdaptableRule

    doc = DocumentParser(PDF10_PDF).parse()
    assert doc is not None

    # 1. Genuine content-stream MCIDs across all 12 pages
    total_stream_mcids = sum(len(p.mcids) for p in doc.pages)
    assert total_stream_mcids == 661

    # 2. Structural ParentTree non-null entries across pages (661 stream + 7 unreferenced slots)
    total_pt_entries = sum(
        len([x for x in doc.parent_tree_map.get(p.struct_parents_id, []) if x is not None])
        for p in doc.pages if p.struct_parents_id is not None
    )
    assert total_pt_entries == 668

    # 3. WCAG SC 1.3.1 Adaptable evaluation
    rule = WCAGAdaptableRule()
    results = rule.evaluate(doc)
    passed_items = sum(r.items_count for r in results if r.status == CheckStatus.PASS)
    assert passed_items >= 661

    # 4. Verifies detection of the 3 Figure elements lacking bounding boxes
    fig_fails = [r for r in results if "Figure" in r.message and r.status == CheckStatus.FAIL]
    assert len(fig_fails) == 3


def test_form_xobject_syntax_validation_rule():
    """Unit test for Form XObject dictionary syntax checking."""
    from src.pdf_inspector.core.models import FormXObjectModel, PDFDocumentModel
    from src.pdf_inspector.engine.pdf_ua.syntax_rules import PDFSyntaxBasicRule

    valid_form = FormXObjectModel(id="f1", obj_num=10, has_valid_bbox=True, bbox=(0, 0, 100, 100), is_valid=True)
    invalid_form = FormXObjectModel(id="f2", obj_num=11, has_valid_bbox=False, is_valid=False, error_message="Missing /BBox")

    doc = PDFDocumentModel(
        filepath="", filename="form_test.pdf", filesize=100, pdf_version="1.7",
        page_count=1, form_xobjects=[valid_form, invalid_form]
    )

    rule = PDFSyntaxBasicRule()
    results = rule.evaluate(doc)
    form_fails = [r for r in results if "Form XObject" in r.message and r.status == CheckStatus.FAIL]
    form_passes = [r for r in results if "Form XObject" in r.message and r.status == CheckStatus.PASS]

    assert len(form_fails) == 1
    assert form_fails[0].items_count == 1
    assert len(form_passes) == 1
    assert form_passes[0].items_count == 1


def test_wcag_marked_content_unmarked_detection():
    """Unit test for WCAG 1.3 marked content evaluation with unmarked content operations."""
    from src.pdf_inspector.core.models import PageModel, PDFDocumentModel
    from src.pdf_inspector.engine.wcag.wcag_rules import WCAGAdaptableRule

    p1 = PageModel(page_number=1, width=612, height=792, mcids=[1, 2, 3], tagged_operations_count=5, unmarked_real_content_count=0)
    p2 = PageModel(page_number=2, width=612, height=792, mcids=[], tagged_operations_count=0, unmarked_real_content_count=3)

    doc = PDFDocumentModel(
        filepath="", filename="mc_test.pdf", filesize=100, pdf_version="1.7",
        page_count=2, is_tagged=True, pages=[p1, p2]
    )

    rule = WCAGAdaptableRule()
    results = rule.evaluate(doc)

    mc_fails = [r for r in results if "unmarked real content" in r.message.lower() and r.status == CheckStatus.FAIL]
    assert len(mc_fails) == 1
    assert mc_fails[0].page == 2
    assert mc_fails[0].items_count == 3

    mc_passes = [r for r in results if "marked-content sequence" in r.message.lower() and r.status == CheckStatus.PASS]
    assert len(mc_passes) == 1
    assert mc_passes[0].page == 1
    assert mc_passes[0].items_count == 3


@pytest.mark.skipif(not os.path.exists(PDF03_PDF), reason="PDF03.pdf not found in Downloads")
def test_pac_parity_pdf03_fonts():
    """Verifies that PDF03 achieves exact PAC parity for Fonts (4 passed, 4 failed)."""
    from src.pdf_inspector.engine.runner import AuditRunner

    doc = DocumentParser(PDF03_PDF).parse()
    assert doc is not None

    report = AuditRunner().run(doc)
    counts = report.get_category_counts("PDF/UA")
    font_counts = counts.get("Fonts", {})

    assert font_counts.get("passed") == 4
    assert font_counts.get("failed") == 4


def test_synthetic_form_xobjects_traversal(tmp_path):
    """Synthetic test verifying reachable, nested, repeated-reference, and unreferenced Form XObjects."""
    import pikepdf
    from src.pdf_inspector.core.document_parser import DocumentParser

    pdf_path = str(tmp_path / "synthetic_forms.pdf")
    pdf = pikepdf.new()
    p1 = pdf.add_blank_page()
    p2 = pdf.add_blank_page()

    # 1. Reachable root Form XObject (f1)
    f1 = pdf.make_stream(b"q /F2 Do Q")
    f1.Type = pikepdf.Name.XObject
    f1.Subtype = pikepdf.Name.Form
    f1.BBox = [0, 0, 200, 200]
    f1.Matrix = [1, 0, 0, 1, 0, 0]

    # 2. Reachable nested Form XObject (f2 inside f1)
    f2 = pdf.make_stream(b"q Q")
    f2.Type = pikepdf.Name.XObject
    f2.Subtype = pikepdf.Name.Form
    f2.BBox = [0, 0, 100, 100]

    f1.Resources = pikepdf.Dictionary()
    f1.Resources.XObject = pikepdf.Dictionary()
    f1.Resources.XObject.F2 = f2

    # 3. Image XObject (must NOT be counted as Form XObject)
    img = pdf.make_stream(b"\x00\x00\x00")
    img.Type = pikepdf.Name.XObject
    img.Subtype = pikepdf.Name.Image
    img.Width = 1
    img.Height = 1
    img.ColorSpace = pikepdf.Name.DeviceRGB
    img.BitsPerComponent = 8

    # Assign f1 and image to page 1 resources
    p1.Resources = pikepdf.Dictionary()
    p1.Resources.XObject = pikepdf.Dictionary()
    p1.Resources.XObject.Form1 = f1
    p1.Resources.XObject.Image1 = img

    # 4. Repeated reference to f1 on page 2 (must NOT be double counted)
    p2.Resources = pikepdf.Dictionary()
    p2.Resources.XObject = pikepdf.Dictionary()
    p2.Resources.XObject.Form1Repeat = f1

    # 5. Unreferenced orphan Form XObject (not reachable via page resources)
    f_orphan = pdf.make_stream(b"q Q")
    f_orphan.Type = pikepdf.Name.XObject
    f_orphan.Subtype = pikepdf.Name.Form
    f_orphan.BBox = [0, 0, 50, 50]
    pdf.Root.OrphanForm = f_orphan

    pdf.save(pdf_path)

    doc = DocumentParser(pdf_path).parse()
    assert doc is not None

    # Expected: exactly 2 reachable Form XObjects (f1 and nested f2).
    # f1 repeated on p2 is deduplicated; f_orphan is unreferenced; img is Image subtype.
    assert len(doc.form_xobjects) == 2

    bboxes = {fo.bbox for fo in doc.form_xobjects}
    assert (0.0, 0.0, 200.0, 200.0) in bboxes
    assert (0.0, 0.0, 100.0, 100.0) in bboxes

    # Verify all extracted Form XObjects are valid
    assert all(fo.is_valid for fo in doc.form_xobjects)


BINDER1_PDF = r"C:\Users\HBS\Downloads\Binder1_tagged_fixed_PAC (2).pdf"


@pytest.mark.skipif(not os.path.exists(BINDER1_PDF), reason="Binder1 PDF not found in Downloads")
def test_pac_parity_binder1_artifacted_content_on_page_body():
    """Verifies that 'Artifacted content on page body' produces exactly 68 warnings on Binder1 matching PAC."""
    doc = DocumentParser(BINDER1_PDF).parse()
    assert doc is not None

    runner = AuditRunner()
    report = runner.run(doc)

    quality_counts = report.get_category_counts("Quality")
    art_body = quality_counts.get("Artifacted content on page body", {})
    assert art_body.get("warned") == 68
    assert art_body.get("failed") == 0

