"""
Unit tests for PDF/UA and WCAG Rules
"""

import pytest
from src.pdf_inspector.core.models import (
    PDFDocumentModel, PageModel, StructureNode, FontModel, ImageModel, CheckStatus
)
from src.pdf_inspector.engine.pdf_ua.syntax_rules import PDFSyntaxBasicRule
from src.pdf_inspector.engine.pdf_ua.font_rules import FontEmbeddingRule, FontToUnicodeRule
from src.pdf_inspector.engine.pdf_ua.content_rules import TaggedPDFRule
from src.pdf_inspector.engine.pdf_ua.language_rules import DocumentLanguageRule
from src.pdf_inspector.engine.pdf_ua.metadata_rules import MetadataCompletenessRule
from src.pdf_inspector.engine.pdf_ua.document_settings_rules import DisplayDocTitleRule
from src.pdf_inspector.engine.wcag.wcag_rules import WCAGTextAlternativesRule, WCAGNavigableRule


def test_tagged_pdf_rule():
    rule = TaggedPDFRule()

    # Case 1: Untagged document
    doc_untagged = PDFDocumentModel(
        filepath="", filename="untagged.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=False, structure_tree=None
    )
    res = rule.evaluate(doc_untagged)
    assert res[0].status == CheckStatus.FAIL

    # Case 2: Tagged document with structure tree
    doc_tagged = PDFDocumentModel(
        filepath="", filename="tagged.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    )
    res = rule.evaluate(doc_tagged)
    assert res[0].status == CheckStatus.PASS


def test_font_embedding_rule():
    rule = FontEmbeddingRule()

    # Case 1: One unembedded font used on one page
    f1 = FontModel("Helvetica", "Type1", is_embedded=False, is_subset=False, has_tounicode=True, encoding="WinAnsi", pages=[1], is_used=True)
    doc1 = PDFDocumentModel(filepath="", filename="f.pdf", filesize=10, pdf_version="1.7", page_count=1, fonts=[f1])
    res1 = rule.evaluate(doc1)
    assert len(res1) == 1
    assert res1[0].status == CheckStatus.FAIL
    assert res1[0].page == 1
    assert res1[0].items_count == 1

    # Case 2: One unembedded font used on multiple pages (4 pages -> 4 FAIL evaluation records)
    f2 = FontModel("Arial", "TrueType", is_embedded=False, is_subset=False, has_tounicode=True, encoding="WinAnsi", pages=[1, 2, 3, 4], is_used=True)
    doc2 = PDFDocumentModel(filepath="", filename="f.pdf", filesize=10, pdf_version="1.7", page_count=4, fonts=[f2])
    res2 = rule.evaluate(doc2)
    fail_res2 = [r for r in res2 if r.status == CheckStatus.FAIL]
    assert [r.page for r in fail_res2] == [1, 2, 3, 4]
    assert sum(r.items_count for r in fail_res2) == 1

    # Case 3: Multiple unembedded fonts on distinct pages
    f3_1 = FontModel("Helvetica-Bold", "Type1", is_embedded=False, is_subset=False, has_tounicode=True, encoding="WinAnsi", pages=[1, 4], is_used=True)
    f3_2 = FontModel("Helvetica", "Type1", is_embedded=False, is_subset=False, has_tounicode=True, encoding="WinAnsi", pages=[1, 2, 3], is_used=True)
    f3_3 = FontModel("ABCDEF+Courier", "Type1", is_embedded=True, is_subset=True, has_tounicode=True, encoding="WinAnsi", pages=[1, 2, 3, 4], is_used=True)
    doc3 = PDFDocumentModel(filepath="", filename="f.pdf", filesize=10, pdf_version="1.7", page_count=4, fonts=[f3_1, f3_2, f3_3])
    res3 = rule.evaluate(doc3)
    fail_res3 = [r for r in res3 if r.status == CheckStatus.FAIL]
    assert len(fail_res3) == 5  # 2 for f3_1 + 3 for f3_2
    pass_res3 = [r for r in res3 if r.status == CheckStatus.PASS]
    assert len(pass_res3) == 1
    assert pass_res3[0].items_count == 1  # 1 embedded font passed

    # Case 4: All embedded fonts
    f4 = FontModel("ABCDEF+Arial", "TrueType", is_embedded=True, is_subset=True, has_tounicode=True, encoding="WinAnsi", pages=[1, 2], is_used=True)
    doc4 = PDFDocumentModel(filepath="", filename="f.pdf", filesize=10, pdf_version="1.7", page_count=2, fonts=[f4])
    res4 = rule.evaluate(doc4)
    assert len(res4) == 1
    assert res4[0].status == CheckStatus.PASS
    assert res4[0].items_count == 1

    # Case 5: A font listed in the PDF but not actually used (is_used=False) -> should NOT produce failures
    f5_unused = FontModel("UnusedFont", "Type1", is_embedded=False, is_subset=False, has_tounicode=False, encoding="Custom", pages=[1, 2], is_used=False)
    f5_used = FontModel("ABCDEF+Arial", "TrueType", is_embedded=True, is_subset=True, has_tounicode=True, encoding="WinAnsi", pages=[1], is_used=True)
    doc5 = PDFDocumentModel(filepath="", filename="f.pdf", filesize=10, pdf_version="1.7", page_count=2, fonts=[f5_unused, f5_used])
    res5 = rule.evaluate(doc5)
    fail_res5 = [r for r in res5 if r.status == CheckStatus.FAIL]
    assert len(fail_res5) == 0
    assert any(r.status == CheckStatus.PASS for r in res5)

    # Case 6: Same font family appearing with different subsets/identities
    f6_1 = FontModel("ABCDEF+Arial", "TrueType", is_embedded=True, is_subset=True, has_tounicode=True, encoding="WinAnsi", pages=[1], is_used=True)
    f6_2 = FontModel("GHIJKL+Arial", "TrueType", is_embedded=True, is_subset=True, has_tounicode=True, encoding="WinAnsi", pages=[2], is_used=True)
    doc6 = PDFDocumentModel(filepath="", filename="f.pdf", filesize=10, pdf_version="1.7", page_count=2, fonts=[f6_1, f6_2])
    res6 = rule.evaluate(doc6)
    assert all(r.status == CheckStatus.PASS for r in res6)
    assert res6[0].items_count == 2


def test_font_tounicode_rule():
    rule = FontToUnicodeRule()

    # Case 1: Embedded font with valid Unicode mapping
    f1_valid = FontModel("ABCDEF+Arial", "TrueType", is_embedded=True, is_subset=True, has_tounicode=True, encoding="Identity-H", pages=[1], is_used=True)
    doc1 = PDFDocumentModel(filepath="", filename="f1.pdf", filesize=10, pdf_version="1.7", page_count=1, fonts=[f1_valid])
    res1 = rule.evaluate(doc1)
    assert len(res1) == 1
    assert res1[0].status == CheckStatus.PASS
    assert res1[0].items_count == 1

    # Case 2: Embedded font with missing/invalid Unicode mapping
    f2_invalid = FontModel("ABCDEF+Symbol", "Type1", is_embedded=True, is_subset=True, has_tounicode=False, encoding="Custom", pages=[1], is_used=True)
    doc2 = PDFDocumentModel(filepath="", filename="f2.pdf", filesize=10, pdf_version="1.7", page_count=1, fonts=[f2_invalid])
    res2 = rule.evaluate(doc2)
    assert len(res2) == 1
    assert res2[0].status == CheckStatus.WARNING
    assert "lacks a valid Unicode mapping" in res2[0].message
    assert res2[0].items_count == 1

    # Case 3: Unembedded font with valid standard encoding (e.g. WinAnsiEncoding)
    # Provides valid Unicode mapping via standard encoding, so no defect is flagged,
    # but does not receive an embedded PDF/UA compliance PASS.
    f3_winansi = FontModel("Arial", "TrueType", is_embedded=False, is_subset=False, has_tounicode=False, encoding="WinAnsiEncoding", pages=[1], is_used=True)
    doc3 = PDFDocumentModel(filepath="", filename="f3.pdf", filesize=10, pdf_version="1.7", page_count=1, fonts=[f3_winansi])
    res3 = rule.evaluate(doc3)
    assert len(res3) == 0

    # Case 4: Unembedded font with missing/invalid Unicode mapping (custom encoding, no ToUnicode)
    # The genuine Unicode mapping defect is NOT suppressed despite font being unembedded!
    f4_unemb_inv = FontModel("CustomFont", "TrueType", is_embedded=False, is_subset=False, has_tounicode=False, encoding="Custom", pages=[2], is_used=True)
    doc4 = PDFDocumentModel(filepath="", filename="f4.pdf", filesize=10, pdf_version="1.7", page_count=2, fonts=[f4_unemb_inv])
    res4 = rule.evaluate(doc4)
    assert len(res4) == 1
    assert res4[0].status == CheckStatus.WARNING
    assert "lacks a valid Unicode mapping" in res4[0].message
    assert res4[0].page == 2
    assert res4[0].items_count == 1

    # Case 5: Unused font resources (is_used=False) -> should NOT produce warnings or false passes
    f5_unused = FontModel("UnusedFont", "Type1", is_embedded=False, is_subset=False, has_tounicode=False, encoding="Custom", pages=[1], is_used=False)
    doc5 = PDFDocumentModel(filepath="", filename="f5.pdf", filesize=10, pdf_version="1.7", page_count=1, fonts=[f5_unused])
    res5 = rule.evaluate(doc5)
    assert len(res5) == 0

    # Case 6: Used Type 0 font with Identity-H and no /ToUnicode -> must report defect (Matterhorn 14-003)
    f6_identity_h_no_tounicode = FontModel(
        "Type0IdentityH", "Type0", is_embedded=True, is_subset=True,
        has_tounicode=False, encoding="Identity-H", pages=[1], is_used=True
    )
    doc6 = PDFDocumentModel(
        filepath="", filename="f6.pdf", filesize=10, pdf_version="1.7",
        page_count=1, fonts=[f6_identity_h_no_tounicode]
    )
    res6 = rule.evaluate(doc6)
    assert len(res6) == 1
    assert res6[0].status == CheckStatus.WARNING
    assert "lacks a valid Unicode mapping" in res6[0].message
    assert res6[0].items_count == 1

    # Case 7: Unused Type 0 font with Identity-H and no /ToUnicode -> should NOT produce findings
    f7_unused_identity_h = FontModel(
        "Type0UnusedIdentityH", "Type0", is_embedded=True, is_subset=True,
        has_tounicode=False, encoding="Identity-H", pages=[1], is_used=False
    )
    doc7 = PDFDocumentModel(
        filepath="", filename="f7.pdf", filesize=10, pdf_version="1.7",
        page_count=1, fonts=[f7_unused_identity_h]
    )
    res7 = rule.evaluate(doc7)
    assert len(res7) == 0


def test_language_rule():
    rule = DocumentLanguageRule()

    # Missing language
    doc_nolang = PDFDocumentModel(filepath="", filename="l.pdf", filesize=10, pdf_version="1.7", page_count=1, language=None)
    assert rule.evaluate(doc_nolang)[0].status == CheckStatus.FAIL

    # Valid BCP 47
    doc_valid = PDFDocumentModel(filepath="", filename="l.pdf", filesize=10, pdf_version="1.7", page_count=1, language="en-US")
    assert rule.evaluate(doc_valid)[0].status == CheckStatus.PASS


def test_display_doc_title_rule():
    rule = DisplayDocTitleRule()

    doc_false = PDFDocumentModel(filepath="", filename="d.pdf", filesize=10, pdf_version="1.7", page_count=1, display_doc_title=False)
    assert rule.evaluate(doc_false)[0].status == CheckStatus.FAIL

    doc_true = PDFDocumentModel(filepath="", filename="d.pdf", filesize=10, pdf_version="1.7", page_count=1, display_doc_title=True)
    assert rule.evaluate(doc_true)[0].status == CheckStatus.PASS


def test_wcag_text_alternatives():
    rule = WCAGTextAlternativesRule()

    # Image missing alt text
    img_no_alt = ImageModel("img1", 1, (10, 10, 100, 100), 200, 200, "RGB", has_alt=False)
    doc_bad = PDFDocumentModel(filepath="", filename="i.pdf", filesize=10, pdf_version="1.7", page_count=1, images=[img_no_alt])
    assert rule.evaluate(doc_bad)[0].status == CheckStatus.FAIL

    # Image with alt text
    img_alt = ImageModel("img2", 1, (10, 10, 100, 100), 200, 200, "RGB", has_alt=True, alt_text="Bar chart showing growth")
    doc_good = PDFDocumentModel(filepath="", filename="i.pdf", filesize=10, pdf_version="1.7", page_count=1, images=[img_alt])
    assert rule.evaluate(doc_good)[0].status == CheckStatus.PASS


def test_parent_tree_integrity_rule():
    from src.pdf_inspector.engine.pdf_ua.parent_tree_rules import ParentTreeIntegrityRule
    rule = ParentTreeIntegrityRule()

    # Case 1: Tagged but missing ParentTree
    tree = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    doc_no_pt = PDFDocumentModel(
        filepath="", filename="p.pdf", filesize=10, pdf_version="1.7", page_count=1,
        is_tagged=True, structure_tree=tree, has_parent_tree=False
    )
    assert any(r.status == CheckStatus.FAIL for r in rule.evaluate(doc_no_pt))

    # Case 2: Tagged with valid ParentTree
    doc_with_pt = PDFDocumentModel(
        filepath="", filename="p.pdf", filesize=10, pdf_version="1.7", page_count=1,
        is_tagged=True, structure_tree=tree, has_parent_tree=True, parent_tree_valid=True,
        parent_tree_entries_count=2
    )
    assert any(r.status == CheckStatus.PASS for r in rule.evaluate(doc_with_pt))


def test_artifact_in_structure_tree_rule():
    from src.pdf_inspector.engine.pdf_ua.artifact_rules import ArtifactInStructureTreeRule
    rule = ArtifactInStructureTreeRule()

    # Case 1: Artifact tag erroneously inside structure tree
    art_node = StructureNode("art1", "Artifact", "Artifact")
    tree_bad = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[art_node])
    doc_bad = PDFDocumentModel(
        filepath="", filename="a.pdf", filesize=10, pdf_version="1.7", page_count=1,
        is_tagged=True, structure_tree=tree_bad
    )
    assert any(r.status == CheckStatus.FAIL for r in rule.evaluate(doc_bad))

    # Case 2: Clean structure tree with no Artifact tags
    p_node = StructureNode("p1", "P", "P")
    tree_good = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[p_node])
    doc_good = PDFDocumentModel(
        filepath="", filename="a.pdf", filesize=10, pdf_version="1.7", page_count=1,
        is_tagged=True, structure_tree=tree_good
    )
    assert any(r.status == CheckStatus.PASS for r in rule.evaluate(doc_good))


def test_annotation_tagged_rule():
    from src.pdf_inspector.engine.pdf_ua.annotation_rules import AnnotationTaggedRule
    from src.pdf_inspector.core.models import AnnotationModel
    rule = AnnotationTaggedRule()

    # Case 1: Untagged link annotation
    ann_bad = AnnotationModel(id="ann1", page=1, subtype="Link", rect=(10, 10, 100, 30), is_tagged=False)
    doc_bad = PDFDocumentModel(
        filepath="", filename="ann.pdf", filesize=10, pdf_version="1.7", page_count=1,
        is_tagged=True, annotations=[ann_bad]
    )
    assert any(r.status == CheckStatus.FAIL for r in rule.evaluate(doc_bad))

    # Case 2: Tagged link annotation
    ann_good = AnnotationModel(id="ann2", page=1, subtype="Link", rect=(10, 10, 100, 30), is_tagged=True)
    doc_good = PDFDocumentModel(
        filepath="", filename="ann.pdf", filesize=10, pdf_version="1.7", page_count=1,
        is_tagged=True, annotations=[ann_good]
    )
    assert any(r.status == CheckStatus.PASS for r in rule.evaluate(doc_good))


def test_page_tab_order_rule():
    from src.pdf_inspector.engine.pdf_ua.annotation_rules import PageTabOrderRule
    from src.pdf_inspector.core.models import PageModel, AnnotationModel
    rule = PageTabOrderRule()

    # Case 1: Page with annotations but missing /Tabs /S -> FAIL
    p_bad = PageModel(page_number=1, width=612, height=792, tab_order_mode="Unspecified", annotations_count=2)
    doc_bad = PDFDocumentModel(
        filepath="", filename="tab.pdf", filesize=10, pdf_version="1.7", page_count=1,
        is_tagged=True, pages=[p_bad]
    )
    res_bad = rule.evaluate(doc_bad)
    assert any(r.status == CheckStatus.FAIL for r in res_bad)
    assert res_bad[0].page == 1

    # Case 2: Page with annotations having /Tabs /S -> PASS
    p_good = PageModel(page_number=1, width=612, height=792, tab_order_mode="S", annotations_count=2)
    doc_good = PDFDocumentModel(
        filepath="", filename="tab.pdf", filesize=10, pdf_version="1.7", page_count=1,
        is_tagged=True, pages=[p_good]
    )
    res_good = rule.evaluate(doc_good)
    assert any(r.status == CheckStatus.PASS for r in res_good)

    # Case 3: Page without annotations -> PASS
    p_no_annot = PageModel(page_number=1, width=612, height=792, tab_order_mode="Unspecified", annotations_count=0)
    doc_no_annot = PDFDocumentModel(
        filepath="", filename="tab.pdf", filesize=10, pdf_version="1.7", page_count=1,
        is_tagged=True, pages=[p_no_annot]
    )
    assert any(r.status == CheckStatus.PASS for r in rule.evaluate(doc_no_annot))


def test_metadata_completeness_rule():
    rule = MetadataCompletenessRule()

    # Missing Title
    doc_notitle = PDFDocumentModel(
        filepath="", filename="m.pdf", filesize=10, pdf_version="1.7", page_count=1,
        title=None
    )
    assert any(r.status == CheckStatus.FAIL and "Title" in r.message for r in rule.evaluate(doc_notitle))

    # Fully populated metadata with PDF/UA declaration
    doc_complete = PDFDocumentModel(
        filepath="", filename="m.pdf", filesize=10, pdf_version="1.7", page_count=1,
        title="Valid Accessibility Report", author="Audit Team", subject="Auditing",
        pdfua_identifier_present=True
    )
    assert any(r.status == CheckStatus.PASS for r in rule.evaluate(doc_complete))


def test_form_field_accessibility_rule():
    from src.pdf_inspector.engine.pdf_ua.form_rules import FormFieldAccessibilityRule
    from src.pdf_inspector.engine.pdf_ua import PDF_UA_RULES
    from src.pdf_inspector.core.models import FormFieldModel
    rule = FormFieldAccessibilityRule()

    # Verify FormFieldAccessibilityRule error check is completely removed from PDF_UA_RULES
    assert not any(isinstance(r, FormFieldAccessibilityRule) for r in PDF_UA_RULES)

    # Form field missing /TU tooltip produces no error
    f_bad = FormFieldModel(name="SignatureField", field_type="Sig", tooltip=None, page=1)
    doc_bad = PDFDocumentModel(filepath="", filename="form_bad.pdf", filesize=100, pdf_version="1.7", page_count=1, form_fields=[f_bad])
    res_bad = rule.evaluate(doc_bad)
    assert not any(r.status == CheckStatus.FAIL for r in res_bad)

    # Form field with valid /TU tooltip produces no error
    f_good = FormFieldModel(name="EmailField", field_type="Text", tooltip="Enter your email address", page=1)
    doc_good = PDFDocumentModel(filepath="", filename="form_good.pdf", filesize=100, pdf_version="1.7", page_count=1, form_fields=[f_good])
    res_good = rule.evaluate(doc_good)
    assert not any(r.status == CheckStatus.FAIL for r in res_good)

    # Document without form fields produces no error
    doc_empty = PDFDocumentModel(filepath="", filename="form_none.pdf", filesize=100, pdf_version="1.7", page_count=1, form_fields=[])
    res_empty = rule.evaluate(doc_empty)
    assert not any(r.status == CheckStatus.FAIL for r in res_empty)


def test_table_structure_headers_rule():
    from src.pdf_inspector.engine.pdf_ua.table_rules import TableStructureHeadersRule
    from src.pdf_inspector.core.models import TableModel
    rule = TableStructureHeadersRule()

    # Case 1: Table with header cells
    t_good = TableModel(id="tbl1", page=1, rows_count=3, cols_count=3, has_headers=True, header_cells_count=3, data_cells_count=6)
    doc_good = PDFDocumentModel(filepath="", filename="tbl_good.pdf", filesize=100, pdf_version="1.7", page_count=1, tables=[t_good])
    res_good = rule.evaluate(doc_good)
    assert any(r.status == CheckStatus.PASS and "header cell(s)" in r.message for r in res_good)

    # Case 2: Table without header cells
    t_bad = TableModel(id="tbl2", page=2, rows_count=3, cols_count=3, has_headers=False, header_cells_count=0, data_cells_count=9)
    doc_bad = PDFDocumentModel(filepath="", filename="tbl_bad.pdf", filesize=100, pdf_version="1.7", page_count=2, tables=[t_bad])
    res_bad = rule.evaluate(doc_bad)
    assert any(r.status == CheckStatus.FAIL and "no designated header" in r.message for r in res_bad)


def test_bookmark_structure_rule():
    from src.pdf_inspector.engine.pdf_ua.document_settings_rules import BookmarkStructureRule
    from src.pdf_inspector.core.models import BookmarkModel
    rule = BookmarkStructureRule()

    # Case 1: Document > 20 pages without bookmarks -> WARNING
    doc_long_nobookmarks = PDFDocumentModel(filepath="", filename="long.pdf", filesize=100, pdf_version="1.7", page_count=25, bookmarks=[])
    res_long = rule.evaluate(doc_long_nobookmarks)
    assert any(r.status == CheckStatus.WARNING for r in res_long)

    # Case 2: Document <= 20 pages without bookmarks -> PASS (informational)
    doc_short_nobookmarks = PDFDocumentModel(filepath="", filename="short.pdf", filesize=100, pdf_version="1.7", page_count=10, bookmarks=[])
    res_short = rule.evaluate(doc_short_nobookmarks)
    assert any(r.status == CheckStatus.PASS and "optional" in r.message for r in res_short)

    # Case 3: Document with bookmarks -> PASS
    b1 = BookmarkModel(title="Chapter 1", level=1, page=1)
    doc_with_bm = PDFDocumentModel(filepath="", filename="bm.pdf", filesize=100, pdf_version="1.7", page_count=30, bookmarks=[b1])
    res_bm = rule.evaluate(doc_with_bm)
    assert any(r.status == CheckStatus.PASS and "contains" in r.message for r in res_bm)


def test_list_structure_hierarchy_rule():
    from src.pdf_inspector.engine.pdf_ua.list_rules import ListStructureHierarchyRule
    from src.pdf_inspector.core.models import ListModel, StructureNode
    rule = ListStructureHierarchyRule()

    # Case 1: Valid list structure (L -> LI -> Lbl, LBody)
    l_good = ListModel(id="list1", page=1, items_count=3, is_valid_structure=True, has_labels=True)
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    doc_good = PDFDocumentModel(filepath="", filename="l_good.pdf", filesize=100, pdf_version="1.7", page_count=1, structure_tree=root, lists=[l_good])
    res_good = rule.evaluate(doc_good)
    assert any(r.status == CheckStatus.PASS and "conform" in r.message for r in res_good)

    # Case 2: Invalid list structure (direct non-LI child or invalid LI child)
    l_bad = ListModel(id="list2", page=2, items_count=2, is_valid_structure=False, has_labels=False)
    doc_bad = PDFDocumentModel(filepath="", filename="l_bad.pdf", filesize=100, pdf_version="1.7", page_count=2, structure_tree=root, lists=[l_bad])
    res_bad = rule.evaluate(doc_bad)
    assert any(r.status == CheckStatus.FAIL and "invalid structural hierarchy" in r.message for r in res_bad)

    # Case 3: No lists in document
    doc_none = PDFDocumentModel(filepath="", filename="l_none.pdf", filesize=100, pdf_version="1.7", page_count=1, lists=[])
    res_none = rule.evaluate(doc_none)
    assert any(r.status == CheckStatus.PASS and "No lists" in r.message for r in res_none)


def test_form_field_accessibility_duplicate_and_unnamed_counting():
    """Tests that FormFieldAccessibilityRule error check is completely removed and reports no error findings."""
    from src.pdf_inspector.engine.pdf_ua.form_rules import FormFieldAccessibilityRule
    from src.pdf_inspector.core.models import FormFieldModel
    rule = FormFieldAccessibilityRule()

    # Form fields produce no error findings
    f1 = FormFieldModel(name="UnnamedField", field_type="Text", tooltip=None, page=1)
    f2 = FormFieldModel(name="UnnamedField", field_type="Text", tooltip=None, page=2)
    f3 = FormFieldModel(name="ValidField", field_type="Text", tooltip="Valid description", page=3)

    doc = PDFDocumentModel(
        filepath="", filename="form.pdf", filesize=100, pdf_version="1.7",
        page_count=3, is_tagged=True, form_fields=[f1, f2, f3]
    )
    res = rule.evaluate(doc)
    fail_res = [r for r in res if r.status == CheckStatus.FAIL]
    assert len(fail_res) == 0


def test_form_field_structure_real_pdf(tmp_path):
    """Tests that FormFieldAccessibilityRule produces no error findings on real PDFs."""
    import os
    import pikepdf
    from src.pdf_inspector.engine.pdf_ua.form_rules import FormFieldAccessibilityRule
    from src.pdf_inspector.core.models import FormFieldModel
    rule = FormFieldAccessibilityRule()

    pdf_path_valid = str(tmp_path / "form_valid.pdf")
    pdf1 = pikepdf.new()
    page1 = pdf1.add_blank_page()
    w1 = pdf1.make_indirect(pikepdf.Dictionary({
        "/Type": pikepdf.Name("/Annot"),
        "/Subtype": pikepdf.Name("/Widget"),
        "/Rect": [100, 100, 200, 120],
        "/T": "EmailField",
        "/TU": "Enter email address",
        "/StructParent": 0
    }))
    page1.Annots = pdf1.make_indirect(pikepdf.Array([w1]))
    objr1 = pikepdf.Dictionary({"/Type": pikepdf.Name("/OBJR"), "/Obj": w1, "/Pg": page1.obj})
    form1 = pdf1.make_indirect(pikepdf.Dictionary({
        "/Type": pikepdf.Name("/StructElem"),
        "/S": pikepdf.Name("/Form"),
        "/Pg": page1.obj,
        "/K": pikepdf.Array([objr1])
    }))
    p1 = pdf1.make_indirect(pikepdf.Dictionary({
        "/Type": pikepdf.Name("/StructElem"),
        "/S": pikepdf.Name("/P"),
        "/Pg": page1.obj,
        "/ActualText": "Email: ",
        "/K": pikepdf.Array([form1])
    }))
    pdf1.Root.StructTreeRoot = pdf1.make_indirect(pikepdf.Dictionary({
        "/Type": pikepdf.Name("/StructTreeRoot"),
        "/K": pikepdf.Array([p1])
    }))
    pdf1.Root.MarkInfo = pikepdf.Dictionary({"/Marked": True})
    pdf1.save(pdf_path_valid)
    pdf1.close()

    f1 = FormFieldModel(name="EmailField", field_type="Text", tooltip="Enter email address", page=1)
    doc_real_valid = PDFDocumentModel(
        filepath=pdf_path_valid, filename="form_valid.pdf", filesize=os.path.getsize(pdf_path_valid),
        pdf_version="1.7", page_count=1, is_tagged=True, form_fields=[f1]
    )
    res_real_valid = rule.evaluate(doc_real_valid)
    assert not any(r.status == CheckStatus.FAIL for r in res_real_valid)


def test_figure_alt_text_decorative_filtering():
    """Tests that decorative figures marked as artifacts are skipped from missing alt text failures."""
    from src.pdf_inspector.engine.pdf_ua.alt_text_rules import FigureAlternativeTextRule
    rule = FigureAlternativeTextRule()

    # Decorative figure with /Placement /Background or /Artifact
    fig_dec = StructureNode(
        id="f1", tag="Figure", standard_tag="Figure", page=1,
        attributes={"Placement": "/Background"}, is_artifact=True
    )
    # Informative figure without alt
    fig_info = StructureNode(
        id="f2", tag="Figure", standard_tag="Figure", page=2,
        alt_text=None, actual_text=None
    )
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[fig_dec, fig_info])
    doc = PDFDocumentModel(
        filepath="", filename="fig.pdf", filesize=100, pdf_version="1.7",
        page_count=2, is_tagged=True, structure_tree=root
    )
    res = rule.evaluate(doc)
    fail_res = [r for r in res if r.status == CheckStatus.FAIL]
    assert len(fail_res) == 1
    assert fail_res[0].page == 2  # Only fig_info on page 2 failed


def test_figure_bounding_box_multi_page_spanned():
    """Tests that FigureBoundingBoxRule allows valid multi-page figures without requiring per-page BBoxes."""
    from src.pdf_inspector.engine.pdf_ua.structure_rules import FigureBoundingBoxRule
    rule = FigureBoundingBoxRule()

    # Multi-page figure spanning page 1 and page 2 without BBox (BBox is optional)
    fig_multi = StructureNode(
        id="f_multi", tag="Figure", standard_tag="Figure", page=1,
        pages_spanned=[1, 2], has_explicit_bbox=False
    )
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[fig_multi])
    doc = PDFDocumentModel(
        filepath="", filename="multi_fig.pdf", filesize=100, pdf_version="1.7",
        page_count=2, is_tagged=True, structure_tree=root
    )
    res = rule.evaluate(doc)
    assert all(r.status == CheckStatus.PASS for r in res)


def test_figure_bounding_box_comprehensive_matrix():
    """
    Comprehensive tests for FigureBoundingBoxRule:
    - Single-page figure with no BBox (PASS)
    - Single-page figure with valid 4-number BBox (PASS)
    - Single-page figure with problematic float BBox [197.75, 581.365, 424.672, 648.236] (PASS)
    - Single-page figure with integer BBox (PASS)
    - Single-page figure with pikepdf.Array / Decimal BBox (PASS)
    - Single-page figure with valid Alt and no BBox (PASS)
    - Single-page figure with valid ActualText and no BBox (PASS)
    - Single-page figure with malformed BBox + valid Alt (FAIL PDFUA-FIG-001)
    - Single-page figure with fewer than 4 numbers (FAIL)
    - Single-page figure with more than 4 numbers (FAIL)
    - Single-page figure with non-numeric values (FAIL)
    - Multi-page figure with page-specific BBoxes for all pages (PASS)
    - Multi-page figure with only 1 BBox spanning 2 pages (FAIL)
    """
    import decimal
    import pikepdf
    from src.pdf_inspector.engine.pdf_ua.structure_rules import FigureBoundingBoxRule
    rule = FigureBoundingBoxRule()

    # 1. Single-page figure with no BBox (PASS - BBox is optional on single page)
    f1 = StructureNode("f1", "Figure", "Figure", page=1, pages_spanned=[1])
    doc1 = PDFDocumentModel(filepath="", filename="f1.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[f1]))
    assert all(r.status == CheckStatus.PASS for r in rule.evaluate(doc1))

    # 2. Single-page figure with valid float BBox (PASS)
    f2 = StructureNode("f2", "Figure", "Figure", page=1, pages_spanned=[1], attributes={"BBox": [197.75, 581.365, 424.672, 648.236]})
    doc2 = PDFDocumentModel(filepath="", filename="f2.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[f2]))
    assert all(r.status == CheckStatus.PASS for r in rule.evaluate(doc2))

    # 3. Single-page figure with integer BBox (PASS)
    f3 = StructureNode("f3", "Figure", "Figure", page=1, pages_spanned=[1], attributes={"BBox": [0, 0, 500, 300]})
    doc3 = PDFDocumentModel(filepath="", filename="f3.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[f3]))
    assert all(r.status == CheckStatus.PASS for r in rule.evaluate(doc3))

    # 4. Single-page figure with pikepdf Array / Decimal BBox (PASS)
    pike_arr = pikepdf.Array([decimal.Decimal("197.75"), decimal.Decimal("581.365"), decimal.Decimal("424.672"), decimal.Decimal("648.236")])
    f4 = StructureNode("f4", "Figure", "Figure", page=1, pages_spanned=[1], attributes={"BBox": pike_arr})
    doc4 = PDFDocumentModel(filepath="", filename="f4.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[f4]))
    assert all(r.status == CheckStatus.PASS for r in rule.evaluate(doc4))

    # 5. Single-page figure with valid Alt and no BBox (PASS BBox validation)
    f5 = StructureNode("f5", "Figure", "Figure", page=1, pages_spanned=[1], alt_text="Sales chart for 2024")
    doc5 = PDFDocumentModel(filepath="", filename="f5.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[f5]))
    assert all(r.status == CheckStatus.PASS for r in rule.evaluate(doc5))

    # 6. Single-page figure with valid ActualText and no BBox (PASS BBox validation)
    f6 = StructureNode("f6", "Figure", "Figure", page=1, pages_spanned=[1], actual_text="Quarterly revenue diagram")
    doc6 = PDFDocumentModel(filepath="", filename="f6.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[f6]))
    assert all(r.status == CheckStatus.PASS for r in rule.evaluate(doc6))

    # 7. Single-page figure with malformed BBox (2 numbers) + valid Alt (FAIL PDFUA-FIG-001)
    f7 = StructureNode("f7", "Figure", "Figure", page=1, pages_spanned=[1], alt_text="Company logo", attributes={"BBox": [50.0, 100.0]})
    doc7 = PDFDocumentModel(filepath="", filename="f7.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[f7]))
    res7 = rule.evaluate(doc7)
    assert any(r.status == CheckStatus.FAIL and "invalid /BBox" in r.message for r in res7)

    # 8. Single-page figure with 5 numbers in BBox (FAIL)
    f8 = StructureNode("f8", "Figure", "Figure", page=1, pages_spanned=[1], attributes={"BBox": [1.0, 2.0, 3.0, 4.0, 5.0]})
    doc8 = PDFDocumentModel(filepath="", filename="f8.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[f8]))
    res8 = rule.evaluate(doc8)
    assert any(r.status == CheckStatus.FAIL and "invalid /BBox" in r.message for r in res8)

    # 9. Single-page figure with non-numeric BBox (FAIL)
    f9 = StructureNode("f9", "Figure", "Figure", page=1, pages_spanned=[1], attributes={"BBox": ["a", "b", "c", "d"]})
    doc9 = PDFDocumentModel(filepath="", filename="f9.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[f9]))
    res9 = rule.evaluate(doc9)
    assert any(r.status == CheckStatus.FAIL and "invalid /BBox" in r.message for r in res9)

    # 10. Multi-page figure with page-specific BBoxes on child figures covering all spanned pages (PASS)
    c_p1 = StructureNode("c_p1", "Figure", "Figure", page=1, pages_spanned=[1], attributes={"BBox": [10.0, 20.0, 100.0, 200.0]})
    c_p2 = StructureNode("c_p2", "Figure", "Figure", page=2, pages_spanned=[2], attributes={"BBox": [15.0, 25.0, 105.0, 205.0]})
    f10 = StructureNode("f10", "Figure", "Figure", page=1, pages_spanned=[1, 2], children=[c_p1, c_p2])
    doc10 = PDFDocumentModel(filepath="", filename="f10.pdf", filesize=100, pdf_version="1.7", page_count=2, is_tagged=True, structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[f10]))
    assert all(r.status == CheckStatus.PASS for r in rule.evaluate(doc10))

    # 11. Multi-page figure spanning pages 1 and 2 with valid BBox (PASS)
    f11 = StructureNode("f11", "Figure", "Figure", page=1, pages_spanned=[1, 2], attributes={"BBox": [10.0, 20.0, 100.0, 200.0]})
    doc11 = PDFDocumentModel(filepath="", filename="f11.pdf", filesize=100, pdf_version="1.7", page_count=2, is_tagged=True, structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[f11]))
    res11 = rule.evaluate(doc11)
    assert all(r.status == CheckStatus.PASS for r in res11)


def test_unicode_pua_rule_synthetic():
    """Verify standards-compliant evaluation of Unicode Private Use Area characters."""
    from src.pdf_inspector.engine.pdf_ua.unicode_rules import UnicodePUARule
    from src.pdf_inspector.core.models import ArtifactOccurrenceModel
    rule = UnicodePUARule()

    # Case 1: Unexempt PUA in regular P node without ActualText -> WARNING
    p_bad = StructureNode("p1", "P", "P", page=1, text_content="Custom icon \uE001 in paragraph")
    root1 = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[p_bad])
    p_bad.parent = root1
    doc1 = PDFDocumentModel(filepath="", filename="pua1.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=root1)
    res1 = rule.evaluate(doc1)
    assert len(res1) == 1
    assert res1[0].status == CheckStatus.WARNING
    assert "0xe001" in res1[0].message

    # Case 2: PUA inside Formula element -> PASS (ISO 14289-1 Clause 7.2 & 7.5 math exception)
    formula_node = StructureNode("form1", "Formula", "Formula", page=1, text_content="E = mc\uF8FF")
    root2 = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[formula_node])
    formula_node.parent = root2
    doc2 = PDFDocumentModel(filepath="", filename="pua2.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=root2)
    res2 = rule.evaluate(doc2)
    assert all(r.status == CheckStatus.PASS for r in res2)

    # Case 3: PUA with ActualText directly on node -> PASS
    p_actual = StructureNode("p2", "Span", "Span", page=1, text_content="\uE002", actual_text="Star Rating")
    root3 = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[p_actual])
    p_actual.parent = root3
    doc3 = PDFDocumentModel(filepath="", filename="pua3.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=root3)
    res3 = rule.evaluate(doc3)
    assert all(r.status == CheckStatus.PASS for r in res3)

    # Case 4: PUA with ActualText on parent node -> PASS
    parent_actual = StructureNode("p_par", "P", "P", page=1, actual_text="Checkmark List Item")
    child_pua = StructureNode("span1", "Span", "Span", page=1, text_content="\uE005")
    parent_actual.children.append(child_pua)
    child_pua.parent = parent_actual
    root4 = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[parent_actual])
    parent_actual.parent = root4
    doc4 = PDFDocumentModel(filepath="", filename="pua4.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=root4)
    res4 = rule.evaluate(doc4)
    assert all(r.status == CheckStatus.PASS for r in res4)

    # Case 5: PUA marked as Artifact -> PASS
    art_node = StructureNode("art1", "Span", "Span", page=1, text_content="\uE010", is_artifact=True)
    root5 = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[art_node])
    art_node.parent = root5
    doc5 = PDFDocumentModel(filepath="", filename="pua5.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=root5)
    res5 = rule.evaluate(doc5)
    assert all(r.status == CheckStatus.PASS for r in res5)

    # Case 6: Untagged document with PUA covered by Artifact -> PASS
    art1 = ArtifactOccurrenceModel(page_number=1, is_inside_tagged=False, text_snippet="\uE008")
    pg1 = PageModel(page_number=1, width=612, height=792, text="Bullet \uE008 item", artifacts=[art1])
    doc6 = PDFDocumentModel(filepath="", filename="pua6.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=False, structure_tree=None, pages=[pg1])
    res6 = rule.evaluate(doc6)
    assert all(r.status == CheckStatus.PASS for r in res6)

    # Case 7: Untagged document with PUA NOT covered by Artifact -> WARNING
    pg2 = PageModel(page_number=1, width=612, height=792, text="Uncovered \uE009 item")
    doc7 = PDFDocumentModel(filepath="", filename="pua7.pdf", filesize=100, pdf_version="1.7", page_count=1, is_tagged=False, structure_tree=None, pages=[pg2])
    res7 = rule.evaluate(doc7)
    assert any(r.status == CheckStatus.WARNING and "0xe009" in r.message for r in res7)
