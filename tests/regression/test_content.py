"""
Regression tests for Content Stream and Marked Content Rules:
- Tagged PDF mark & StructTreeRoot presence (PDFUA-CONTENT-001)
- Real Content Tagged / Unmarked Content Detection (PDFUA-CONTENT-002)
- Artifact inside tagged content (PDFUA-ART-003)
- Tagged content inside artifact (PDFUA-CONTENT-004)
- MCID reference integrity / orphan MCIDs (PDFUA-CONTENT-005)
"""

import pytest
from src.pdf_inspector.core.models import (
    PDFDocumentModel, PageModel, StructureNode, ContentOccurrenceModel,
    ArtifactOccurrenceModel, CheckStatus
)
from src.pdf_inspector.engine.pdf_ua.content_rules import (
    TaggedPDFRule,
    ContentTaggedRule,
    TaggedInsideArtifactRule,
    MCIDStructureReferenceRule,
)
from src.pdf_inspector.engine.pdf_ua.artifact_rules import (
    ArtifactInStructureTreeRule,
    ArtifactInsideTaggedContentRule,
)


class TestContentRegression:
    def test_tagged_pdf_rule(self):
        rule = TaggedPDFRule()

        # Case 1: Untagged
        doc_untagged = PDFDocumentModel(
            filepath="", filename="untagged.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=False, structure_tree=None
        )
        res1 = rule.evaluate(doc_untagged)
        assert len(res1) == 1
        assert res1[0].status == CheckStatus.FAIL

        # Case 2: Tagged
        root = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
        doc_tagged = PDFDocumentModel(
            filepath="", filename="tagged.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        res2 = rule.evaluate(doc_tagged)
        assert len(res2) == 1
        assert res2[0].status == CheckStatus.PASS

    def test_unmarked_real_content_rule(self):
        rule = ContentTaggedRule()

        # Case 1: Page has unmarked text / path painting operator
        unmarked_occ = ContentOccurrenceModel(
            page_number=1,
            operator_type="text",
            operator_name="Tj",
            is_unmarked_real_content=True,
            snippet="Untagged body paragraph"
        )
        p1 = PageModel(
            page_number=1, width=600, height=800,
            content_occurrences=[unmarked_occ],
            unmarked_real_content_count=1
        )
        doc_unmarked = PDFDocumentModel(
            filepath="", filename="unmarked.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, pages=[p1]
        )
        res1 = rule.evaluate(doc_unmarked)
        assert len(res1) >= 1
        assert any(r.status == CheckStatus.FAIL and "Page 1 contains real content" in r.message for r in res1)

        # Case 2: Page has unmarked XObject Do operator
        unmarked_do = ContentOccurrenceModel(
            page_number=2,
            operator_type="xobject",
            operator_name="Do",
            is_unmarked_real_content=True,
            xobject_name="Meta51",
            snippet="XObject /Meta51 Do"
        )
        p_do = PageModel(
            page_number=2, width=600, height=800,
            content_occurrences=[unmarked_do],
            unmarked_real_content_count=1
        )
        doc_do = PDFDocumentModel(
            filepath="", filename="unmarked_do.pdf", filesize=100, pdf_version="1.7",
            page_count=2, is_tagged=True, pages=[PageModel(page_number=1, width=600, height=800), p_do]
        )
        res_do = rule.evaluate(doc_do)
        assert any(r.status == CheckStatus.FAIL and "Page 2 contains real content" in r.message for r in res_do)

        # Case 3: Clean page (all real content in MCID or Artifact)
        p2 = PageModel(
            page_number=1, width=600, height=800,
            content_occurrences=[],
            unmarked_real_content_count=0
        )
        doc_marked = PDFDocumentModel(
            filepath="", filename="clean.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, pages=[p2]
        )
        res2 = rule.evaluate(doc_marked)
        assert len(res2) == 1
        assert res2[0].status == CheckStatus.PASS

    def test_tagged_inside_artifact_rule(self):
        rule = TaggedInsideArtifactRule()

        # Case 1: Page has tagged sequence inside Artifact
        p_bad = PageModel(page_number=2, width=600, height=800, tagged_in_artifact_count=2)
        doc_bad = PDFDocumentModel(
            filepath="", filename="nested_art.pdf", filesize=100, pdf_version="1.7",
            page_count=2, is_tagged=True, pages=[PageModel(page_number=1, width=600, height=800), p_bad]
        )
        res_bad = rule.evaluate(doc_bad)
        assert any(r.status == CheckStatus.FAIL and r.page == 2 for r in res_bad)

        # Case 2: Clean pages
        p_good = PageModel(page_number=1, width=600, height=800, tagged_in_artifact_count=0)
        doc_good = PDFDocumentModel(
            filepath="", filename="clean_art.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, pages=[p_good]
        )
        res_good = rule.evaluate(doc_good)
        assert len(res_good) == 1
        assert res_good[0].status == CheckStatus.PASS

    def test_artifact_inside_tagged_content_rule(self):
        rule = ArtifactInsideTaggedContentRule()

        # Case 1: Artifact inside tagged content
        art_bad = ArtifactOccurrenceModel(
            page_number=1, is_inside_tagged=True, parent_tag="P", parent_mcid=0, text_snippet="Artifact inside P"
        )
        doc_bad = PDFDocumentModel(
            filepath="", filename="art_in_p.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, pages=[PageModel(page_number=1, width=600, height=800, artifacts=[art_bad])]
        )
        res_bad = rule.evaluate(doc_bad)
        assert any(r.status == CheckStatus.FAIL for r in res_bad)

        # Case 2: Artifact legitimately placed outside tagged content
        art_good = ArtifactOccurrenceModel(
            page_number=1, is_inside_tagged=False
        )
        doc_good = PDFDocumentModel(
            filepath="", filename="clean_art.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, pages=[PageModel(page_number=1, width=600, height=800, artifacts=[art_good])]
        )
        res_good = rule.evaluate(doc_good)
        assert all(r.status == CheckStatus.PASS for r in res_good)

    def test_mcid_reference_integrity_rule(self):
        rule = MCIDStructureReferenceRule()

        # Case 1: Page has MCID 0, 1, but structure tree only references MCID 0
        node = StructureNode("p1", "P", "P", mcids=[0])
        root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node])
        page1 = PageModel(page_number=1, width=600, height=800, mcids=[0, 1])
        doc_orphan = PDFDocumentModel(
            filepath="", filename="orphan.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root, pages=[page1]
        )
        res_orphan = rule.evaluate(doc_orphan)
        assert any(r.status == CheckStatus.FAIL and "not referenced" in r.message for r in res_orphan)

        # Case 2: All MCIDs properly referenced
        node2 = StructureNode("p2", "P", "P", mcids=[0, 1])
        root2 = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node2])
        doc_valid = PDFDocumentModel(
            filepath="", filename="valid_mcid.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root2, pages=[page1]
        )
        res_valid = rule.evaluate(doc_valid)
        assert len(res_valid) == 1
        assert res_valid[0].status == CheckStatus.PASS

    def test_structure_mcid_existence_mcr_explicit_page(self):
        """Tests that MCR with explicit /Pg pointing to a different page resolves correctly."""
        from src.pdf_inspector.engine.pdf_ua.content_rules import StructureMCIDExistenceRule
        rule = StructureMCIDExistenceRule()

        # Case 1: Node has parent page=2, but MCR specifies MCID 7 on Page 1 and MCID 3 on Page 2
        node = StructureNode(
            id="p_multi", tag="P", standard_tag="P", page=2,
            mcids=[7, 3],
            mcid_entries=[(7, 1), (3, 2)]
        )
        root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node])
        page1 = PageModel(page_number=1, width=600, height=800, mcids=[7])
        page2 = PageModel(page_number=2, width=600, height=800, mcids=[3])
        doc_valid = PDFDocumentModel(
            filepath="", filename="mcr_valid.pdf", filesize=100, pdf_version="1.7",
            page_count=2, is_tagged=True, structure_tree=root, pages=[page1, page2]
        )
        res_valid = rule.evaluate(doc_valid)
        assert len(res_valid) == 1
        assert res_valid[0].status == CheckStatus.PASS

        # Case 2: Node has MCR with explicit Page 1, but MCID 99 does not exist on Page 1
        node_bad = StructureNode(
            id="p_bad", tag="P", standard_tag="P", page=2,
            mcids=[99],
            mcid_entries=[(99, 1)]
        )
        root_bad = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node_bad])
        doc_bad = PDFDocumentModel(
            filepath="", filename="mcr_bad.pdf", filesize=100, pdf_version="1.7",
            page_count=2, is_tagged=True, structure_tree=root_bad, pages=[page1, page2]
        )
        res_bad = rule.evaluate(doc_bad)
        assert any(r.status == CheckStatus.FAIL and "references MCID 99" in r.message and r.page == 1 for r in res_bad)

        # Case 3: MCR without explicit /Pg (None) falls back to node.page (Page 2)
        node_fallback = StructureNode(
            id="p_fb", tag="P", standard_tag="P", page=2,
            mcids=[3],
            mcid_entries=[(3, None)]
        )
        root_fb = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node_fallback])
        doc_fb = PDFDocumentModel(
            filepath="", filename="mcr_fb.pdf", filesize=100, pdf_version="1.7",
            page_count=2, is_tagged=True, structure_tree=root_fb, pages=[page1, page2]
        )
        res_fb = rule.evaluate(doc_fb)
        assert len(res_fb) == 1
        assert res_fb[0].status == CheckStatus.PASS

    def test_tagged_inside_artifact_mcid_vs_untagged_marker(self):
        """Tests that only marked content with an MCID triggers tagged-inside-artifact failure."""
        rule = TaggedInsideArtifactRule()

        # Untagged marker inside artifact (tagged_in_artifact_count == 0) -> PASS
        p_untagged = PageModel(page_number=1, width=600, height=800, tagged_in_artifact_count=0)
        doc_untagged = PDFDocumentModel(
            filepath="", filename="untagged_art.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, pages=[p_untagged]
        )
        res_untagged = rule.evaluate(doc_untagged)
        assert len(res_untagged) == 1
        assert res_untagged[0].status == CheckStatus.PASS

        # MCID tagged sequence inside artifact (tagged_in_artifact_count > 0) -> FAIL
        p_tagged = PageModel(page_number=1, width=600, height=800, tagged_in_artifact_count=1)
        doc_tagged = PDFDocumentModel(
            filepath="", filename="tagged_art.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, pages=[p_tagged]
        )
        res_tagged = rule.evaluate(doc_tagged)
        assert any(r.status == CheckStatus.FAIL and r.page == 1 for r in res_tagged)

    def test_mcid_reference_integrity_page_scoped(self):
        """Tests that MCID reference checking is properly page-scoped and not fooled by identical MCIDs on different pages."""
        rule = MCIDStructureReferenceRule()

        # Page 1 has MCID 0 (referenced in StructTree). Page 2 also has MCID 0 (NOT referenced in StructTree).
        node_p1 = StructureNode("p1", "P", "P", page=1, mcids=[0], mcid_entries=[(0, 1)])
        root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node_p1])

        page1 = PageModel(page_number=1, width=600, height=800, mcids=[0])
        page2 = PageModel(page_number=2, width=600, height=800, mcids=[0])

        doc = PDFDocumentModel(
            filepath="", filename="multipage_mcid.pdf", filesize=100, pdf_version="1.7",
            page_count=2, is_tagged=True, structure_tree=root, pages=[page1, page2]
        )
        res = rule.evaluate(doc)
        # Page 2 must be flagged as having orphan MCID 0 (Matterhorn 01-005)
        fail_p2 = [r for r in res if r.status == CheckStatus.FAIL and r.page == 2]
        assert len(fail_p2) >= 1
        assert "Page 2 contains marked content MCID(s) [0]" in fail_p2[0].message

    def test_parent_tree_integrity_mismatch_and_corrupt_entries(self):
        """Tests ParentTreeIntegrityRule for Matterhorn 01-006 and 01-008."""
        from src.pdf_inspector.engine.pdf_ua.parent_tree_rules import ParentTreeIntegrityRule
        rule = ParentTreeIntegrityRule()

        node = StructureNode("h1", "H1", "H1", page=1, obj_num=100, mcids=[0], mcid_entries=[(0, 1)])
        root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[node])
        page1 = PageModel(page_number=1, width=600, height=800, struct_parents_id=0, mcids=[0, 1])

        # ParentTree:
        # Index 0: Points to obj 200 (mismatch vs node.obj_num 100) -> Matterhorn 01-008
        # Index 1: Corrupt dictionary with tag 'Artifact' -> Matterhorn 01-008
        pt_map = {
            0: [
                {"obj_num": 200, "tag": "H1", "type": "StructElem", "has_parent": True},
                {"obj_num": 300, "tag": "Artifact", "type": "", "has_parent": False}
            ]
        }
        doc = PDFDocumentModel(
            filepath="", filename="pt_corrupt.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root, pages=[page1],
            has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=1,
            parent_tree_map=pt_map
        )
        res = rule.evaluate(doc)
        fails = [r for r in res if r.status == CheckStatus.FAIL]
        assert any("refers to MCID 0, but /ParentTree points to obj 200" in r.message for r in fails)
        assert any("not a valid structure element (tag: 'Artifact')" in r.message for r in fails)

    def test_parent_tree_supplementary_elements_valid(self):
        """
        Tests that valid supplementary structure elements referenced via /ParentTree
        (such as localized footer tags or supplementary elements not in /K of StructTreeRoot)
        are recognized as valid and do not trigger false-positive Matterhorn 01-005 or 01-008 failures.
        """
        from src.pdf_inspector.engine.pdf_ua.parent_tree_rules import ParentTreeIntegrityRule
        from src.pdf_inspector.engine.pdf_ua.content_rules import MCIDStructureReferenceRule

        # StructTreeRoot -> Document (obj 100) -> Paragraph (obj 101, MCID 0)
        p_node = StructureNode("p1", "P", "P", page=1, obj_num=101, mcids=[0], mcid_entries=[(0, 1)])
        doc_node = StructureNode("doc1", "Document", "Document", page=1, obj_num=100, children=[p_node])
        root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", obj_num=99, children=[doc_node])

        # Page 1 contains MCIDs [0, 1]. MCID 1 is associated with supplementary element obj 150 in ParentTree.
        page1 = PageModel(page_number=1, width=600, height=800, struct_parents_id=0, mcids=[0, 1])

        # ParentTree:
        # Index 0: Points to obj 101 (matches p_node.obj_num 101)
        # Index 1: Supplementary element obj 150 (tag 'P', parent_obj_num 100)
        pt_map = {
            0: [
                {"obj_num": 101, "tag": "P", "type": "StructElem", "has_parent": True, "parent_obj_num": 100},
                {"obj_num": 150, "tag": "P", "type": "StructElem", "has_parent": True, "parent_obj_num": 100}
            ]
        }
        doc = PDFDocumentModel(
            filepath="", filename="pt_supplementary.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root, pages=[page1],
            has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=1,
            parent_tree_map=pt_map
        )

        # 1. ParentTreeIntegrityRule: must NOT report corrupt/orphan entry for obj 150
        pt_rule = ParentTreeIntegrityRule()
        pt_res = pt_rule.evaluate(doc)
        pt_fails = [r for r in pt_res if r.status == CheckStatus.FAIL]
        assert len(pt_fails) == 0

        # 2. MCIDStructureReferenceRule: must recognize MCID 1 has valid structure element via ParentTree
        mcid_rule = MCIDStructureReferenceRule()
        mcid_res = mcid_rule.evaluate(doc)
        mcid_fails = [r for r in mcid_res if r.status == CheckStatus.FAIL]
        assert len(mcid_fails) == 0

    def test_parent_tree_detached_corrupt_entry(self):
        """Tests that detached ParentTree entries (missing /P and not StructTreeRoot) fail Matterhorn 01-008."""
        from src.pdf_inspector.engine.pdf_ua.parent_tree_rules import ParentTreeIntegrityRule

        node = StructureNode("p1", "P", "P", page=1, obj_num=101, mcids=[0], mcid_entries=[(0, 1)])
        root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", obj_num=99, children=[node])
        page1 = PageModel(page_number=1, width=600, height=800, struct_parents_id=0, mcids=[0, 1])

        # Index 1 has no parent (/P missing) and is not StructTreeRoot -> detached
        pt_map = {
            0: [
                {"obj_num": 101, "tag": "P", "type": "StructElem", "has_parent": True, "parent_obj_num": 99},
                {"obj_num": 150, "tag": "Span", "type": "StructElem", "has_parent": False, "parent_obj_num": None}
            ]
        }
        doc = PDFDocumentModel(
            filepath="", filename="pt_detached.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root, pages=[page1],
            has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=1,
            parent_tree_map=pt_map
        )

        rule = ParentTreeIntegrityRule()
        res = rule.evaluate(doc)
        fails = [r for r in res if r.status == CheckStatus.FAIL]
        assert any("is not a valid structure element" in r.message and "obj 150" in r.message for r in fails)

    def test_form_xobject_stream_parent_tree_and_artifact_header(self):
        """
        Tests that Form XObject streams with their own /StructParents (ISO 32000-1 Clause 14.7.4.2)
        and artifacted headers across pages are validly verified in ParentTreeIntegrityRule
        and ContentTaggedRule without false positive failures.
        """
        from src.pdf_inspector.engine.pdf_ua.parent_tree_rules import ParentTreeIntegrityRule
        from src.pdf_inspector.engine.pdf_ua.content_rules import ContentTaggedRule

        # Structure tree has a Span (obj 230) on Page 13 referencing MCID 1 inside Form XObject /Fm0
        span_node = StructureNode("span1", "Span", "Span", page=13, obj_num=230, mcids=[1], mcid_entries=[(1, 13)])
        # Page 13 also has a Paragraph (obj 738) referencing MCID 1 in page content stream
        p_node = StructureNode("p1", "P", "P", page=13, obj_num=738, mcids=[1], mcid_entries=[(1, 13)])
        root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", obj_num=99, children=[span_node, p_node])

        page13 = PageModel(
            page_number=13, width=600, height=800,
            struct_parents_id=14, mcids=[1],
            unmarked_real_content_count=0
        )

        # ParentTree:
        # Key 14 (page struct parents): index 1 -> obj 738 (Paragraph)
        # Key 31 (Form XObject struct parents): index 1 -> obj 230 (Span)
        pt_map = {
            14: [None, {"obj_num": 738, "tag": "P", "type": "StructElem", "has_parent": True, "parent_obj_num": 99}],
            31: [None, {"obj_num": 230, "tag": "Span", "type": "StructElem", "has_parent": True, "parent_obj_num": 99}]
        }
        doc = PDFDocumentModel(
            filepath="", filename="header_xobject.pdf", filesize=100, pdf_version="1.7",
            page_count=13, is_tagged=True, structure_tree=root, pages=[page13],
            has_parent_tree=True, parent_tree_valid=True, parent_tree_entries_count=2,
            parent_tree_map=pt_map
        )

        # 1. ParentTreeIntegrityRule: must recognize obj 230 is mapped under key 31
        pt_rule = ParentTreeIntegrityRule()
        pt_res = pt_rule.evaluate(doc)
        pt_fails = [r for r in pt_res if r.status == CheckStatus.FAIL]
        assert len(pt_fails) == 0

        # 2. ContentTaggedRule: clean page passes
        content_rule = ContentTaggedRule()
        content_res = content_rule.evaluate(doc)
        content_fails = [r for r in content_res if r.status == CheckStatus.FAIL]
        assert len(content_fails) == 0
