"""
Comprehensive tests for MCID and ParentTree validation:
1. Verifies that Artifact entries in the ParentTree representing valid artifacts
   outside the structure tree are NOT flagged as invalid structure elements (preventing false positives).
2. Verifies that genuine errors (illegal Artifact tags inside StructTreeRoot, mismatched object references,
   detached structure elements, and genuine orphan real-content MCIDs) continue to be reported.
"""

import os
import glob
import pytest
from src.pdf_inspector.core.models import (
    PDFDocumentModel, PageModel, StructureNode, CheckStatus
)
from src.pdf_inspector.core.document_parser import DocumentParser
from src.pdf_inspector.engine.pdf_ua.parent_tree_rules import ParentTreeIntegrityRule
from src.pdf_inspector.engine.pdf_ua.content_rules import MCIDStructureReferenceRule


def test_w4_real_pdf_parent_tree_artifact_not_flagged():
    """Verifies that 2025_Form_W-4p1_A11y.pdf produces zero ParentTree or orphan MCID errors for MCID 131."""
    w4_files = glob.glob(r"C:\Users\HBS\Downloads\Tax Form*\**\*W-4*.pdf", recursive=True)
    if not w4_files or not os.path.exists(w4_files[0]):
        pytest.skip("W-4 PDF not found in Downloads")

    doc = DocumentParser(w4_files[0]).parse()
    assert doc is not None

    # ParentTreeIntegrityRule must pass without 01-008 error for MCID 131
    pt_rule = ParentTreeIntegrityRule()
    pt_res = pt_rule.evaluate(doc)
    pt_fails = [r for r in pt_res if r.status == CheckStatus.FAIL]
    assert not any("MCID 131" in r.message for r in pt_fails)
    assert not any("not a valid structure element" in r.message for r in pt_fails)

    # MCIDStructureReferenceRule must pass without orphan error for MCID 131
    mcid_rule = MCIDStructureReferenceRule()
    mcid_res = mcid_rule.evaluate(doc)
    mcid_fails = [r for r in mcid_res if r.status == CheckStatus.FAIL]
    assert not any("131" in r.message for r in mcid_fails)


def test_valid_artifact_in_parent_tree_outside_structure_tree():
    """Valid artifact entry outside structure tree must pass ParentTree and MCID checks."""
    node = StructureNode("p1", "P", "P", page=1, obj_num=10, mcids=[0], mcid_entries=[(0, 1)])
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node])
    page = PageModel(
        page_number=1, width=612, height=792, struct_parents_id=0,
        mcids=[0, 1], artifact_mcids={1}
    )

    pt_map = {
        0: [
            {"obj_num": 10, "tag": "P", "type": "StructElem", "has_parent": True},
            {"obj_num": 359, "tag": "Artifact", "type": "", "has_parent": False}
        ]
    }
    doc = PDFDocumentModel(
        filepath="", filename="valid_artifact.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root, pages=[page],
        has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=1,
        parent_tree_map=pt_map
    )

    pt_rule = ParentTreeIntegrityRule()
    assert not any(r.status == CheckStatus.FAIL for r in pt_rule.evaluate(doc))

    mcid_rule = MCIDStructureReferenceRule()
    assert not any(r.status == CheckStatus.FAIL for r in mcid_rule.evaluate(doc))


def test_illegal_artifact_tag_inside_structure_tree_reported():
    """An Artifact tag illegally placed inside StructTreeRoot must fail Matterhorn 01-008."""
    node_p = StructureNode("p1", "P", "P", page=1, obj_num=10, mcids=[0], mcid_entries=[(0, 1)])
    node_art = StructureNode("art1", "Artifact", "Artifact", page=1, obj_num=20, mcids=[1], mcid_entries=[(1, 1)])
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node_p, node_art])
    page = PageModel(page_number=1, width=612, height=792, struct_parents_id=0, mcids=[0, 1])

    pt_map = {
        0: [
            {"obj_num": 10, "tag": "P", "type": "StructElem", "has_parent": True},
            {"obj_num": 20, "tag": "Artifact", "type": "StructElem", "has_parent": True}
        ]
    }
    doc = PDFDocumentModel(
        filepath="", filename="illegal_artifact.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root, pages=[page],
        has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=1,
        parent_tree_map=pt_map
    )

    pt_rule = ParentTreeIntegrityRule()
    fails = [r for r in pt_rule.evaluate(doc) if r.status == CheckStatus.FAIL]
    assert any("not a valid structure element (tag: 'Artifact')" in r.message for r in fails)


def test_mismatched_parent_tree_reference_reported():
    """Inconsistent ParentTree entry pointing to wrong structure element must fail Matterhorn 01-008."""
    node = StructureNode("p1", "P", "P", page=1, obj_num=10, mcids=[0], mcid_entries=[(0, 1)])
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node])
    page = PageModel(page_number=1, width=612, height=792, struct_parents_id=0, mcids=[0])

    pt_map = {
        0: [
            {"obj_num": 999, "tag": "H1", "type": "StructElem", "has_parent": True}
        ]
    }
    doc = PDFDocumentModel(
        filepath="", filename="mismatch.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root, pages=[page],
        has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=1,
        parent_tree_map=pt_map
    )

    pt_rule = ParentTreeIntegrityRule()
    fails = [r for r in pt_rule.evaluate(doc) if r.status == CheckStatus.FAIL]
    assert any("refers to MCID 0, but /ParentTree points to obj 999" in r.message for r in fails)


def test_detached_structure_element_reported():
    """Detached structure element with no parent and not in StructTreeRoot must fail Matterhorn 01-008."""
    node = StructureNode("p1", "P", "P", page=1, obj_num=10, mcids=[0], mcid_entries=[(0, 1)])
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node])
    page = PageModel(page_number=1, width=612, height=792, struct_parents_id=0, mcids=[0, 1])

    pt_map = {
        0: [
            {"obj_num": 10, "tag": "P", "type": "StructElem", "has_parent": True},
            {"obj_num": 555, "tag": "Span", "type": "StructElem", "has_parent": False}
        ]
    }
    doc = PDFDocumentModel(
        filepath="", filename="detached.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root, pages=[page],
        has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=1,
        parent_tree_map=pt_map
    )

    pt_rule = ParentTreeIntegrityRule()
    fails = [r for r in pt_rule.evaluate(doc) if r.status == CheckStatus.FAIL]
    assert any("obj 555" in r.message and "is not a valid structure element" in r.message for r in fails)


def test_genuine_orphan_mcid_reported():
    """Real content MCID with no structure element and no artifact mapping must fail Matterhorn 01-005."""
    node = StructureNode("p1", "P", "P", page=1, obj_num=10, mcids=[0], mcid_entries=[(0, 1)])
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node])
    page = PageModel(page_number=1, width=612, height=792, struct_parents_id=0, mcids=[0, 99])  # MCID 99 is unreferenced real content

    pt_map = {
        0: [
            {"obj_num": 10, "tag": "P", "type": "StructElem", "has_parent": True}
        ]
    }
    doc = PDFDocumentModel(
        filepath="", filename="orphan.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root, pages=[page],
        has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=1,
        parent_tree_map=pt_map
    )

    mcid_rule = MCIDStructureReferenceRule()
    fails = [r for r in mcid_rule.evaluate(doc) if r.status == CheckStatus.FAIL]
    assert any("Page 1 contains marked content MCID(s) [99] not referenced by any structure element" in r.message for r in fails)


def test_artifact_mcid_with_null_in_parent_tree():
    """An artifact MCID that has null in ParentTree array (ISO 32000-1 §14.7.4.4) must PASS and not fail Matterhorn 01-006."""
    node = StructureNode("p1", "P", "P", page=1, obj_num=10, mcids=[0], mcid_entries=[(0, 1)])
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node])
    page = PageModel(
        page_number=1, width=612, height=792, struct_parents_id=0,
        mcids=[0, 1], artifact_mcids={1}
    )

    pt_map = {
        0: [
            {"obj_num": 10, "tag": "P", "type": "StructElem", "has_parent": True},
            None  # null entry in ParentTree for artifact MCID 1
        ]
    }
    doc = PDFDocumentModel(
        filepath="", filename="artifact_null.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root, pages=[page],
        has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=1,
        parent_tree_map=pt_map
    )

    pt_rule = ParentTreeIntegrityRule()
    pt_fails = [r for r in pt_rule.evaluate(doc) if r.status == CheckStatus.FAIL]
    assert not pt_fails

    mcid_rule = MCIDStructureReferenceRule()
    mcid_fails = [r for r in mcid_rule.evaluate(doc) if r.status == CheckStatus.FAIL]
    assert not mcid_fails


def test_real_content_mcid_with_null_in_parent_tree():
    """A real content MCID that has null in ParentTree array MUST fail Matterhorn 01-006."""
    node = StructureNode("p1", "P", "P", page=1, obj_num=10, mcids=[0], mcid_entries=[(0, 1)])
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node])
    page = PageModel(
        page_number=1, width=612, height=792, struct_parents_id=0,
        mcids=[0, 1], artifact_mcids=set()  # MCID 1 is real content, not an artifact!
    )

    pt_map = {
        0: [
            {"obj_num": 10, "tag": "P", "type": "StructElem", "has_parent": True},
            None  # null entry in ParentTree for real content MCID 1
        ]
    }
    doc = PDFDocumentModel(
        filepath="", filename="real_content_null.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root, pages=[page],
        has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=1,
        parent_tree_map=pt_map
    )

    pt_rule = ParentTreeIntegrityRule()
    pt_fails = [r for r in pt_rule.evaluate(doc) if r.status == CheckStatus.FAIL]
    assert any("MCID 1 has no valid entry in /ParentTree (null entry in ParentTree)" in r.message for r in pt_fails)


def test_artifact_mcid_omitted_from_parent_tree_array():
    """An artifact MCID whose index exceeds ParentTree array length must PASS and not fail 01-006."""
    node = StructureNode("p1", "P", "P", page=1, obj_num=10, mcids=[0], mcid_entries=[(0, 1)])
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node])
    page = PageModel(
        page_number=1, width=612, height=792, struct_parents_id=0,
        mcids=[0, 5], artifact_mcids={5}  # MCID 5 is an artifact, array length is 1
    )

    pt_map = {
        0: [
            {"obj_num": 10, "tag": "P", "type": "StructElem", "has_parent": True}
        ]
    }
    doc = PDFDocumentModel(
        filepath="", filename="artifact_omitted.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root, pages=[page],
        has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=1,
        parent_tree_map=pt_map
    )

    pt_rule = ParentTreeIntegrityRule()
    pt_fails = [r for r in pt_rule.evaluate(doc) if r.status == CheckStatus.FAIL]
    assert not pt_fails


def test_page_with_only_artifact_mcids_no_structparents():
    """A page with only artifact MCIDs and no /StructParents must PASS Matterhorn 01-004."""
    page = PageModel(
        page_number=1, width=612, height=792, struct_parents_id=None,
        mcids=[1, 2], artifact_mcids={1, 2}
    )
    doc = PDFDocumentModel(
        filepath="", filename="artifacts_only.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=None, pages=[page],
        has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=0,
        parent_tree_map={}
    )

    pt_rule = ParentTreeIntegrityRule()
    pt_fails = [r for r in pt_rule.evaluate(doc) if r.status == CheckStatus.FAIL]
    assert not any("lack /StructParents" in r.message for r in pt_fails)


def test_form_xobject_mcid_mapped_under_xobject_structparents():
    """Form XObject MCID mapped under XObject's StructParents must pass ParentTree and MCID integrity."""
    node = StructureNode("p1", "P", "P", page=1, obj_num=10, mcids=[0], mcid_entries=[(0, 1)])
    node_xo = StructureNode("fig1", "Figure", "Figure", page=1, obj_num=20, mcids=[0], mcid_entries=[(0, 1)])
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node, node_xo])
    page = PageModel(
        page_number=1, width=612, height=792, struct_parents_id=0,
        mcids=[0]
    )

    pt_map = {
        0: [
            {"obj_num": 10, "tag": "P", "type": "StructElem", "has_parent": True}
        ],
        5: [  # StructParents 5 for Form XObject
            {"obj_num": 20, "tag": "Figure", "type": "StructElem", "has_parent": True}
        ]
    }
    doc = PDFDocumentModel(
        filepath="", filename="xobject_struct.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root, pages=[page],
        has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=2,
        parent_tree_map=pt_map
    )

    pt_rule = ParentTreeIntegrityRule()
    assert not any(r.status == CheckStatus.FAIL for r in pt_rule.evaluate(doc))

    mcid_rule = MCIDStructureReferenceRule()
    assert not any(r.status == CheckStatus.FAIL for r in mcid_rule.evaluate(doc))
