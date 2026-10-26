"""
Unit tests for new Quality Rules:
- QUAL-BOUND-001 (TaggedContentPageBoundariesRule)
- QUAL-TOC-001 (TOCIContainsLinkRule)
- QUAL-TOC-002 (TOCILinkDestinationRule)
- QUAL-TEXT-001 (TextElementAltTextQualityRule)
- QUAL-NOTE-001 (NoteReferencedQualityRule)
- QUAL-NOTE-002 (NoteContainsLabelQualityRule)
- QUAL-NOTE-003 (ParagraphContainsNoteQualityRule)
"""

import pytest
from src.pdf_inspector.core.models import (
    PDFDocumentModel, PageModel, StructureNode, CheckStatus, Severity, LinkModel, TableModel, ArtifactOccurrenceModel
)
from src.pdf_inspector.engine.quality.quality_rules import (
    TaggedContentPageBoundariesRule,
    TOCIContainsLinkRule,
    TOCILinkDestinationRule,
    TextElementAltTextQualityRule,
    NoteReferencedQualityRule,
    NoteContainsLabelQualityRule,
    ParagraphContainsNoteQualityRule,
    HeadingHierarchyQualityRule,
    TableRegularityQualityRule,
    ArtifactedContentOnPageBodyRule,
    LinkCompletenessQualityRule,
    DocumentTitleQualityRule,
    BookmarksIfHeadingsQualityRule,
    ListItemStructureQualityRule,
    AlternativeTextValidityQualityRule,
)


def test_tagged_content_page_boundaries_pass():
    page = PageModel(
        page_number=1,
        width=612.0,
        height=792.0,
        mcid_bboxes={
            0: (50.0, 50.0, 200.0, 100.0),
            1: (100.0, 150.0, 400.0, 300.0)
        }
    )
    doc = PDFDocumentModel(
        filepath="sample.pdf",
        filename="sample.pdf",
        filesize=1000,
        pdf_version="1.7",
        page_count=1,
        is_tagged=True,
        pages=[page]
    )

    rule = TaggedContentPageBoundariesRule()
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS


def test_tagged_content_page_boundaries_fail():
    page = PageModel(
        page_number=1,
        width=612.0,
        height=792.0,
        mcid_bboxes={
            0: (50.0, 50.0, 200.0, 100.0),
            1: (700.0, 850.0, 800.0, 900.0)  # Strictly outside page
        },
        mcid_texts={1: "Off-screen text"}
    )
    doc = PDFDocumentModel(
        filepath="sample.pdf",
        filename="sample.pdf",
        filesize=1000,
        pdf_version="1.7",
        page_count=1,
        is_tagged=True,
        pages=[page]
    )

    rule = TaggedContentPageBoundariesRule()
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.WARNING
    assert "MCID 1" in results[0].message


def test_toci_contains_link_rule():
    rule = TOCIContainsLinkRule()

    # Case 1: No TOCI -> []
    root_no_toci = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot")
    doc_no_toci = PDFDocumentModel(
        filepath="sample.pdf", filename="sample.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_no_toci
    )
    assert rule.evaluate(doc_no_toci) == []

    # Case 2: TOCI without Link -> FAIL
    toci_no_link = StructureNode(id="toci1", tag="TOCI", standard_tag="TOCI", page=1)
    root_no_link = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[toci_no_link])
    doc_no_link = PDFDocumentModel(
        filepath="sample.pdf", filename="sample.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_no_link
    )
    res_no_link = rule.evaluate(doc_no_link)
    assert len(res_no_link) == 1
    assert res_no_link[0].status == CheckStatus.FAIL

    # Case 3: TOCI with Link -> PASS
    link_child = StructureNode(id="lnk1", tag="Link", standard_tag="Link", page=1)
    toci_valid = StructureNode(id="toci1", tag="TOCI", standard_tag="TOCI", page=1, children=[link_child])
    root_valid = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[toci_valid])
    doc_valid = PDFDocumentModel(
        filepath="sample.pdf", filename="sample.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_valid
    )
    res_valid = rule.evaluate(doc_valid)
    assert len(res_valid) == 1
    assert res_valid[0].status == CheckStatus.PASS


def test_toci_link_destination_rule():
    rule = TOCILinkDestinationRule()

    # Case 1: TOCI with link having destination -> PASS
    link_child = StructureNode(id="lnk1", tag="Link", standard_tag="Link", page=1, attributes={"Dest": "Chapter1"})
    toci = StructureNode(id="toci1", tag="TOCI", standard_tag="TOCI", page=1, children=[link_child])
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[toci])
    doc = PDFDocumentModel(
        filepath="sample.pdf", filename="sample.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS


def test_text_element_alt_text_rule():
    rule = TextElementAltTextQualityRule()

    # Case 1: Normal text elements without Alt -> PASS
    p_node = StructureNode(id="p1", tag="P", standard_tag="P", text_content="Normal paragraph text")
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[p_node])
    doc = PDFDocumentModel(
        filepath="sample.pdf", filename="sample.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    res = rule.evaluate(doc)
    assert len(res) == 1
    assert res[0].status == CheckStatus.PASS

    # Case 2: Text element with inappropriate Alt masking text -> WARNING
    p_bad = StructureNode(id="p2", tag="P", standard_tag="P", text_content="Real text content", alt_text="Masking alt text")
    root_bad = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[p_bad])
    doc_bad = PDFDocumentModel(
        filepath="sample.pdf", filename="sample.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_bad
    )
    res_bad = rule.evaluate(doc_bad)
    assert len(res_bad) == 1
    assert res_bad[0].status == CheckStatus.WARNING


def test_note_referenced_quality_rule():
    rule = NoteReferencedQualityRule()

    # Case 1: No notes -> []
    root_empty = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot")
    doc_empty = PDFDocumentModel(
        filepath="sample.pdf", filename="sample.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_empty
    )
    assert rule.evaluate(doc_empty) == []

    # Case 2: Note without Reference -> WARNING
    note = StructureNode(id="note1", tag="Note", standard_tag="Note", page=1)
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[note])
    doc = PDFDocumentModel(
        filepath="sample.pdf", filename="sample.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    res = rule.evaluate(doc)
    assert len(res) == 1
    assert res[0].status == CheckStatus.WARNING

    # Case 3: Note with Reference -> PASS
    ref = StructureNode(id="ref1", tag="Reference", standard_tag="Reference", page=1, attributes={"Ref": "note1"})
    root_with_ref = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[ref, note])
    doc_with_ref = PDFDocumentModel(
        filepath="sample.pdf", filename="sample.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_with_ref
    )
    res_pass = rule.evaluate(doc_with_ref)
    assert len(res_pass) == 1
    assert res_pass[0].status == CheckStatus.PASS


def test_note_contains_label_quality_rule():
    rule = NoteContainsLabelQualityRule()

    # Case 1: Note without Lbl -> WARNING
    note_no_lbl = StructureNode(id="note1", tag="Note", standard_tag="Note", page=1)
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[note_no_lbl])
    doc = PDFDocumentModel(
        filepath="sample.pdf", filename="sample.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    res = rule.evaluate(doc)
    assert len(res) == 1
    assert res[0].status == CheckStatus.WARNING

    # Case 2: Note with Lbl -> PASS
    lbl = StructureNode(id="lbl1", tag="Lbl", standard_tag="Lbl", page=1, text_content="1")
    note_with_lbl = StructureNode(id="note1", tag="Note", standard_tag="Note", page=1, children=[lbl])
    root_lbl = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[note_with_lbl])
    doc_lbl = PDFDocumentModel(
        filepath="sample.pdf", filename="sample.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_lbl
    )
    res_lbl = rule.evaluate(doc_lbl)
    assert len(res_lbl) == 1
    assert res_lbl[0].status == CheckStatus.PASS


def test_paragraph_contains_note_quality_rule():
    rule = ParagraphContainsNoteQualityRule()

    # Case 1: Note inside P -> WARNING
    note = StructureNode(id="note1", tag="Note", standard_tag="Note", page=1)
    p_node = StructureNode(id="p1", tag="P", standard_tag="P", page=1, children=[note])
    root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[p_node])
    doc = PDFDocumentModel(
        filepath="sample.pdf", filename="sample.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    res = rule.evaluate(doc)
    assert len(res) == 1
    assert res[0].status == CheckStatus.WARNING

    # Case 2: Note outside P -> PASS
    p_sibling = StructureNode(id="p2", tag="P", standard_tag="P", page=1)
    root_pass = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[p_sibling, note])
    doc_pass = PDFDocumentModel(
        filepath="sample.pdf", filename="sample.pdf", filesize=1000, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_pass
    )
    res_pass = rule.evaluate(doc_pass)
    assert len(res_pass) == 1
    assert res_pass[0].status == CheckStatus.PASS


def test_heading_hierarchy_quality_rule():
    rule = HeadingHierarchyQualityRule()

    # Case 1: Valid hierarchy (H1 -> H2 -> H3) -> PASS only
    h1 = StructureNode(id="h1", tag="H1", standard_tag="H1", page=1)
    h2 = StructureNode(id="h2", tag="H2", standard_tag="H2", page=1)
    h3 = StructureNode(id="h3", tag="H3", standard_tag="H3", page=2)
    root_valid = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[h1, h2, h3])
    doc_valid = PDFDocumentModel(filepath="", filename="h.pdf", filesize=10, pdf_version="1.7", page_count=2, is_tagged=True, structure_tree=root_valid)
    res_valid = rule.evaluate(doc_valid)
    assert len(res_valid) == 1
    assert res_valid[0].status == CheckStatus.PASS
    assert res_valid[0].items_count == 1

    # Case 2: First heading is H2 (starts with non-H1) -> WARNING only, no dual PASS
    root_bad_start = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[h2, h3])
    doc_bad_start = PDFDocumentModel(filepath="", filename="h.pdf", filesize=10, pdf_version="1.7", page_count=2, is_tagged=True, structure_tree=root_bad_start)
    res_bad_start = rule.evaluate(doc_bad_start)
    assert len(res_bad_start) == 1
    assert res_bad_start[0].status == CheckStatus.WARNING
    assert "instead of <H1>" in res_bad_start[0].message
    assert not any(r.status == CheckStatus.PASS for r in res_bad_start)

    # Case 3: Skipped jump (H1 -> H3) -> WARNING only, no dual PASS
    root_skip = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[h1, h3])
    doc_skip = PDFDocumentModel(filepath="", filename="h.pdf", filesize=10, pdf_version="1.7", page_count=2, is_tagged=True, structure_tree=root_skip)
    res_skip = rule.evaluate(doc_skip)
    assert len(res_skip) == 1
    assert res_skip[0].status == CheckStatus.WARNING
    assert "Heading level skipped" in res_skip[0].message
    assert not any(r.status == CheckStatus.PASS for r in res_skip)

    # Case 4: No headings in document -> WARNING
    root_none = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[])
    doc_none = PDFDocumentModel(filepath="", filename="h.pdf", filesize=10, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=root_none)
    res_none = rule.evaluate(doc_none)
    assert len(res_none) == 1
    assert res_none[0].status == CheckStatus.WARNING


def test_table_regularity_quality_rule():
    rule = TableRegularityQualityRule()

    # Case 1: No tables -> []
    doc_notables = PDFDocumentModel(filepath="", filename="t.pdf", filesize=10, pdf_version="1.7", page_count=1, tables=[])
    assert rule.evaluate(doc_notables) == []

    # Case 2: All regular tables -> PASS
    t1 = TableModel(id="tbl1", page=1, rows_count=3, cols_count=3, has_headers=True, header_cells_count=3, data_cells_count=6, is_regular=True, bbox=(0, 0, 100, 100))
    t2 = TableModel(id="tbl2", page=2, rows_count=2, cols_count=2, has_headers=True, header_cells_count=2, data_cells_count=2, is_regular=True, bbox=(0, 0, 100, 100))
    doc_all_regular = PDFDocumentModel(filepath="", filename="t.pdf", filesize=10, pdf_version="1.7", page_count=2, tables=[t1, t2])
    res_reg = rule.evaluate(doc_all_regular)
    assert len(res_reg) == 1
    assert res_reg[0].status == CheckStatus.PASS
    assert res_reg[0].items_count == 2

    # Case 3: Mixed complete and incomplete tables -> WARNING for incomplete, PASS for complete
    t_irreg = TableModel(id="tbl3", page=3, rows_count=0, cols_count=0, has_headers=False, header_cells_count=0, data_cells_count=0, is_regular=False, bbox=(0, 0, 100, 100))
    doc_mixed = PDFDocumentModel(filepath="", filename="t.pdf", filesize=10, pdf_version="1.7", page_count=3, tables=[t1, t_irreg])
    res_mixed = rule.evaluate(doc_mixed)
    assert len(res_mixed) == 2
    warns = [r for r in res_mixed if r.status == CheckStatus.WARNING]
    passes = [r for r in res_mixed if r.status == CheckStatus.PASS]
    assert len(warns) == 1
    assert len(passes) == 1
    assert passes[0].items_count == 1


def test_artifacted_content_on_page_body_rule():
    rule = ArtifactedContentOnPageBodyRule()

    # Case 1: No artifacts -> []
    p0 = PageModel(page_number=1, width=612, height=792, artifacts=[])
    doc_noart = PDFDocumentModel(filepath="", filename="a.pdf", filesize=10, pdf_version="1.7", page_count=1, pages=[p0])
    assert rule.evaluate(doc_noart) == []

    # Case 2: Strictly pagination artifact -> valid, returns [] (PAC displays '-')
    art_page = ArtifactOccurrenceModel(page_number=1, is_inside_tagged=False, text_snippet="Page 1 of 5")
    p1 = PageModel(page_number=1, width=612, height=792, artifacts=[art_page])
    doc_pag = PDFDocumentModel(filepath="", filename="a.pdf", filesize=10, pdf_version="1.7", page_count=1, pages=[p1])
    res_pag = rule.evaluate(doc_pag)
    assert res_pag == []

    # Case 3: Readable body text artifact -> WARNING
    art_body = ArtifactOccurrenceModel(page_number=1, is_inside_tagged=False, text_snippet="Important substantive text in body")
    p2 = PageModel(page_number=1, width=612, height=792, artifacts=[art_body])
    doc_body = PDFDocumentModel(filepath="", filename="a.pdf", filesize=10, pdf_version="1.7", page_count=1, pages=[p2])
    res_body = rule.evaluate(doc_body)
    assert len(res_body) == 1
    assert res_body[0].status == CheckStatus.WARNING
    assert res_body[0].items_count == 1


def test_link_completeness_quality_rule():
    rule = LinkCompletenessQualityRule()

    # Case 1: No links -> []
    root_empty = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot")
    doc_nolinks = PDFDocumentModel(filepath="", filename="l.pdf", filesize=10, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=root_empty)
    assert rule.evaluate(doc_nolinks) == []

    # Case 2: Complete link with text -> PASS with items_count=1
    lnk_good = StructureNode(id="lnk1", tag="Link", standard_tag="Link", page=1, text_content="Visit Website")
    root_good = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[lnk_good])
    doc_good = PDFDocumentModel(filepath="", filename="l.pdf", filesize=10, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=root_good)
    res_good = rule.evaluate(doc_good)
    assert len(res_good) == 1
    assert res_good[0].status == CheckStatus.PASS
    assert res_good[0].items_count == 1

    # Case 3: Incomplete empty link -> WARNING with items_count=1 (matching PAC quality checks)
    lnk_bad = StructureNode(id="lnk2", tag="Link", standard_tag="Link", page=1, text_content="")
    root_bad = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[lnk_bad])
    doc_bad = PDFDocumentModel(filepath="", filename="l.pdf", filesize=10, pdf_version="1.7", page_count=1, is_tagged=True, structure_tree=root_bad)
    res_bad = rule.evaluate(doc_bad)
    assert len(res_bad) == 1
    assert res_bad[0].status == CheckStatus.WARNING
    assert res_bad[0].items_count == 1


def test_document_title_quality_rule():
    rule = DocumentTitleQualityRule()

    # Case 1: Valid title + DisplayDocTitle True -> PASS (1)
    doc_valid = PDFDocumentModel(
        filepath="", filename="report.pdf", filesize=10, pdf_version="1.7",
        page_count=1, title="Quarterly Financial Report", display_doc_title=True
    )
    res_valid = rule.evaluate(doc_valid)
    assert len(res_valid) == 1
    assert res_valid[0].status == CheckStatus.PASS
    assert res_valid[0].items_count == 1

    # Case 2: Missing title -> FAIL (1)
    doc_notitle = PDFDocumentModel(
        filepath="", filename="report.pdf", filesize=10, pdf_version="1.7",
        page_count=1, title="", display_doc_title=True
    )
    res_notitle = rule.evaluate(doc_notitle)
    assert len(res_notitle) == 1
    assert res_notitle[0].status == CheckStatus.FAIL
    assert "missing" in res_notitle[0].message.lower()

    # Case 3: Title matches filename -> FAIL (1)
    doc_fn = PDFDocumentModel(
        filepath="", filename="report.pdf", filesize=10, pdf_version="1.7",
        page_count=1, title="report.pdf", display_doc_title=True
    )
    res_fn = rule.evaluate(doc_fn)
    assert len(res_fn) == 1
    assert res_fn[0].status == CheckStatus.FAIL
    assert "matches the filename" in res_fn[0].message

    # Case 4: Title valid but DisplayDocTitle False -> FAIL (1)
    doc_nodisp = PDFDocumentModel(
        filepath="", filename="report.pdf", filesize=10, pdf_version="1.7",
        page_count=1, title="Quarterly Financial Report", display_doc_title=False
    )
    res_nodisp = rule.evaluate(doc_nodisp)
    assert len(res_nodisp) == 1
    assert res_nodisp[0].status == CheckStatus.FAIL
    assert "DisplayDocTitle is false" in res_nodisp[0].message


def test_bookmarks_if_headings_quality_rule():
    rule = BookmarksIfHeadingsQualityRule()

    # Case 1: No headings in document -> [] (displays '-' in PAC)
    root_no_h = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot")
    doc_no_h = PDFDocumentModel(
        filepath="", filename="d.pdf", filesize=10, pdf_version="1.7",
        page_count=2, is_tagged=True, structure_tree=root_no_h
    )
    assert rule.evaluate(doc_no_h) == []

    # Case 2: Headings exist AND bookmarks exist -> PASS (1)
    h1 = StructureNode(id="h1", tag="H1", standard_tag="H1", page=1)
    root_with_h = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[h1])
    doc_with_bm = PDFDocumentModel(
        filepath="", filename="d.pdf", filesize=10, pdf_version="1.7",
        page_count=2, is_tagged=True, structure_tree=root_with_h, bookmarks=[{"title": "Section 1", "page": 1}]
    )
    res_bm = rule.evaluate(doc_with_bm)
    assert len(res_bm) == 1
    assert res_bm[0].status == CheckStatus.PASS
    assert res_bm[0].items_count == 1

    # Case 3: Headings exist BUT NO bookmarks -> WARNING (1)
    doc_no_bm = PDFDocumentModel(
        filepath="", filename="d.pdf", filesize=10, pdf_version="1.7",
        page_count=2, is_tagged=True, structure_tree=root_with_h, bookmarks=[]
    )
    res_no_bm = rule.evaluate(doc_no_bm)
    assert len(res_no_bm) == 1
    assert res_no_bm[0].status == CheckStatus.WARNING
    assert res_no_bm[0].items_count == 1


def test_list_item_structure_quality_rule():
    rule = ListItemStructureQualityRule()

    # Case 1: No list items in document -> [] (displays '-' in PAC)
    root_empty = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot")
    doc_empty = PDFDocumentModel(
        filepath="", filename="d.pdf", filesize=10, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_empty
    )
    assert rule.evaluate(doc_empty) == []

    # Case 2: All valid LI elements (LI contains Lbl and LBody) -> PASS (count=2)
    lbl1 = StructureNode(id="lbl1", tag="Lbl", standard_tag="Lbl")
    lbody1 = StructureNode(id="lb1", tag="LBody", standard_tag="LBody")
    li1 = StructureNode(id="li1", tag="LI", standard_tag="LI", children=[lbl1, lbody1])

    lbl2 = StructureNode(id="lbl2", tag="Lbl", standard_tag="Lbl")
    lbody2 = StructureNode(id="lb2", tag="LBody", standard_tag="LBody")
    li2 = StructureNode(id="li2", tag="LI", standard_tag="LI", children=[lbl2, lbody2])

    l_node = StructureNode(id="l1", tag="L", standard_tag="L", children=[li1, li2])
    root_valid = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[l_node])
    doc_valid = PDFDocumentModel(
        filepath="", filename="d.pdf", filesize=10, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_valid
    )
    res_valid = rule.evaluate(doc_valid)
    assert len(res_valid) == 1
    assert res_valid[0].status == CheckStatus.PASS
    assert res_valid[0].items_count == 2

    # Case 3: Invalid LI element (contains direct Span without LBody) -> FAIL
    span_bad = StructureNode(id="s1", tag="Span", standard_tag="Span", text_content="bad")
    li_bad = StructureNode(id="li3", tag="LI", standard_tag="LI", children=[span_bad])
    l_mixed = StructureNode(id="l2", tag="L", standard_tag="L", children=[li1, li_bad])
    root_mixed = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[l_mixed])
    doc_mixed = PDFDocumentModel(
        filepath="", filename="d.pdf", filesize=10, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_mixed
    )
    res_mixed = rule.evaluate(doc_mixed)
    fails = [r for r in res_mixed if r.status == CheckStatus.FAIL]
    passes = [r for r in res_mixed if r.status == CheckStatus.PASS]
    assert len(fails) == 1
    assert fails[0].items_count == 1
    assert len(passes) == 1
    assert passes[0].items_count == 1


def test_alternative_text_validity_quality_rule():
    rule = AlternativeTextValidityQualityRule()

    # Case 1: Empty document with no graphics -> [] (renders as '-' in PAC)
    root_empty = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot")
    doc_empty = PDFDocumentModel(
        filepath="", filename="d.pdf", filesize=10, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_empty
    )
    assert rule.evaluate(doc_empty) == []

    # Case 2: Figure without any alt text attribute (alt_text=None) -> []
    fig_no_alt = StructureNode(id="fig1", tag="Figure", standard_tag="Figure", page=1)
    root_no_alt = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[fig_no_alt])
    doc_no_alt = PDFDocumentModel(
        filepath="", filename="d.pdf", filesize=10, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_no_alt
    )
    assert rule.evaluate(doc_no_alt) == []

    # Case 3: Figure with valid descriptive alt text -> PASS (count=1)
    fig_valid = StructureNode(
        id="fig2", tag="Figure", standard_tag="Figure", page=1,
        alt_text="Quarterly sales bar chart comparing Q1 through Q4 revenue",
        bbox=(50.0, 50.0, 200.0, 200.0)
    )
    root_valid = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[fig_valid])
    doc_valid = PDFDocumentModel(
        filepath="", filename="d.pdf", filesize=10, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_valid
    )
    res_valid = rule.evaluate(doc_valid)
    assert len(res_valid) == 1
    assert res_valid[0].status == CheckStatus.PASS
    assert res_valid[0].items_count == 1

    # Case 4: Figure with filename as alt text -> WARNING
    fig_file = StructureNode(
        id="fig3", tag="Figure", standard_tag="Figure", page=1,
        alt_text="sales_chart_final.png",
        bbox=(50.0, 50.0, 200.0, 200.0)
    )
    root_file = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[fig_file])
    doc_file = PDFDocumentModel(
        filepath="", filename="d.pdf", filesize=10, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_file
    )
    res_file = rule.evaluate(doc_file)
    assert len(res_file) == 1
    assert res_file[0].status == CheckStatus.WARNING
    assert "file name" in res_file[0].message

    # Case 5: Figure with generic placeholder alt text -> WARNING
    fig_ph = StructureNode(
        id="fig4", tag="Figure", standard_tag="Figure", page=1,
        alt_text="photo",
        bbox=(50.0, 50.0, 200.0, 200.0)
    )
    root_ph = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[fig_ph])
    doc_ph = PDFDocumentModel(
        filepath="", filename="d.pdf", filesize=10, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_ph
    )
    res_ph = rule.evaluate(doc_ph)
    assert len(res_ph) == 1
    assert res_ph[0].status == CheckStatus.WARNING
    assert "placeholder" in res_ph[0].message

    # Case 6: Figure with pure whitespace alt text -> WARNING
    fig_white = StructureNode(
        id="fig5", tag="Figure", standard_tag="Figure", page=1,
        alt_text="   \t   ",
        bbox=(50.0, 50.0, 200.0, 200.0)
    )
    root_white = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[fig_white])
    doc_white = PDFDocumentModel(
        filepath="", filename="d.pdf", filesize=10, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_white
    )
    res_white = rule.evaluate(doc_white)
    assert len(res_white) == 1
    assert res_white[0].status == CheckStatus.WARNING
    assert "whitespace" in res_white[0].message

    # Case 7: Decorative figure is ignored
    fig_deco = StructureNode(
        id="fig6", tag="Figure", standard_tag="Figure", page=1,
        alt_text="",
        actual_text=""
    )
    # If standard_tag is Artifact or tag is Artifact
    fig_deco.standard_tag = "Artifact"
    root_deco = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[fig_deco])
    doc_deco = PDFDocumentModel(
        filepath="", filename="d.pdf", filesize=10, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_deco
    )
    assert rule.evaluate(doc_deco) == []

    # Case 8: Mixed document with valid and invalid items produces accurate pass/warn counts
    root_mixed = StructureNode(
        id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot",
        children=[fig_valid, fig_file, fig_ph]
    )
    doc_mixed = PDFDocumentModel(
        filepath="", filename="d.pdf", filesize=10, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root_mixed
    )
    res_mixed = rule.evaluate(doc_mixed)
    warns = [r for r in res_mixed if r.status == CheckStatus.WARNING]
    passes = [r for r in res_mixed if r.status == CheckStatus.PASS]
    assert len(warns) == 2
    assert len(passes) == 1
    assert passes[0].items_count == 1
