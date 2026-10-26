"""
Regression tests for Artifact XObject tracking and Alternative Descriptions category boundary.

Verifies:
1. Image XObject invoked inside /Artifact BMC ... EMC or /Artifact BDC ... EMC is classified as is_artifact=True.
2. Image XObject invoked outside Artifact remains non-artifact (is_artifact=False).
3. Nested marked content (/Artifact BMC ... /PlacedPDF BMC ... /Im0 Do ... EMC ... EMC) correctly tracks image as artifact.
4. Alternative Descriptions rule (PDFUA-ALT-001) evaluates only structure elements and links, not untagged images.
5. Genuine untagged real-content images remain covered by Content rules (PDFUA-CONTENT-002).
"""

import os
import tempfile
import pytest
import pymupdf
import pikepdf

from src.pdf_inspector.core.document_parser import DocumentParser
from src.pdf_inspector.core.models import (
    PDFDocumentModel, PageModel, StructureNode, ImageModel,
    ContentOccurrenceModel, CheckStatus
)
from src.pdf_inspector.engine.pdf_ua.alt_text_rules import FigureAlternativeTextRule
from src.pdf_inspector.engine.pdf_ua.content_rules import ContentTaggedRule


def test_image_xobject_inside_artifact_marked_content():
    """An image XObject invoked inside /Artifact BMC ... EMC is recognized as an artifact."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "artifact_img.pdf")

        # Create a 1-page PDF with an image using PyMuPDF
        doc = pymupdf.open()
        page = doc.new_page(width=300, height=300)
        # Insert a 50x50 dummy pixmap
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False)
        pix.clear_with(128)
        img_rect = pymupdf.Rect(50, 50, 150, 150)
        page.insert_image(img_rect, pixmap=pix)
        doc.save(pdf_path)
        doc.close()

        # Re-write the content stream using pikepdf to wrap the Do operator in /Artifact BMC ... EMC
        with pikepdf.open(pdf_path, allow_overwriting_input=True) as pike:
            p0 = pike.pages[0]
            stream = b"".join(s.read_bytes() for s in (p0.Contents if isinstance(p0.Contents, pikepdf.Array) else [p0.Contents])).decode("latin1")
            
            # Find the image name /Im0 Do
            import re
            m = re.search(r"/(\w+)\s+Do", stream)
            assert m is not None, "Failed to find image Do in stream"
            img_name = m.group(1)

            # Wrap in /Artifact BMC ... EMC
            wrapped_stream = stream.replace(
                f"/{img_name} Do",
                f"/Artifact BMC\nq\n/{img_name} Do\nQ\nEMC"
            )
            p0.Contents = pike.make_stream(wrapped_stream.encode("latin1"))
            pike.save(pdf_path)

        # Parse with DocumentParser
        parsed_doc = DocumentParser(pdf_path).parse()
        assert len(parsed_doc.images) >= 1
        img = parsed_doc.images[0]
        assert img.is_artifact is True, "Image invoked inside /Artifact BMC was not marked as is_artifact=True"


def test_image_xobject_outside_artifact_remains_non_artifact():
    """An image XObject invoked outside any marked content remains is_artifact=False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "plain_img.pdf")

        doc = pymupdf.open()
        page = doc.new_page(width=300, height=300)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False)
        pix.clear_with(200)
        page.insert_image(pymupdf.Rect(20, 20, 80, 80), pixmap=pix)
        doc.save(pdf_path)
        doc.close()

        parsed_doc = DocumentParser(pdf_path).parse()
        assert len(parsed_doc.images) >= 1
        img = parsed_doc.images[0]
        assert img.is_artifact is False, "Unmarked image was incorrectly marked as an artifact"


def test_nested_artifact_placed_pdf_image_classified_as_artifact():
    """Nested marked content (/Artifact BMC ... /PlacedPDF BMC ... /Im0 Do ... EMC ... EMC) is recognized as an artifact."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "nested_artifact_img.pdf")

        doc = pymupdf.open()
        page = doc.new_page(width=300, height=300)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
        page.insert_image(pymupdf.Rect(10, 10, 90, 90), pixmap=pix)
        doc.save(pdf_path)
        doc.close()

        with pikepdf.open(pdf_path, allow_overwriting_input=True) as pike:
            p0 = pike.pages[0]
            stream = b"".join(s.read_bytes() for s in (p0.Contents if isinstance(p0.Contents, pikepdf.Array) else [p0.Contents])).decode("latin1")
            import re
            m = re.search(r"/(\w+)\s+Do", stream)
            assert m is not None
            img_name = m.group(1)

            # Nested artifact container
            wrapped_stream = stream.replace(
                f"/{img_name} Do",
                f"/Artifact BMC\n/PlacedPDF BMC\nq\n/{img_name} Do\nQ\nEMC\nEMC"
            )
            p0.Contents = pike.make_stream(wrapped_stream.encode("latin1"))
            pike.save(pdf_path)

        parsed_doc = DocumentParser(pdf_path).parse()
        assert len(parsed_doc.images) >= 1
        img = parsed_doc.images[0]
        assert img.is_artifact is True, "Nested artifact image was not marked as is_artifact=True"


def test_alt_descriptions_rule_evaluates_only_structure_elements():
    """FigureAlternativeTextRule evaluates Figure/Formula structure elements and does not count untagged images."""
    rule = FigureAlternativeTextRule()

    # 1 Figure with alt, 1 Figure without alt, 1 Formula with alt
    fig_good = StructureNode("f1", "Figure", "Figure", page=1, alt_text="A decorative landscape")
    fig_bad = StructureNode("f2", "Figure", "Figure", page=1, alt_text=None, actual_text=None)
    form_good = StructureNode("m1", "Formula", "Formula", page=1, alt_text="x squared plus y squared")
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[fig_good, fig_bad, form_good])

    # Add 3 untagged non-artifact images to the document model
    untagged_imgs = [
        ImageModel(id=f"img_{i}", page=1, bbox=(0, 0, 100, 100), width=100, height=100,
                   colorspace="RGB", has_alt=False, is_artifact=False, structure_element_id=None)
        for i in range(3)
    ]

    doc = PDFDocumentModel(
        filepath="", filename="struct_alt.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root, images=untagged_imgs
    )

    results = rule.evaluate(doc)

    # Exactly 1 failure for fig_bad
    fails = [r for r in results if r.status == CheckStatus.FAIL]
    assert len(fails) == 1
    assert "Figure" in fails[0].message
    assert "Alternative text missing" in fails[0].message
    # Untagged images must NOT appear in Alternative Descriptions failures
    assert not any("Image on page" in r.message for r in results)


def test_genuine_untagged_real_content_image_caught_by_content_rules():
    """Genuine untagged real-content images remain covered by ContentTaggedRule (PDFUA-CONTENT-002)."""
    rule = ContentTaggedRule()

    # Page with an unmarked real content image operation (outside marked content, not artifact)
    occ = ContentOccurrenceModel(
        page_number=1,
        operator_type="xobject",
        operator_name="Do",
        is_unmarked_real_content=True,
        xobject_name="Im0",
        snippet="XObject /Im0 Do",
        bbox=(50.0, 50.0, 150.0, 150.0)
    )
    p = PageModel(
        page_number=1, width=600.0, height=800.0,
        unmarked_real_content_count=1,
        content_occurrences=[occ]
    )
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[])
    doc = PDFDocumentModel(
        filepath="", filename="untagged_img.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, pages=[p], structure_tree=root
    )

    results = rule.evaluate(doc)
    fails = [r for r in results if r.status == CheckStatus.FAIL]
    assert len(fails) >= 1
    assert any("neither enclosed in marked content (/MCID) nor marked as an Artifact" in f.message for f in fails)


def test_figure_non_whitespace_alt_takes_precedence():
    """Non-whitespace /Alt takes precedence over /ActualText."""
    rule = FigureAlternativeTextRule()
    node = StructureNode(
        "fig1", "Figure", "Figure", page=1,
        alt_text="Primary description", actual_text="Secondary transcription"
    )
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node])
    doc = PDFDocumentModel(
        filepath="", filename="t1.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    results = rule.evaluate(doc)
    assert not any(r.status == CheckStatus.FAIL for r in results)
    pass_results = [r for r in results if r.status == CheckStatus.PASS]
    assert len(pass_results) >= 1


def test_figure_whitespace_alt_with_valid_actual_text_passes():
    """Whitespace-only /Alt with valid /ActualText correctly falls back and passes."""
    rule = FigureAlternativeTextRule()
    node = StructureNode(
        "form1", "Formula", "Formula", page=1,
        alt_text="  \r\n\t  ", actual_text="omega subscript b equal 35 radians per second."
    )
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node])
    doc = PDFDocumentModel(
        filepath="", filename="t2.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    results = rule.evaluate(doc)
    assert not any(r.status == CheckStatus.FAIL for r in results)
    pass_results = [r for r in results if r.status == CheckStatus.PASS]
    assert len(pass_results) >= 1


def test_figure_empty_alt_with_valid_actual_text_passes():
    """Empty /Alt with valid /ActualText falls back and passes."""
    rule = FigureAlternativeTextRule()
    node = StructureNode(
        "form2", "Formula", "Formula", page=1,
        alt_text="", actual_text="E equals m c squared"
    )
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node])
    doc = PDFDocumentModel(
        filepath="", filename="t3.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    results = rule.evaluate(doc)
    assert not any(r.status == CheckStatus.FAIL for r in results)
    pass_results = [r for r in results if r.status == CheckStatus.PASS]
    assert len(pass_results) >= 1


def test_figure_both_alt_and_actual_text_absent_or_whitespace_fails():
    """Both /Alt and /ActualText absent, empty, or whitespace-only must fail."""
    rule = FigureAlternativeTextRule()
    # Case A: both None
    node_none = StructureNode("fig_none", "Figure", "Figure", page=1, alt_text=None, actual_text=None)
    # Case B: both whitespace
    node_ws = StructureNode("form_ws", "Formula", "Formula", page=1, alt_text="   ", actual_text="\r\n\t")
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node_none, node_ws])
    doc = PDFDocumentModel(
        filepath="", filename="t4.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    results = rule.evaluate(doc)
    fails = [r for r in results if r.status == CheckStatus.FAIL]
    assert len(fails) == 2
    failed_ids = {r.object_reference for r in fails}
    assert "<Figure id='fig_none'>" in failed_ids
    assert "<Formula id='form_ws'>" in failed_ids
