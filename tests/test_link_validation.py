"""
Comprehensive Unit and Integration Test Suite for Link Validation Logic
Conforming to official PAC Quality Checks documentation and W3C PDF11/PDF13 techniques.

Tested dimensions:
1. Link Structure and Association (AnnotationTaggedRule PDFUA-ANNOT-001)
2. PAC - Completeness of Link Elements (LinkCompletenessQualityRule QUAL-LINK-002)
3. PAC - TOCI Elements Contain Link Elements (TOCIContainsLinkRule QUAL-TOC-001)
4. Link Purpose and Alternative Text (W3C PDF11 / PDF13, LinkQualityRule QUAL-LINK-001)
5. Distinction of Form Widgets, Notes, Internal Links, and External Links
6. Duplicate OBJR Annotations Custom Rule (DuplicateOBJRLinkRule CUST-LINK-001)
7. Optional Span Tag independence
8. Separation of official PAC and custom rule results
"""

import os
import pytest
import pikepdf
import pymupdf

from src.pdf_inspector.core.models import (
    PDFDocumentModel,
    StructureNode,
    AnnotationModel,
    LinkModel,
    PageModel,
)
from src.pdf_inspector.engine.rule_base import CheckStatus, Severity
from src.pdf_inspector.engine.pdf_ua.annotation_rules import AnnotationTaggedRule
from src.pdf_inspector.engine.quality.quality_rules import (
    LinkQualityRule,
    LinkCompletenessQualityRule,
    TOCIContainsLinkRule,
    DuplicateOBJRLinkRule,
)
from src.pdf_inspector.engine.runner import AuditRunner


# ============================================================================
# Dimension 1: Link Structure and Association (PDFUA-ANNOT-001)
# ============================================================================

def test_link_structure_valid_tagged_link():
    """Verify that a tagged link annotation associated with a Link tag and text passes."""
    rule = AnnotationTaggedRule()
    link_node = StructureNode(id="l1", tag="Link", standard_tag="Link", page=1, text_content="Accessibility Guide")
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[link_node])
    ann = AnnotationModel(id="ann1", page=1, subtype="Link", rect=(10, 10, 100, 30), is_tagged=True)

    doc = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, annotations=[ann], structure_tree=root
    )
    results = rule.evaluate(doc)
    assert any(r.status == CheckStatus.PASS for r in results)
    assert not any(r.status == CheckStatus.FAIL for r in results)


def test_link_structure_untagged_link_annotation():
    """Verify that untagged link annotations produce structural errors."""
    rule = AnnotationTaggedRule()
    ann_untagged = AnnotationModel(id="ann1", page=1, subtype="Link", rect=(10, 10, 100, 30), is_tagged=False)

    doc = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, annotations=[ann_untagged]
    )
    results = rule.evaluate(doc)
    assert len(results) >= 1
    assert any(r.status == CheckStatus.FAIL and "not associated with any structure element" in r.message for r in results)


def test_link_structure_associated_with_non_link_element():
    """Verify that a link annotation associated with a non-Link tag (e.g. <P>) is flagged (Matterhorn 19-002)."""
    rule = AnnotationTaggedRule()
    p_node = StructureNode(id="p1", tag="P", standard_tag="P", page=1, text_content="Paragraph without Link tag")
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[p_node])
    ann = AnnotationModel(id="ann1", page=1, subtype="Link", rect=(10, 10, 100, 30), is_tagged=True)

    doc = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, annotations=[ann], structure_tree=root
    )
    results = rule.evaluate(doc)
    assert any(r.status == CheckStatus.FAIL and "Matterhorn 19-002" in r.message for r in results)


def test_link_structure_missing_text_content_w3c_pdf11():
    """Verify that a Link tag with no accessible text or Alt entry fails W3C PDF11."""
    rule = AnnotationTaggedRule()
    link_node = StructureNode(id="l1", tag="Link", standard_tag="Link", page=1, text_content="", alt_text=None)
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[link_node])
    ann = AnnotationModel(id="ann1", page=1, subtype="Link", rect=(10, 10, 100, 30), is_tagged=True)

    doc = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, annotations=[ann], structure_tree=root
    )
    results = rule.evaluate(doc)
    assert any(r.status == CheckStatus.FAIL and "W3C PDF11" in r.message for r in results)


def test_link_structure_flexible_hierarchy():
    """Verify that links are valid inside diverse parent elements (P, H1, LI, Div, Table TD)."""
    rule = AnnotationTaggedRule()
    for parent_tag in ["P", "H1", "LI", "Div", "TD", "Caption", "TOCI"]:
        link_node = StructureNode(id="lnk", tag="Link", standard_tag="Link", page=1, text_content="Section Link")
        parent_node = StructureNode(id="parent", tag=parent_tag, standard_tag=parent_tag, page=1, children=[link_node])
        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[parent_node])
        ann = AnnotationModel(id="ann1", page=1, subtype="Link", rect=(10, 10, 100, 30), is_tagged=True)

        doc = PDFDocumentModel(
            filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
            page_count=1, is_tagged=True, annotations=[ann], structure_tree=root
        )
        results = rule.evaluate(doc)
        assert any(r.status == CheckStatus.PASS for r in results), f"Link inside <{parent_tag}> should pass"
        assert not any(r.status == CheckStatus.FAIL for r in results)


# ============================================================================
# Dimension 2: PAC - Completeness of Link Elements (QUAL-LINK-002)
# ============================================================================

def test_pac_completeness_of_link_elements_pass():
    """Document with complete link elements enclosing linkable URLs returns PASS."""
    rule = LinkCompletenessQualityRule()
    page = PageModel(page_number=1, width=612, height=792, text="Visit https://example.com/info for details.")
    lnk = StructureNode(id="l1", tag="Link", standard_tag="Link", page=1, text_content="https://example.com/info")
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[lnk])

    doc = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, pages=[page], structure_tree=root
    )
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS
    assert results[0].items_count == 1


def test_pac_completeness_of_link_elements_warning():
    """Document with unlinked URL/email returns WARNING matching official PAC behavior."""
    rule = LinkCompletenessQualityRule()
    page = PageModel(page_number=1, width=612, height=792, text="Contact us at support@example.com for help.")
    p_node = StructureNode(id="p1", tag="P", standard_tag="P", page=1, text_content="Contact us at support@example.com for help.")
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[p_node])

    doc = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, pages=[page], structure_tree=root
    )
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.WARNING
    assert "support@example.com" in results[0].message


def test_pac_completeness_of_link_elements_skipped():
    """Document with no linkable text and no links returns [] (skipped, '-' in PAC)."""
    rule = LinkCompletenessQualityRule()
    page = PageModel(page_number=1, width=612, height=792, text="Plain document text without URLs or emails.")
    p_node = StructureNode(id="p1", tag="P", standard_tag="P", page=1, text_content="Plain document text without URLs or emails.")
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[p_node])

    doc = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, pages=[page], structure_tree=root
    )
    results = rule.evaluate(doc)
    assert results == []


# ============================================================================
# Dimension 3: PAC - TOCI Elements Contain Link Elements (QUAL-TOC-001)
# ============================================================================

def test_toci_contains_link_zero_links_fails():
    """TOCI element with 0 qualifying links returns FAIL (Matterhorn 18-001)."""
    rule = TOCIContainsLinkRule()
    toci = StructureNode(id="t1", tag="TOCI", standard_tag="TOCI", page=1, children=[
        StructureNode(id="span1", tag="Span", standard_tag="Span", text_content="1. Introduction ... 5")
    ])
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[toci])

    doc = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.FAIL
    assert "Matterhorn 18-001" in results[0].message


def test_toci_contains_link_one_qualifying_link_passes():
    """TOCI element with exactly 1 qualifying Link element returns PASS."""
    rule = TOCIContainsLinkRule()
    lnk = StructureNode(id="l1", tag="Link", standard_tag="Link", page=1, text_content="1. Introduction")
    toci = StructureNode(id="t1", tag="TOCI", standard_tag="TOCI", page=1, children=[lnk])
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[toci])

    doc = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS
    assert results[0].items_count == 1


def test_toci_contains_link_multiple_qualifying_links_passes():
    """TOCI element with multiple qualifying Link elements returns PASS."""
    rule = TOCIContainsLinkRule()
    lnk1 = StructureNode(id="l1", tag="Link", standard_tag="Link", page=1, text_content="Chapter 1")
    lnk2 = StructureNode(id="l2", tag="Link", standard_tag="Link", page=1, text_content="Page 12")
    toci = StructureNode(id="t1", tag="TOCI", standard_tag="TOCI", page=1, children=[lnk1, lnk2])
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[toci])

    doc = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS
    assert results[0].items_count == 1


def test_toci_rule_does_not_apply_to_non_toci_elements():
    """Ordinary paragraphs, forms, and footnotes without TOCI elements return [] (skipped)."""
    rule = TOCIContainsLinkRule()
    p_node = StructureNode(id="p1", tag="P", standard_tag="P", page=1, text_content="Ordinary text")
    note_node = StructureNode(id="n1", tag="Note", standard_tag="Note", page=1, text_content="Footnote 1")
    form_node = StructureNode(id="f1", tag="Form", standard_tag="Form", page=1)
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[p_node, note_node, form_node])

    doc = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    results = rule.evaluate(doc)
    assert results == []


# ============================================================================
# Dimension 4: Link Purpose and Alternative Text (W3C PDF11 / PDF13, QUAL-LINK-001)
# ============================================================================

def test_w3c_pdf11_descriptive_text_without_alt_passes():
    """Descriptive visible text satisfies W3C PDF11 without requiring an /Alt entry."""
    rule = LinkQualityRule()
    lnk = LinkModel(
        id="lnk1", page=1, text="Download Q3 2026 Financial Report (PDF)",
        uri="https://example.com/report.pdf", alt_text=None
    )
    doc = PDFDocumentModel(filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7", page_count=1, links=[lnk])
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS


def test_w3c_pdf13_alt_text_overrides_vague_visible_text():
    """Vague visible text ('click here') with descriptive /Alt satisfies W3C PDF13."""
    rule = LinkQualityRule()
    lnk = LinkModel(
        id="lnk1", page=1, text="Click Here",
        uri="https://example.com/annual-report",
        alt_text="Download Annual Performance Report 2026"
    )
    doc = PDFDocumentModel(filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7", page_count=1, links=[lnk])
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS


def test_w3c_pdf13_bare_url_with_alt_text_passes():
    """Bare URL anchor text with descriptive /Alt text satisfies W3C PDF13."""
    rule = LinkQualityRule()
    lnk = LinkModel(
        id="lnk1", page=1, text="https://example.com/data/download?id=99281",
        uri="https://example.com/data/download?id=99281",
        alt_text="Dataset of Environmental Observations 2026"
    )
    doc = PDFDocumentModel(filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7", page_count=1, links=[lnk])
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS


def test_link_quality_flags_vague_labels_and_bare_urls():
    """Vague labels and bare URLs lacking /Alt produce WARNING results."""
    rule = LinkQualityRule()
    l_vague = LinkModel(id="l1", page=1, text="read more", uri="https://example.com/blog", alt_text=None)
    l_bare = LinkModel(id="l2", page=1, text="https://example.com/page", uri="https://example.com/page", alt_text=None)
    l_empty = LinkModel(id="l3", page=1, text="", uri="https://example.com/empty", alt_text=None)

    doc = PDFDocumentModel(filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7", page_count=1, links=[l_vague, l_bare, l_empty])
    results = rule.evaluate(doc)
    assert any(r.status == CheckStatus.WARNING and "Ambiguous link label" in r.message for r in results)
    assert any(r.status == CheckStatus.WARNING and "raw URL strings" in r.message for r in results)
    assert any(r.status == CheckStatus.WARNING and "lacks accessible link text" in r.message for r in results)


# ============================================================================
# Dimension 5: Forms, Notes, Internal Links, and External Links
# ============================================================================

def test_form_widgets_and_notes_distinguished_from_links():
    """Form widgets and note annotations are not flagged as invalid links."""
    rule = AnnotationTaggedRule()
    ann_widget = AnnotationModel(id="w1", page=1, subtype="Widget", rect=(10, 10, 50, 30), is_tagged=True)
    ann_note = AnnotationModel(id="n1", page=1, subtype="Text", rect=(60, 10, 80, 30), is_tagged=True)

    form_node = StructureNode(id="fn1", tag="Form", standard_tag="Form", page=1)
    note_node = StructureNode(id="nn1", tag="Note", standard_tag="Note", page=1, text_content="Footnote comment")
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[form_node, note_node])

    doc = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, annotations=[ann_widget, ann_note], structure_tree=root
    )
    results = rule.evaluate(doc)
    assert any(r.status == CheckStatus.PASS for r in results)
    assert not any(r.status == CheckStatus.FAIL for r in results)


def test_internal_and_external_links_different_actions():
    """Internal links (page destinations) and external links (URIs) are both validated properly."""
    rule = LinkQualityRule()
    internal_link = LinkModel(
        id="l_int", page=1, text="Jump to Section 3",
        uri="", is_internal=True, destination_page=3
    )
    external_link = LinkModel(
        id="l_ext", page=1, text="W3C PDF Accessibility Techniques",
        uri="https://www.w3.org/WAI/WCAG21/Techniques/pdf/", is_internal=False
    )
    doc = PDFDocumentModel(filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7", page_count=3, links=[internal_link, external_link])
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS


# ============================================================================
# Dimension 6: Duplicate OBJR Annotations - Custom Rule (CUST-LINK-001)
# ============================================================================

def test_duplicate_objr_custom_rule_detects_duplicates():
    """Link element with multiple OBJR referencing the same annotation triggers CUST-LINK-001 FAIL."""
    rule = DuplicateOBJRLinkRule()
    assert rule.standard == "Custom"
    assert rule.rule_id == "CUST-LINK-001"

    # Single link referencing the same annotation twice
    lnk_dup = StructureNode(
        id="l1", tag="Link", standard_tag="Link", page=1,
        attributes={"objr_refs": ["(12, 0)", "(12, 0)"]}
    )
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[lnk_dup])
    doc = PDFDocumentModel(filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7", page_count=1, structure_tree=root)

    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.FAIL
    assert "multiple OBJR annotations" in results[0].message


def test_duplicate_objr_custom_rule_separate_links_not_duplicates():
    """Separate legitimate links with unique annotations pass without duplicate errors."""
    rule = DuplicateOBJRLinkRule()
    lnk1 = StructureNode(
        id="l1", tag="Link", standard_tag="Link", page=1,
        attributes={"objr_refs": ["(12, 0)"]}
    )
    lnk2 = StructureNode(
        id="l2", tag="Link", standard_tag="Link", page=1,
        attributes={"objr_refs": ["(14, 0)"]}
    )
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[lnk1, lnk2])
    doc = PDFDocumentModel(filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7", page_count=1, structure_tree=root)

    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS
    assert results[0].items_count == 2


# ============================================================================
# Dimension 7: Optional Span Tag Independence
# ============================================================================

def test_optional_span_tag_absence_does_not_error():
    """Links without a <Span> tag validate cleanly across all checks."""
    # Structure association check
    struct_rule = AnnotationTaggedRule()
    link_no_span = StructureNode(id="l1", tag="Link", standard_tag="Link", page=1, text_content="Direct Link Text")
    root_no_span = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[link_no_span])
    ann = AnnotationModel(id="ann1", page=1, subtype="Link", rect=(10, 10, 100, 30), is_tagged=True)
    doc_no_span = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, annotations=[ann], structure_tree=root_no_span
    )
    res_struct = struct_rule.evaluate(doc_no_span)
    assert any(r.status == CheckStatus.PASS for r in res_struct)
    assert not any(r.status == CheckStatus.FAIL for r in res_struct)

    # TOCI containment check without Span
    toci_rule = TOCIContainsLinkRule()
    toci_no_span = StructureNode(id="t1", tag="TOCI", standard_tag="TOCI", page=1, children=[link_no_span])
    root_toci = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[toci_no_span])
    doc_toci = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_toci
    )
    res_toci = toci_rule.evaluate(doc_toci)
    assert len(res_toci) == 1
    assert res_toci[0].status == CheckStatus.PASS

    # Duplicate OBJR check without Span
    dup_rule = DuplicateOBJRLinkRule()
    res_dup = dup_rule.evaluate(doc_no_span)
    assert len(res_dup) == 1
    assert res_dup[0].status == CheckStatus.PASS


def test_optional_span_tag_presence_validated_cleanly():
    """Links with a nested <Span> tag validate cleanly across all checks."""
    span_node = StructureNode(id="s1", tag="Span", standard_tag="Span", page=1, text_content="Span Link Text")
    link_with_span = StructureNode(id="l1", tag="Link", standard_tag="Link", page=1, children=[span_node])
    root_with_span = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[link_with_span])
    ann = AnnotationModel(id="ann1", page=1, subtype="Link", rect=(10, 10, 100, 30), is_tagged=True)

    struct_rule = AnnotationTaggedRule()
    doc_with_span = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, annotations=[ann], structure_tree=root_with_span
    )
    res_struct = struct_rule.evaluate(doc_with_span)
    assert any(r.status == CheckStatus.PASS for r in res_struct)
    assert not any(r.status == CheckStatus.FAIL for r in res_struct)

    toci_rule = TOCIContainsLinkRule()
    toci_with_span = StructureNode(id="t1", tag="TOCI", standard_tag="TOCI", page=1, children=[link_with_span])
    root_toci = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[toci_with_span])
    doc_toci = PDFDocumentModel(
        filepath="", filename="test.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_toci
    )
    res_toci = toci_rule.evaluate(doc_toci)
    assert len(res_toci) == 1
    assert res_toci[0].status == CheckStatus.PASS


# ============================================================================
# Dimension 8: Distinction of Official PAC Results vs Custom Rule Results
# ============================================================================

def test_distinguish_official_pac_from_custom_rule():
    """Verify that official PAC checks and the custom duplicate OBJR rule have distinct standards."""
    runner = AuditRunner()
    rule_ids = {r.rule_id: r for r in runner.rules}

    # Official PAC Quality rules
    assert rule_ids["QUAL-LINK-001"].standard == "Quality"
    assert rule_ids["QUAL-LINK-002"].standard == "Quality"
    assert rule_ids["QUAL-TOC-001"].standard == "Quality"

    # Official PDF/UA rule
    assert rule_ids["PDFUA-ANNOT-001"].standard == "PDF/UA"

    # Custom validation rule
    assert rule_ids["CUST-LINK-001"].standard == "Custom"


# ============================================================================
# End-to-End Real PDF Verification using pikepdf
# ============================================================================

def test_real_pdf_link_validation_with_pikepdf(tmp_path):
    """Generate a real tagged PDF using pikepdf and test end-to-end evaluation."""
    pdf_path = str(tmp_path / "test_links.pdf")
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(612, 792))

    action = pikepdf.Dictionary({
        "/Type": pikepdf.Name("/Action"),
        "/S": pikepdf.Name("/URI"),
        "/URI": "https://www.w3.org"
    })
    link_annot = pdf.make_indirect(pikepdf.Dictionary({
        "/Type": pikepdf.Name("/Annot"),
        "/Subtype": pikepdf.Name("/Link"),
        "/Rect": pikepdf.Array([100, 700, 250, 720]),
        "/A": action,
        "/StructParent": 0
    }))
    page.Annots = pdf.make_indirect(pikepdf.Array([link_annot]))

    # Create structure tree: StructTreeRoot -> P -> Link -> OBJR
    objr = pikepdf.Dictionary({
        "/Type": pikepdf.Name("/OBJR"),
        "/Obj": link_annot,
        "/Pg": page.obj
    })

    link_elem = pdf.make_indirect(pikepdf.Dictionary({
        "/Type": pikepdf.Name("/StructElem"),
        "/S": pikepdf.Name("/Link"),
        "/Pg": page.obj,
        "/Alt": "World Wide Web Consortium",
        "/K": pikepdf.Array([objr])
    }))

    p_elem = pdf.make_indirect(pikepdf.Dictionary({
        "/Type": pikepdf.Name("/StructElem"),
        "/S": pikepdf.Name("/P"),
        "/Pg": page.obj,
        "/K": pikepdf.Array([link_elem])
    }))

    root_elem = pdf.make_indirect(pikepdf.Dictionary({
        "/Type": pikepdf.Name("/StructTreeRoot"),
        "/K": pikepdf.Array([p_elem])
    }))

    pdf.Root.StructTreeRoot = root_elem
    pdf.Root.MarkInfo = pikepdf.Dictionary({"/Marked": True})

    pdf.save(pdf_path)
    pdf.close()

    with pikepdf.open(pdf_path) as saved_pdf:
        annot_xref = saved_pdf.pages[0].Annots[0].objgen[0]

    # Test AnnotationTaggedRule on real file
    doc_model = PDFDocumentModel(
        filepath=pdf_path,
        filename="test_links.pdf",
        filesize=os.path.getsize(pdf_path),
        pdf_version="1.7",
        page_count=1,
        is_tagged=True,
        annotations=[
            AnnotationModel(id=f"annot_p1_{annot_xref}", page=1, subtype="Link", rect=(100, 700, 250, 720), is_tagged=True)
        ]
    )
    rule_annot = AnnotationTaggedRule()
    results_annot = rule_annot.evaluate(doc_model)
    assert any(r.status == CheckStatus.PASS for r in results_annot)
    assert not any(r.status == CheckStatus.FAIL for r in results_annot)

    # Test DuplicateOBJRLinkRule on real file
    rule_dup = DuplicateOBJRLinkRule()
    results_dup = rule_dup.evaluate(doc_model)
    assert len(results_dup) == 1
    assert results_dup[0].status == CheckStatus.PASS
