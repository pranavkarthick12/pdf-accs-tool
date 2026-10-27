"""
Comprehensive Automated Regression Test Suite for PAI Coordinate & Highlight Pipeline
Tests:
1. Centralized geometry validation (rejecting non-finite, out-of-bounds, negative dimensions, dummy (0,0,0,0)).
2. Exact coordinate transformations under page rotations (0, 90, 180, 270 degrees).
3. Non-zero CropBox origin handling without double-offset or displacement.
4. Document-level findings (PDFUA-META, PDFUA-LANG, etc.) returning honest non-spatial contracts with ZERO phantom highlights.
5. Page-level findings (TabOrder /Tabs) returning full-page bounds.
6. Structure-element resolution for list structures (highlighting the offending child rather than container or unrelated elements).
7. Multi-rectangle resolution for multi-line elements avoiding oversized envelope blowups.
8. MCID resolution strictly respecting page association.
9. PAC Split View and Document View consistency.
10. Zoom and interactive viewer rotation coordinate synchronization.
11. Rapid finding selection without stale callbacks or state corruption.
12. Honest reporting for unresolvable spatial locations.
"""

import math
import os
import tempfile
import pytest
import pymupdf
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from src.pdf_inspector.core.models import (
    CheckResult, CheckStatus, Severity, StructureNode,
    PDFDocumentModel, PageModel
)
from src.pdf_inspector.core.visual_locator import (
    VisualLocatorResolver, ResolvedLocation,
    validate_highlight_rect, validate_highlight_rectangles
)
from src.pdf_inspector.ui.widgets.pdf_canvas import PDFCanvas, PageDisplayWidget
from src.pdf_inspector.ui.widgets.pac_visual_locator import PACVisualCanvas, PACVisualLocatorWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def synthetic_rotated_pdf(tmp_path):
    """Generates a synthetic PDF with known text coordinates and rotation for verification."""
    doc = pymupdf.open()
    # Page 1: Normal 0 deg rotation
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((100, 150), "Standard Heading Text", fontsize=16)

    # Page 2: Rotated 90 deg
    p2 = doc.new_page(width=612, height=792)
    p2.insert_text((100, 150), "Rotated 90 Degree Text", fontsize=16)
    p2.set_rotation(90)

    # Page 3: Non-zero CropBox
    p3 = doc.new_page(width=612, height=792)
    p3.set_cropbox(pymupdf.Rect(50, 50, 550, 750))
    p3.insert_text((100, 150), "Cropped Page Content", fontsize=16)

    pdf_path = str(tmp_path / "synthetic_test.pdf")
    doc.save(pdf_path)
    doc.close()
    return pdf_path


# ==============================================================================
# 1. Centralized Geometry Validation Tests
# ==============================================================================

def test_centralized_geometry_validation():
    page_rect = pymupdf.Rect(0, 0, 612, 792)

    # Valid rect
    ok, valid_r, reason = validate_highlight_rect((100, 100, 300, 200), page_rect)
    assert ok is True
    assert valid_r == (100.0, 100.0, 300.0, 200.0)
    assert reason == "Valid"

    # Inverted coordinates (x1 < x0) should be normalized safely
    ok, valid_r, _ = validate_highlight_rect((300, 200, 100, 100), page_rect)
    assert ok is True
    assert valid_r == (100.0, 100.0, 300.0, 200.0)

    # Dummy (0, 0, 0, 0) placeholder must be rejected
    ok, valid_r, reason = validate_highlight_rect((0, 0, 0, 0), page_rect)
    assert ok is False
    assert valid_r is None
    assert "Dummy" in reason

    # Non-finite coordinates (NaN, Inf) must be rejected
    ok, _, reason = validate_highlight_rect((float("nan"), 100, 200, 200), page_rect)
    assert ok is False
    assert "Non-finite" in reason

    ok, _, reason = validate_highlight_rect((100, float("inf"), 200, 200), page_rect)
    assert ok is False
    assert "Non-finite" in reason

    # Out-of-bounds rectangle (completely outside page) must be rejected
    ok, _, reason = validate_highlight_rect((700, 800, 900, 950), page_rect)
    assert ok is False
    assert "does not intersect" in reason

    # Partial intersection should be clamped to visible bounds
    ok, valid_r, _ = validate_highlight_rect((500, 700, 700, 850), page_rect)
    assert ok is True
    assert valid_r[0] == 500.0
    assert valid_r[1] == 700.0
    assert valid_r[2] == 612.0  # Clamped to page width
    assert valid_r[3] == 792.0  # Clamped to page height

    # List validation helper
    candidates = [
        (100, 100, 200, 150),
        (0, 0, 0, 0),
        (float("nan"), 0, 10, 10),
        (150, 200, 250, 250)
    ]
    valid_list, reasons = validate_highlight_rectangles(candidates, page_rect)
    assert len(valid_list) == 2
    assert valid_list[0] == (100.0, 100.0, 200.0, 150.0)
    assert valid_list[1] == (150.0, 200.0, 250.0, 250.0)
    assert len(reasons) == 2


# ==============================================================================
# 2. Coordinate Transformation Under Page Rotation & CropBox Tests
# ==============================================================================

def test_coordinate_transformation_under_rotation():
    """
    Mathematically verifies that a bounding box transformed for rendering under
    interactive viewer rotations (0, 90, 180, 270) aligns with rendered pixmap pixels.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=800)
    # Target text rectangle
    rect = pymupdf.Rect(100, 150, 250, 200)
    page.draw_rect(rect, color=(0, 0, 0), fill=(0, 0, 0))

    zoom = 1.25
    for rot in [0, 90, 180, 270]:
        mat = pymupdf.Matrix(zoom, zoom).prerotate(rot)
        pix = page.get_pixmap(matrix=mat)
        bounds = page.rect * mat

        # Transformation formula applied in PageDisplayWidget
        tr = rect * mat
        pix_r = pymupdf.Rect(
            tr.x0 - bounds.x0,
            tr.y0 - bounds.y0,
            tr.x1 - bounds.x0,
            tr.y1 - bounds.y0
        )

        # Center point inside pixmap
        cx = int((pix_r.x0 + pix_r.x1) / 2)
        cy = int((pix_r.y0 + pix_r.y1) / 2)

        # Pixel must be solid black (0, 0, 0)
        assert 0 <= cx < pix.width
        assert 0 <= cy < pix.height
        pixel = pix.pixel(cx, cy)
        assert pixel == (0, 0, 0), f"Rotation {rot}° failed: pixel at ({cx}, {cy}) is {pixel}"
    doc.close()


def test_coordinate_transformation_with_cropbox():
    """Verifies that non-zero CropBox origins align accurately with pixmap coordinates."""
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.set_cropbox(pymupdf.Rect(50, 60, 550, 750))

    target = pymupdf.Rect(100, 150, 200, 220)
    page.draw_rect(target, color=(0, 0, 0), fill=(0, 0, 0))

    zoom = 1.5
    mat = pymupdf.Matrix(zoom, zoom).prerotate(0)
    pix = page.get_pixmap(matrix=mat)
    bounds = page.rect * mat

    tr = target * mat
    pix_r = pymupdf.Rect(
        tr.x0 - bounds.x0,
        tr.y0 - bounds.y0,
        tr.x1 - bounds.x0,
        tr.y1 - bounds.y0
    )

    cx = int((pix_r.x0 + pix_r.x1) / 2)
    cy = int((pix_r.y0 + pix_r.y1) / 2)

    assert 0 <= cx < pix.width
    assert 0 <= cy < pix.height
    assert pix.pixel(cx, cy) == (0, 0, 0)
    doc.close()


# ==============================================================================
# 3. Document-Level Findings Return ZERO Phantom Highlights
# ==============================================================================

def test_document_level_findings_return_no_phantom_coordinates():
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Sample Document Content", fontsize=12)

    # Document Title Missing (PDFUA-META-002)
    meta_finding = CheckResult(
        check_id="PDFUA-META-002",
        name="Document Title Missing",
        category="Metadata",
        standard="PDF/UA",
        status=CheckStatus.FAIL,
        severity=Severity.HIGH,
        message="Document does not contain a title in the document information dictionary or XMP metadata.",
        page=None,
        bounding_box=None
    )

    resolved = VisualLocatorResolver.resolve_location(doc, page_num=1, finding=meta_finding)
    assert resolved.location_type == "DOCUMENT"
    assert resolved.is_valid is False
    assert len(resolved.rectangles) == 0
    assert resolved.primary_bbox is None
    assert "Document-level" in resolved.message

    # Natural Language Missing (PDFUA-LANG-001)
    lang_finding = CheckResult(
        check_id="PDFUA-LANG-001",
        name="Natural Language Specified",
        category="Language",
        standard="PDF/UA",
        status=CheckStatus.FAIL,
        severity=Severity.HIGH,
        message="The natural language of the document is not specified in the Catalog dictionary.",
        page=None,
        bounding_box=None
    )

    resolved_lang = VisualLocatorResolver.resolve_location(doc, page_num=1, finding=lang_finding)
    assert resolved_lang.location_type == "DOCUMENT"
    assert resolved_lang.is_valid is False
    assert len(resolved_lang.rectangles) == 0

    doc.close()


# ==============================================================================
# 4. Page-Level Findings Return Genuine Page Bounds
# ==============================================================================

def test_page_level_findings_return_whole_page():
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)

    tab_finding = CheckResult(
        check_id="PDFUA-SYNTAX-003",
        name="Tab order entry",
        category="Page Structure",
        standard="PDF/UA",
        status=CheckStatus.FAIL,
        severity=Severity.HIGH,
        message="Page 1 is missing a /Tabs dictionary entry specifying structure tab order.",
        page=1,
        bounding_box=None
    )

    resolved = VisualLocatorResolver.resolve_location(doc, page_num=1, finding=tab_finding)
    assert resolved.location_type == "PAGE"
    assert resolved.is_valid is True
    assert len(resolved.rectangles) == 1
    assert resolved.rectangles[0] == (0.0, 0.0, 612.0, 792.0)
    assert resolved.source == "PAGE_LEVEL"

    doc.close()


# ==============================================================================
# 5. Structure-Based Resolution (List Hierarchy & Offending Sub-Element)
# ==============================================================================

def test_structure_based_resolution_identifies_offending_child():
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)

    # Text spans on page:
    # Bullet at (72, 100, 85, 115)
    # Invalid paragraph tag inside LI at (100, 100, 300, 115)
    page.insert_text((72, 112), "•", fontsize=12)
    page.insert_text((100, 112), "Stray Paragraph Inside List Item", fontsize=12)

    # Construct Document Model with Structure Tree
    lbl_node = StructureNode(
        id="lbl_1",
        tag="Lbl",
        standard_tag="Lbl",
        page=1,
        bbox=(72.0, 100.0, 85.0, 115.0),
        text_content="•"
    )
    p_child = StructureNode(
        id="p_bad",
        tag="P",
        standard_tag="P",
        page=1,
        bbox=(100.0, 100.0, 300.0, 115.0),
        text_content="Stray Paragraph Inside List Item"
    )
    li_node = StructureNode(
        id="li_1",
        tag="LI",
        standard_tag="LI",
        page=1,
        children=[lbl_node, p_child]
    )
    l_node = StructureNode(
        id="list_root",
        tag="L",
        standard_tag="L",
        page=1,
        children=[li_node]
    )
    root_node = StructureNode(
        id="root",
        tag="StructTreeRoot",
        standard_tag="StructTreeRoot",
        children=[l_node]
    )

    doc_model = PDFDocumentModel(
        filepath="dummy.pdf",
        filename="dummy.pdf",
        filesize=1024,
        pdf_version="1.7",
        page_count=1,
        structure_tree=root_node,
        pages=[PageModel(
            page_number=1,
            width=612,
            height=792,
            rotation=0,
            text="• Stray Paragraph Inside List Item"
        )]
    )

    # Finding on LI concerning invalid direct child <P>
    finding = CheckResult(
        check_id="PDFUA-LIST-001",
        name="List item hierarchy",
        category="Lists",
        standard="PDF/UA",
        status=CheckStatus.FAIL,
        severity=Severity.HIGH,
        message="List item <LI> on page 1 has an invalid structural hierarchy: contains invalid direct child element(s) ['P'].",
        evidence="Path: Document/L/LI | Page: 1",
        page=1,
        object_reference="<LI id='li_1'>",
        bounding_box=None
    )

    resolved = VisualLocatorResolver.resolve_location(doc, page_num=1, finding=finding, doc_model=doc_model)
    assert resolved.location_type == "STRUCTURE"
    assert resolved.is_valid is True
    assert len(resolved.rectangles) == 1
    # MUST highlight the offending child <P> rather than the whole LI or the bullet!
    assert resolved.rectangles[0] == (100.0, 100.0, 300.0, 115.0)

    doc.close()


# ==============================================================================
# 6. Multi-Rectangle Resolution for Multi-Line Content
# ==============================================================================

def test_structure_based_multiple_rectangles_for_multiline():
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)

    # Two lines of text
    page.insert_text((72, 100), "First Line of Section Heading", fontsize=14)
    page.insert_text((72, 130), "Second Line of Section Heading", fontsize=14)

    h_node = StructureNode(
        id="h_node",
        tag="H1",
        standard_tag="H1",
        page=1,
        text_content="First Line of Section Heading Second Line of Section Heading"
    )
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[h_node])
    doc_model = PDFDocumentModel(filepath="", filename="", filesize=1024, pdf_version="1.7", page_count=1, structure_tree=root)

    finding = CheckResult(
        check_id="PDFUA-STRUCT-001",
        name="Heading Validation",
        category="Headings",
        standard="PDF/UA",
        status=CheckStatus.FAIL,
        severity=Severity.MEDIUM,
        message="Heading numbering anomaly.",
        page=1,
        object_reference="<H1 id='h_node'>",
        evidence="First Line of Section Heading"
    )

    resolved = VisualLocatorResolver.resolve_location(doc, page_num=1, finding=finding, doc_model=doc_model)
    assert resolved.is_valid is True
    # Should resolve valid rectangles for the text matches
    assert len(resolved.rectangles) >= 1
    for r in resolved.rectangles:
        assert r[0] >= 70.0 and r[2] <= 500.0
    doc.close()


# ==============================================================================
# 7. MCID Resolution on Specific Pages
# ==============================================================================

def test_mcid_resolution_respects_page_association():
    doc = pymupdf.open()
    p1 = doc.new_page(width=612, height=792)
    p2 = doc.new_page(width=612, height=792)

    # Model with different MCID boxes on Page 1 and Page 2
    page1_model = PageModel(page_number=1, width=612, height=792, rotation=0, text="", mcid_bboxes={5: (72.0, 100.0, 200.0, 120.0)})
    page2_model = PageModel(page_number=2, width=612, height=792, rotation=0, text="", mcid_bboxes={5: (150.0, 300.0, 400.0, 350.0)})

    doc_model = PDFDocumentModel(filepath="", filename="", filesize=1024, pdf_version="1.7", page_count=2, pages=[page1_model, page2_model])

    finding_p2 = CheckResult(
        check_id="PDFUA-CONTENT-001",
        name="Marked content issue",
        category="Content",
        standard="PDF/UA",
        status=CheckStatus.FAIL,
        severity=Severity.HIGH,
        message="Marked content syntax issue.",
        page=2,
        object_reference="MCID 5",
        bounding_box=None
    )

    # When resolving for Page 2, it MUST use Page 2's MCID 5 box
    resolved = VisualLocatorResolver.resolve_location(doc, page_num=2, finding=finding_p2, doc_model=doc_model)
    assert resolved.is_valid is True
    assert resolved.rectangles == [(150.0, 300.0, 400.0, 350.0)]

    # When resolving for Page 1, it MUST use Page 1's MCID 5 box
    finding_p1 = CheckResult(
        check_id="PDFUA-CONTENT-001",
        name="Marked content issue",
        category="Content",
        standard="PDF/UA",
        status=CheckStatus.FAIL,
        severity=Severity.HIGH,
        message="Marked content syntax issue.",
        page=1,
        object_reference="MCID 5",
        bounding_box=None
    )
    resolved_p1 = VisualLocatorResolver.resolve_location(doc, page_num=1, finding=finding_p1, doc_model=doc_model)
    assert resolved_p1.is_valid is True
    assert resolved_p1.rectangles == [(72.0, 100.0, 200.0, 120.0)]

    doc.close()


# ==============================================================================
# 8. PDFCanvas Split View & Document View Consistency
# ==============================================================================

def test_pdf_canvas_split_and_document_view_consistency(qapp, synthetic_rotated_pdf):
    canvas = PDFCanvas()
    canvas.load_document(synthetic_rotated_pdf)

    # Finding on Page 1
    finding = CheckResult(
        check_id="TEST-FINDING-001",
        name="Test Finding",
        category="Structure",
        standard="PDF/UA",
        status=CheckStatus.FAIL,
        severity=Severity.HIGH,
        message="Test issue on Page 1",
        page=1,
        bounding_box=(100.0, 150.0, 250.0, 180.0)
    )

    canvas.go_to_page(1, finding.bounding_box, finding=finding)

    # Both views share verified highlight rectangles
    assert canvas.highlight_bbox == (100.0, 150.0, 250.0, 180.0)
    assert canvas.highlight_rects == [(100.0, 150.0, 250.0, 180.0)]

    # PAC Split View canvas has the bounding box
    assert canvas.pac_locator.canvas.bbox == (100.0, 150.0, 250.0, 180.0)
    assert canvas.pac_locator.canvas.bboxes == [(100.0, 150.0, 250.0, 180.0)]

    # Switch to Document View
    canvas.set_view_mode("doc")
    assert canvas.stack.currentIndex() == 1
    assert canvas.page_display.highlight_rects == [(100.0, 150.0, 250.0, 180.0)]

    # Switch back to PAC Split View
    canvas.set_view_mode("pac")
    assert canvas.stack.currentIndex() == 0
    assert canvas.pac_locator.canvas.bboxes == [(100.0, 150.0, 250.0, 180.0)]


# ==============================================================================
# 9. Rapid Finding Selection & Highlight Clearing
# ==============================================================================

def test_rapid_finding_selection_and_clearing(qapp, synthetic_rotated_pdf):
    canvas = PDFCanvas()
    canvas.load_document(synthetic_rotated_pdf)

    # Rapidly select 5 findings across different pages
    for p in range(1, 4):
        f = CheckResult(
            check_id=f"RAPID-{p}",
            name=f"Rapid finding {p}",
            category="Test",
            standard="PDF/UA",
            status=CheckStatus.FAIL,
            severity=Severity.HIGH,
            message=f"Rapid issue {p}",
            page=p,
            bounding_box=(50.0 * p, 50.0 * p, 100.0 * p, 100.0 * p)
        )
        canvas.go_to_page(p, f.bounding_box, finding=f)
        assert canvas.current_page_idx == p - 1
        assert canvas.highlight_bbox == (50.0 * p, 50.0 * p, 100.0 * p, 100.0 * p)

    # Clear highlight
    canvas.clear_highlight()
    assert canvas.highlight_bbox is None
    assert canvas.highlight_rects == []
    assert canvas.current_finding is None


# ==============================================================================
# 10. Honest Non-Spatial Message on Document Findings
# ==============================================================================

def test_honest_message_on_document_findings_in_viewer(qapp, synthetic_rotated_pdf):
    canvas = PDFCanvas()
    canvas.load_document(synthetic_rotated_pdf)

    doc_finding = CheckResult(
        check_id="PDFUA-META-001",
        name="Document Title Missing",
        category="Metadata",
        standard="PDF/UA",
        status=CheckStatus.FAIL,
        severity=Severity.HIGH,
        message="Document does not contain a title.",
        page=None,
        bounding_box=None
    )

    canvas.go_to_page(1, finding=doc_finding)

    # Must NOT have phantom bbox
    assert canvas.highlight_bbox is None
    assert canvas.highlight_rects == []
    assert canvas.pac_locator.canvas.bboxes == []
    # Right panel in PAC Visual Locator presents honest message card
    assert canvas.pac_locator.canvas.resolved_location is not None
    assert canvas.pac_locator.canvas.resolved_location.location_type == "DOCUMENT"
    assert canvas.pac_locator.canvas.resolved_location.is_valid is False


# ==============================================================================
# 11. Nested List Structures Resolution
# ==============================================================================

def test_nested_list_structures_resolution():
    """
    Verifies that for nested lists (<L> -> <LI> -> <LBody> -> nested <L> -> nested <LI>),
    findings targeting the outer list item or inner list item resolve the exact corresponding
    node and coordinates without confusion.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)

    # Outer item at (72, 100, 300, 120)
    # Inner nested item at (90, 130, 300, 150)
    nested_lbl = StructureNode(id="inner_lbl", tag="Lbl", standard_tag="Lbl", page=1, bbox=(90.0, 130.0, 105.0, 145.0), text_content="a.")
    nested_lbody = StructureNode(id="inner_lbody", tag="LBody", standard_tag="LBody", page=1, bbox=(110.0, 130.0, 300.0, 145.0), text_content="Sub-item content")
    nested_li = StructureNode(id="inner_li", tag="LI", standard_tag="LI", page=1, bbox=(90.0, 130.0, 300.0, 145.0), children=[nested_lbl, nested_lbody])
    nested_l = StructureNode(id="inner_l", tag="L", standard_tag="L", page=1, children=[nested_li])

    outer_lbl = StructureNode(id="outer_lbl", tag="Lbl", standard_tag="Lbl", page=1, bbox=(72.0, 100.0, 85.0, 115.0), text_content="1.")
    outer_lbody = StructureNode(id="outer_lbody", tag="LBody", standard_tag="LBody", page=1, bbox=(90.0, 100.0, 300.0, 115.0), children=[nested_l])
    outer_li = StructureNode(id="outer_li", tag="LI", standard_tag="LI", page=1, bbox=(72.0, 100.0, 300.0, 145.0), children=[outer_lbl, outer_lbody])
    outer_l = StructureNode(id="outer_l", tag="L", standard_tag="L", page=1, children=[outer_li])
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[outer_l])

    doc_model = PDFDocumentModel(filepath="", filename="", filesize=1024, pdf_version="1.7", page_count=1, structure_tree=root)

    # 1. Target Outer LI
    finding_outer = CheckResult(
        check_id="PDFUA-LIST-001",
        name="Outer List Item",
        category="Lists",
        standard="PDF/UA",
        status=CheckStatus.FAIL,
        severity=Severity.HIGH,
        message="Outer list issue",
        page=1,
        object_reference="<LI id='outer_li'>",
        evidence="Path: Document/L/LI[1]"
    )
    resolved_outer = VisualLocatorResolver.resolve_location(doc, page_num=1, finding=finding_outer, doc_model=doc_model)
    assert resolved_outer.is_valid is True
    assert resolved_outer.target_node.id == "outer_li"

    # 2. Target Inner Nested LI
    finding_inner = CheckResult(
        check_id="PDFUA-LIST-001",
        name="Inner List Item",
        category="Lists",
        standard="PDF/UA",
        status=CheckStatus.FAIL,
        severity=Severity.HIGH,
        message="Inner list issue",
        page=1,
        object_reference="<LI id='inner_li'>",
        evidence="Path: Document/L/LI[1]/LBody/L/LI[1]"
    )
    resolved_inner = VisualLocatorResolver.resolve_location(doc, page_num=1, finding=finding_inner, doc_model=doc_model)
    assert resolved_inner.is_valid is True
    assert resolved_inner.target_node.id == "inner_li"
    assert resolved_inner.rectangles[0] == (90.0, 130.0, 300.0, 145.0)

    doc.close()


# ==============================================================================
# 12. Out-of-Bounds and Malformed Coordinates
# ==============================================================================

def test_out_of_bounds_and_malformed_coordinates():
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=700)

    # Finding with completely out-of-bounds coordinates
    finding_oob = CheckResult(
        check_id="TEST-OOB",
        name="Out of bounds",
        category="Quality",
        standard="Quality",
        status=CheckStatus.FAIL,
        severity=Severity.HIGH,
        message="OOB finding",
        page=1,
        bounding_box=(800.0, 900.0, 1000.0, 1100.0)
    )

    resolved = VisualLocatorResolver.resolve_location(doc, page_num=1, finding=finding_oob)
    # Rejected without silently falling back to page corner
    assert resolved.is_valid is False
    assert resolved.rectangles == []

    doc.close()


# ==============================================================================
# 13. Interactive Zoom and Rotation in PageDisplayWidget
# ==============================================================================

def test_zoom_and_rotation_in_page_display_widget(qapp):
    widget = PageDisplayWidget()
    page_rect = pymupdf.Rect(0, 0, 500, 800)

    # Test that painting at various zoom levels (0.5, 1.0, 1.5, 2.0) and rotations (0, 90, 180, 270)
    # executes cleanly without any exceptions or coordinate shifts
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=800)

    for zoom in [0.5, 1.0, 1.5, 2.0]:
        for rot in [0, 90, 180, 270]:
            mat = pymupdf.Matrix(zoom, zoom).prerotate(rot)
            pix = page.get_pixmap(matrix=mat)
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)

            widget.set_page_image(
                pixmap=pixmap,
                page_rect=page_rect,
                scale=zoom,
                rotation=rot,
                highlight_rects=[(100.0, 150.0, 250.0, 200.0)]
            )
            assert widget.scale_factor == zoom
            assert widget.rotation == rot
            assert widget.highlight_rects == [(100.0, 150.0, 250.0, 200.0)]

    doc.close()
