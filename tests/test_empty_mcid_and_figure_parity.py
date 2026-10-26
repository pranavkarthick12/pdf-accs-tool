"""
Regression tests for empty marked-content sequences (PDFUA-CONTENT-005, PDFUA-TREE-002)
and multi-page figure bounding box requirements (PDFUA-FIG-001).

Demonstrates:
1. Empty marked-content sequences (no text, path painting, or XObject painting) do not
   produce false-positive failures in PDFUA-CONTENT-005 or PDFUA-TREE-002.
2. Genuine untagged real content (text, paint, images) still produces failures.
3. Nested marked-content sequences and Form XObjects with content are correctly tracked.
4. Multi-page figures are not rejected solely for lacking per-page BBoxes, while malformed
   BBoxes are still caught under Matterhorn 16-001.
"""

import pytest
from src.pdf_inspector.core.models import (
    PDFDocumentModel, PageModel, StructureNode, CheckStatus
)
from src.pdf_inspector.engine.pdf_ua.content_rules import MCIDStructureReferenceRule
from src.pdf_inspector.engine.pdf_ua.parent_tree_rules import ParentTreeIntegrityRule
from src.pdf_inspector.engine.pdf_ua.structure_rules import FigureBoundingBoxRule


def test_empty_marked_content_sequence_not_flagged():
    """Empty marked-content sequences (in empty_mcids) are ignored by CONTENT-005 and TREE-002."""
    # Page with MCID 130 and 131 that contain 0 content operators (empty)
    page1 = PageModel(
        page_number=1,
        width=500.0,
        height=700.0,
        mcids=[130, 131],
        empty_mcids={130, 131},
        struct_parents_id=0
    )
    # ParentTree entry has None for 130 and a detached Figure for 131
    pt_map = {
        0: [None] * 130 + [None, {"tag": "Figure", "obj_num": 999, "has_parent": False}]
    }
    # Structure tree does not reference MCID 130 or 131
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[])
    doc = PDFDocumentModel(
        filepath="", filename="empty_mcid.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, pages=[page1], parent_tree_map=pt_map,
        structure_tree=root, has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=1
    )

    # 1. Content rule (PDFUA-CONTENT-005)
    content_rule = MCIDStructureReferenceRule()
    c_res = content_rule.evaluate(doc)
    assert all(r.status == CheckStatus.PASS for r in c_res), f"Expected PASS for empty MCIDs, got: {c_res}"

    # 2. ParentTree rule (PDFUA-TREE-002)
    tree_rule = ParentTreeIntegrityRule()
    t_res = tree_rule.evaluate(doc)
    assert all(r.status == CheckStatus.PASS for r in t_res), f"Expected PASS for empty MCIDs, got: {t_res}"


def test_genuine_untagged_content_still_flagged():
    """Genuine marked content containing text/paint is flagged if not in structure tree or ParentTree."""
    # Page with MCID 5 which has real content (NOT in empty_mcids)
    page1 = PageModel(
        page_number=1,
        width=500.0,
        height=700.0,
        mcids=[5],
        empty_mcids=set(),  # Has content
        struct_parents_id=0
    )
    pt_map = {
        0: [None, None, None, None, None, None]  # Slot 5 is None
    }
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[])
    doc = PDFDocumentModel(
        filepath="", filename="untagged_content.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, pages=[page1], parent_tree_map=pt_map,
        structure_tree=root, has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=1
    )

    # 1. Content rule must flag genuine unreferenced MCID
    c_res = MCIDStructureReferenceRule().evaluate(doc)
    assert any(r.status == CheckStatus.FAIL and "not referenced" in r.message for r in c_res)

    # 2. ParentTree rule must flag null ParentTree slot for genuine content MCID
    t_res = ParentTreeIntegrityRule().evaluate(doc)
    assert any(r.status == CheckStatus.FAIL and "null entry" in r.message for r in t_res)

    # 3. ParentTree rule must flag detached element for genuine content MCID
    doc.parent_tree_map[0][5] = {"tag": "Figure", "obj_num": 888, "has_parent": False}
    t_res2 = ParentTreeIntegrityRule().evaluate(doc)
    assert any(r.status == CheckStatus.FAIL and "not a valid structure element" in r.message for r in t_res2)


def test_nested_marked_content_stack_tracking():
    """Nested marked-content sequences attribute content to the innermost active MCID only."""
    import re

    # Simulate parser logic for nested sequences:
    # Outer /P << /MCID 10 >> BDC
    #   Inner /Span << /MCID 20 >> BDC
    #     (Visible Text) Tj
    #   EMC
    # EMC
    stream = """
    /P <</MCID 10>> BDC
    /Span <</MCID 20>> BDC
    (Hello nested content) Tj
    EMC
    EMC
    """
    mcids_found = []
    mcids_with_content = set()
    stack = []

    token_re = re.compile(r"""
        (?P<bdc>/(?P<tag>\w+)\s*(?P<props><<.*?>>|/\w+)\s*BDC)|
        (?P<bmc>/(?P<btag>\w+)\s*BMC)|
        (?P<emc>\bEMC\b)|
        (?P<text_tj>\((?:\\.|[^()\\])*\)\s*(?:Tj|'|"))|
        (?P<paint>\b(?:S|s|f\*?|F|b\*?|B\*?|sh)\b)
    """, re.VERBOSE | re.DOTALL)

    for m in token_re.finditer(stream):
        if m.group("bdc"):
            props = m.group("props")
            mc = re.search(r"/MCID\s+(\d+)", props)
            m_id = int(mc.group(1)) if mc else None
            if m_id is not None:
                mcids_found.append(m_id)
            stack.append(m_id)
        elif m.group("emc"):
            if stack:
                stack.pop()
        elif m.group("text_tj") or m.group("paint"):
            innermost = next((active for active in reversed(stack) if active is not None), None)
            if innermost is not None:
                mcids_with_content.add(innermost)

    assert mcids_found == [10, 20]
    # Innermost (20) gets content attributed; outer (10) remains empty
    assert 20 in mcids_with_content
    assert 10 not in mcids_with_content
    empty_mcids = set(mcids_found) - mcids_with_content
    assert empty_mcids == {10}


def test_form_xobject_content_tracking():
    """Form XObjects containing text/paint are properly detected as having content."""
    from pdf_inspector.core.document_parser import STREAM_TOKEN_RE
    import re

    xo_stream = """
    /Figure <</MCID 55>> BDC
    10 20 100 200 re
    f
    EMC
    """
    mcids_found = []
    mcids_with_content = set()
    xo_stack = []

    for xo_m in STREAM_TOKEN_RE.finditer(xo_stream):
        if xo_m.group("bdc"):
            bdc_m = re.match(r"/(\w+)\s*(<<.*?>>|/\w+)\s*BDC", xo_m.group("bdc"), re.DOTALL)
            props = bdc_m.group(2) if bdc_m else ""
            x_mcid = None
            if props.startswith("<<") and "/MCID" in props:
                mc_match = re.search(r"/MCID\s+(\d+)", props)
                if mc_match:
                    x_mcid = int(mc_match.group(1))
                    if x_mcid not in mcids_found:
                        mcids_found.append(x_mcid)
            xo_stack.append(x_mcid)
        elif xo_m.group("emc"):
            if xo_stack:
                xo_stack.pop()
        elif xo_m.group("text_tj") or xo_m.group("paint") or xo_m.group("do") or xo_m.group("bi"):
            innermost_xo = next((st for st in reversed(xo_stack) if st is not None), None)
            if innermost_xo is not None:
                mcids_with_content.add(innermost_xo)

    assert 55 in mcids_found
    assert 55 in mcids_with_content
    assert 55 not in (set(mcids_found) - mcids_with_content)


def test_artifact_contained_mcid_not_treated_as_ordinary_page_mcid(tmp_path):
    """MCIDs encountered inside an active /Artifact sequence are excluded from page.mcids
    and do not cause failures in PDFUA-CONTENT-005 or PDFUA-TREE-002."""
    import pikepdf
    from src.pdf_inspector.core.document_parser import DocumentParser
    from src.pdf_inspector.engine.pdf_ua.content_rules import MCIDStructureReferenceRule
    from src.pdf_inspector.engine.pdf_ua.parent_tree_rules import ParentTreeIntegrityRule

    pdf = pikepdf.new()
    stream_data = b"""
    /Artifact <</Type /Pagination>> BDC
    /P <</MCID 99>> BDC
    (Header page 1) Tj
    EMC
    EMC
    /P <</MCID 1>> BDC
    (Ordinary tagged text) Tj
    EMC
    """
    page = pdf.add_blank_page(page_size=(612, 792))
    page.Contents = pdf.make_stream(stream_data)

    test_pdf = str(tmp_path / "artifact_mcid_test.pdf")
    pdf.save(test_pdf)

    doc = DocumentParser(test_pdf).parse()
    p = doc.pages[0]

    # MCID 99 was inside /Artifact: must NOT be in page.mcids
    assert 99 not in p.mcids
    # Ordinary MCID 1 must be present
    assert 1 in p.mcids
    assert p.mcids == [1]

    # Artifact must be recognized in page.artifacts
    assert len(p.artifacts) >= 1

    # Evaluate rules: MCID 99 must produce no false orphan or ParentTree errors
    # (Mock ParentTree mapping MCID 1)
    doc.has_parent_tree = True
    doc.parent_tree_valid = True
    doc.parent_tree_entries_count = 1
    doc.parent_tree_map = {0: [None, {"tag": "P", "obj_num": 100, "has_parent": True}]}
    p.struct_parents_id = 0

    c_results = MCIDStructureReferenceRule().evaluate(doc)
    assert not any(r.status == CheckStatus.FAIL and "99" in r.message for r in c_results)

    t_results = ParentTreeIntegrityRule().evaluate(doc)
    assert not any(r.status == CheckStatus.FAIL and "99" in r.message for r in t_results)


def test_empty_outer_mcid_containing_inner_mcid_with_content(tmp_path):
    """When a text/paint operator occurs inside nested MCID sequences, attribute it
    to the innermost active MCID only; the outer wrapper MCID is recognized as empty."""
    import pikepdf
    from src.pdf_inspector.core.document_parser import DocumentParser
    from src.pdf_inspector.engine.pdf_ua.content_rules import MCIDStructureReferenceRule

    pdf = pikepdf.new()
    # Replicates Plesha Chapter 16 Page 236: outer MCID 18 wraps inner MCID 22
    stream_data = b"""
    /Formula <</MCID 18>> BDC
    BT
    /P <</MCID 22>> BDC
    (1) Tj
    EMC
    ET
    EMC
    """
    page = pdf.add_blank_page(page_size=(612, 792))
    page.Contents = pdf.make_stream(stream_data)

    test_pdf = str(tmp_path / "nested_empty_outer.pdf")
    pdf.save(test_pdf)

    doc = DocumentParser(test_pdf).parse()
    p = doc.pages[0]

    assert 18 in p.mcids
    assert 22 in p.mcids
    # 18 has no content operators of its own -> must be in empty_mcids
    assert 18 in p.empty_mcids
    # 22 contains (1) Tj -> must NOT be in empty_mcids
    assert 22 not in p.empty_mcids

    # Structure tree references only 22 (node 7333 pattern)
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[
        StructureNode("n22", "P", "P", page=1, mcids=[22])
    ])
    doc.structure_tree = root

    c_results = MCIDStructureReferenceRule().evaluate(doc)
    # Empty outer MCID 18 must NOT be flagged as orphan
    assert not any(r.status == CheckStatus.FAIL and "18" in r.message for r in c_results)


def test_ordinary_non_artifact_mcids_detected_and_associated(tmp_path):
    """Ordinary non-artifact MCIDs are detected, attributed content, and associated correctly."""
    import pikepdf
    from src.pdf_inspector.core.document_parser import DocumentParser

    pdf = pikepdf.new()
    stream_data = b"""
    /P <</MCID 0>> BDC
    (First paragraph) Tj
    EMC
    /P <</MCID 1>> BDC
    (Second paragraph) Tj
    EMC
    """
    page = pdf.add_blank_page(page_size=(612, 792))
    page.Contents = pdf.make_stream(stream_data)

    test_pdf = str(tmp_path / "ordinary_mcids.pdf")
    pdf.save(test_pdf)

    doc = DocumentParser(test_pdf).parse()
    p = doc.pages[0]

    assert p.mcids == [0, 1]
    assert 0 not in p.empty_mcids
    assert 1 not in p.empty_mcids
    assert len(p.empty_mcids) == 0


def test_existing_nested_marked_content_and_artifact_behavior_not_regressing(tmp_path):
    """Verifies that nested marked content with text in both outer and inner MCIDs marks both
    as having content, and artifacts inside tagged sequences are preserved."""
    import pikepdf
    from src.pdf_inspector.core.document_parser import DocumentParser

    pdf = pikepdf.new()
    stream_data = b"""
    /P <</MCID 1>> BDC
    (Outer prefix ) Tj
    /Span <</MCID 2>> BDC
    (nested bold) Tj
    EMC
    ( outer suffix) Tj
    EMC
    /P <</MCID 3>> BDC
    (Real text before artifact) Tj
    /Artifact BMC
    (Decorative line) Tj
    EMC
    EMC
    """
    page = pdf.add_blank_page(page_size=(612, 792))
    page.Contents = pdf.make_stream(stream_data)

    test_pdf = str(tmp_path / "nested_regression.pdf")
    pdf.save(test_pdf)

    doc = DocumentParser(test_pdf).parse()
    p = doc.pages[0]

    assert p.mcids == [1, 2, 3]
    # Both 1 and 2 had their own text operators executed while they were innermost
    assert 1 not in p.empty_mcids
    assert 2 not in p.empty_mcids
    # 3 had real text before artifact
    assert 3 not in p.empty_mcids
    assert len(p.empty_mcids) == 0

    # Artifact inside MCID 3 is tracked
    assert len(p.artifacts) == 1
    assert p.artifact_in_tagged_count == 1



def test_multipage_figure_bounding_box_parity():
    """Multi-page figures pass without per-page BBoxes; invalid BBoxes still fail Matterhorn 16-001."""
    rule = FigureBoundingBoxRule()

    # Case 1: Multi-page figure spanning pages 1 and 2 with single BBox -> PASS
    f1 = StructureNode(
        "f1", "Figure", "Figure", page=1, pages_spanned=[1, 2],
        attributes={"BBox": [0.0, 0.0, 400.0, 600.0]}
    )
    doc1 = PDFDocumentModel(
        filepath="", filename="f1.pdf", filesize=100, pdf_version="1.7",
        page_count=2, is_tagged=True,
        structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[f1])
    )
    res1 = rule.evaluate(doc1)
    assert all(r.status == CheckStatus.PASS for r in res1)

    # Case 2: Multi-page figure spanning pages 1 and 2 without BBox -> PASS (BBox is optional)
    f2 = StructureNode("f2", "Figure", "Figure", page=1, pages_spanned=[1, 2])
    doc2 = PDFDocumentModel(
        filepath="", filename="f2.pdf", filesize=100, pdf_version="1.7",
        page_count=2, is_tagged=True,
        structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[f2])
    )
    res2 = rule.evaluate(doc2)
    assert all(r.status == CheckStatus.PASS for r in res2)

    # Case 3: Figure with malformed BBox (fewer than 4 numbers) -> FAIL Matterhorn 16-001
    f3 = StructureNode(
        "f3", "Figure", "Figure", page=1, pages_spanned=[1, 2],
        attributes={"BBox": [10.0, 20.0]}
    )
    doc3 = PDFDocumentModel(
        filepath="", filename="f3.pdf", filesize=100, pdf_version="1.7",
        page_count=2, is_tagged=True,
        structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[f3])
    )
    res3 = rule.evaluate(doc3)
    assert any(r.status == CheckStatus.FAIL and "invalid /BBox attribute" in r.message for r in res3)


def test_form_xobject_artifact_mcid_does_not_suppress_page_mcid(tmp_path):
    """When a Form XObject contains an artifact with MCID K and the page stream has a genuine,
    non-artifact MCID K, the page MCID is recognized and its content is not classified as empty or missing."""
    import pikepdf
    from src.pdf_inspector.core.document_parser import DocumentParser

    pdf = pikepdf.new()

    # Form XObject containing an artifact sequence with MCID K (e.g. 5)
    xo_stream_data = b"""
    /Artifact <</Type /Pagination>> BDC
    /Span <</MCID 5>> BDC
    (Header Artifact Text) Tj
    EMC
    EMC
    """
    xo = pdf.make_stream(xo_stream_data)
    xo[pikepdf.Name.Type] = pikepdf.Name.XObject
    xo[pikepdf.Name.Subtype] = pikepdf.Name.Form
    xo[pikepdf.Name.BBox] = pikepdf.Array([0, 0, 100, 100])

    # Page content stream containing a genuine, non-artifact MCID 5 with visible text
    page_stream_data = b"""
    /P <</MCID 5>> BDC
    BT
    (Genuine Page Content) Tj
    ET
    EMC
    """

    page = pdf.add_blank_page(page_size=(612, 792))
    page.Contents = pdf.make_stream(page_stream_data)
    page.Resources = pikepdf.Dictionary(
        XObject=pikepdf.Dictionary({
            "/Fm0": xo
        })
    )

    test_pdf = str(tmp_path / "form_xo_artifact_isolation.pdf")
    pdf.save(test_pdf)

    doc = DocumentParser(test_pdf).parse()
    p = doc.pages[0]

    # Requirement 1 & 3: Assert page MCID is still recognized
    assert 5 in p.mcids
    # Assert its content is not incorrectly classified as empty or missing
    assert 5 not in p.empty_mcids


def test_form_xobject_artifact_exclusion_and_nested_scope(tmp_path):
    """Form XObject artifact exclusion works within the Form XObject itself while preserving
    non-artifact MCIDs and isolating nested scopes."""
    import pikepdf
    from src.pdf_inspector.core.document_parser import DocumentParser

    pdf = pikepdf.new()

    # Form XObject stream:
    # - Nested artifact marked-content: /Artifact BDC -> /Span <</MCID 10>> BDC -> (Art) Tj -> EMC -> EMC
    # - Genuine tagged non-artifact: /P <</MCID 20>> BDC -> (Visible Form Text) Tj -> EMC
    xo_stream_data = b"""
    /Artifact <</Type /Layout>> BDC
    /Span <</MCID 10>> BDC
    (Form Artifact Text) Tj
    EMC
    EMC
    /P <</MCID 20>> BDC
    (Legitimate Form Component) Tj
    EMC
    """
    xo = pdf.make_stream(xo_stream_data)
    xo[pikepdf.Name.Type] = pikepdf.Name.XObject
    xo[pikepdf.Name.Subtype] = pikepdf.Name.Form
    xo[pikepdf.Name.BBox] = pikepdf.Array([0, 0, 100, 100])

    # Page stream:
    # - Genuine tagged non-artifact with MCID 10 (same number as Form XObject artifact)
    page_stream_data = b"""
    /H1 <</MCID 10>> BDC
    BT
    (Page Section Title) Tj
    ET
    EMC
    """

    page = pdf.add_blank_page(page_size=(612, 792))
    page.Contents = pdf.make_stream(page_stream_data)
    page.Resources = pikepdf.Dictionary(
        XObject=pikepdf.Dictionary({
            "/Fm1": xo
        })
    )

    test_pdf = str(tmp_path / "form_xo_nested_and_exclusion.pdf")
    pdf.save(test_pdf)

    doc = DocumentParser(test_pdf).parse()
    p = doc.pages[0]

    # Page MCID 10 must be recognized and have content
    assert 10 in p.mcids
    assert 10 not in p.empty_mcids

    # Form XObject non-artifact MCID 20 must be recognized and have content
    assert 20 in p.mcids
    assert 20 not in p.empty_mcids

    # The artifact MCID 10 from the Form XObject must NOT have created a separate orphan/empty entry
    assert p.empty_mcids == set()

