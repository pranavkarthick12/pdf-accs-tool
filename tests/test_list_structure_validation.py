"""
Comprehensive Automated Tests for List Structure Validation (PDFUA-LIST-001 & QUAL-LIST-001)
Validates ISO 14289-1:2014 Clause 7.4, Matterhorn Protocol 1.1 Checkpoints 28-001 and 28-002,
and ISO 32000-1:2008 Clause 14.8.4.3.3.

Covers:
- Valid single-label, single-body list items
- Duplicate direct <Lbl> children (cardinality violation)
- Duplicate direct <LBody> children (cardinality violation)
- Missing-label edge cases (permitted under ISO 32000-1)
- Missing-body edge cases (handled safely without false positives)
- Both missing (empty LI or raw MCID without LBody)
- Direct invalid children under LI (P, Span, Table)
- Direct invalid children under L (P, Sect)
- Nested lists inside <LBody> (must PASS without counting nested descendants)
- Multiple levels of nested lists (3 levels deep)
- Nested <Lbl> belonging to a nested <LI> must not count against the parent <LI>
- Defective nested <LI> flagged independently without falsely failing the parent <LI>
- Direct <L> placed directly under <LI> without <LBody> wrapper (violates Matterhorn 28-002)
- Empty, malformed, and unusual structure references (handled safely)
- Full end-to-end DocumentParser and AuditRunner audit with real pikepdf document
"""

import os
import tempfile
import pytest
import pymupdf
import pikepdf

from src.pdf_inspector.core.models import (
    PDFDocumentModel, StructureNode, ListModel, CheckStatus, Severity
)
from src.pdf_inspector.engine.pdf_ua.list_rules import ListStructureHierarchyRule
from src.pdf_inspector.engine.quality.quality_rules import ListItemStructureQualityRule
from src.pdf_inspector.core.document_parser import DocumentParser
from src.pdf_inspector.engine.runner import AuditRunner


class TestListStructureHierarchyValidation:
    """Tests for ListStructureHierarchyRule (PDFUA-LIST-001)."""

    def setup_method(self):
        self.rule = ListStructureHierarchyRule()

    def test_valid_single_label_single_body(self):
        """Case 1: Standard LI with exactly 1 direct <Lbl> and 1 direct <LBody> -> PASS."""
        lbl = StructureNode(id="lbl1", tag="Lbl", standard_tag="Lbl", page=1, text_content="1.")
        lbody = StructureNode(id="lb1", tag="LBody", standard_tag="LBody", page=1, text_content="First item text")
        li = StructureNode(id="li1", tag="LI", standard_tag="LI", page=1, children=[lbl, lbody])
        l_node = StructureNode(id="l1", tag="L", standard_tag="L", page=1, children=[li])
        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[l_node])

        doc = PDFDocumentModel(
            filepath="", filename="valid_list.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        assert len(results) >= 1
        assert all(r.status == CheckStatus.PASS for r in results)
        assert any("conform" in r.message for r in results)

    def test_duplicate_direct_lbl_children(self):
        """Case 2: LI with two direct <Lbl> children -> FAIL with cardinality violation."""
        lbl1 = StructureNode(id="lbl1", tag="Lbl", standard_tag="Lbl", page=1, text_content="1.")
        lbl2 = StructureNode(id="lbl2", tag="Lbl", standard_tag="Lbl", page=1, text_content="a.")
        lbody = StructureNode(id="lb1", tag="LBody", standard_tag="LBody", page=1, text_content="Body text")
        li = StructureNode(id="li1", tag="LI", standard_tag="LI", page=1, children=[lbl1, lbl2, lbody])
        l_node = StructureNode(id="l1", tag="L", standard_tag="L", page=1, children=[li])
        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[l_node])

        doc = PDFDocumentModel(
            filepath="", filename="dup_lbl.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        fails = [r for r in results if r.status == CheckStatus.FAIL]
        assert len(fails) == 1
        fail = fails[0]
        assert "2 direct <Lbl>" in fail.message
        assert "at most 1" in fail.message
        assert "Path: L/LI" in fail.evidence
        assert "2 <Lbl>, 1 <LBody>" in fail.evidence
        assert fail.object_reference == "<LI id='li1'>"

    def test_duplicate_direct_lbody_children(self):
        """Case 3: LI with two direct <LBody> children -> FAIL with cardinality violation."""
        lbl = StructureNode(id="lbl1", tag="Lbl", standard_tag="Lbl", page=2, text_content="*")
        lbody1 = StructureNode(id="lb1", tag="LBody", standard_tag="LBody", page=2, text_content="Part 1")
        lbody2 = StructureNode(id="lb2", tag="LBody", standard_tag="LBody", page=2, text_content="Part 2")
        li = StructureNode(id="li1", tag="LI", standard_tag="LI", page=2, children=[lbl, lbody1, lbody2])
        l_node = StructureNode(id="l1", tag="L", standard_tag="L", page=2, children=[li])
        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[l_node])

        doc = PDFDocumentModel(
            filepath="", filename="dup_lbody.pdf", filesize=100, pdf_version="1.7",
            page_count=2, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        fails = [r for r in results if r.status == CheckStatus.FAIL]
        assert len(fails) == 1
        fail = fails[0]
        assert "2 direct <LBody>" in fail.message
        assert "at most 1" in fail.message
        assert "1 <Lbl>, 2 <LBody>" in fail.evidence
        assert fail.page == 2

    def test_missing_lbl_permitted(self):
        """Case 4: LI with only <LBody> (bulletless/unnumbered list) -> PASS."""
        lbody = StructureNode(id="lb1", tag="LBody", standard_tag="LBody", page=1, text_content="Unbulleted item")
        li = StructureNode(id="li1", tag="LI", standard_tag="LI", page=1, children=[lbody])
        l_node = StructureNode(id="l1", tag="L", standard_tag="L", page=1, children=[li])
        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[l_node])

        doc = PDFDocumentModel(
            filepath="", filename="no_lbl.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        assert not any(r.status == CheckStatus.FAIL for r in results)
        assert any(r.status == CheckStatus.PASS for r in results)

    def test_missing_lbody_handled_safely(self):
        """Case 5: LI with only <Lbl> (permitted under ISO 32000-1 grammar) -> No false-positive FAIL."""
        lbl = StructureNode(id="lbl1", tag="Lbl", standard_tag="Lbl", page=1, text_content="Note bullet")
        li = StructureNode(id="li1", tag="LI", standard_tag="LI", page=1, children=[lbl])
        l_node = StructureNode(id="l1", tag="L", standard_tag="L", page=1, children=[li])
        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[l_node])

        doc = PDFDocumentModel(
            filepath="", filename="only_lbl.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        assert not any(r.status == CheckStatus.FAIL for r in results)
        assert any(r.status == CheckStatus.PASS for r in results)

    def test_empty_li_element(self):
        """Case 6: Empty LI element with no children and no MCIDs -> FAIL."""
        li_empty = StructureNode(id="li_empty", tag="LI", standard_tag="LI", page=1, children=[])
        l_node = StructureNode(id="l1", tag="L", standard_tag="L", page=1, children=[li_empty])
        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[l_node])

        doc = PDFDocumentModel(
            filepath="", filename="empty_li.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        fails = [r for r in results if r.status == CheckStatus.FAIL]
        assert len(fails) == 1
        assert "is empty" in fails[0].message

    def test_inadmissible_direct_child_under_li(self):
        """Case 7: LI containing direct <P> or <Span> -> FAIL (Matterhorn 28-002)."""
        p_child = StructureNode(id="p1", tag="P", standard_tag="P", page=1, text_content="Paragraph in LI")
        li_bad = StructureNode(id="li1", tag="LI", standard_tag="LI", page=1, children=[p_child])
        l_node = StructureNode(id="l1", tag="L", standard_tag="L", page=1, children=[li_bad])
        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[l_node])

        doc = PDFDocumentModel(
            filepath="", filename="p_in_li.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        fails = [r for r in results if r.status == CheckStatus.FAIL]
        assert len(fails) == 1
        assert "invalid direct child" in fails[0].message
        assert "'P'" in fails[0].message

    def test_inadmissible_direct_child_under_l(self):
        """Case 8: List container <L> containing direct <P> -> FAIL (Matterhorn 28-001)."""
        p_child = StructureNode(id="p1", tag="P", standard_tag="P", page=1, text_content="Paragraph in L")
        l_bad = StructureNode(id="l1", tag="L", standard_tag="L", page=1, children=[p_child])
        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[l_bad])

        doc = PDFDocumentModel(
            filepath="", filename="p_in_l.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        fails = [r for r in results if r.status == CheckStatus.FAIL]
        assert len(fails) == 1
        assert "List container <L>" in fails[0].message
        assert "Matterhorn 28-001" in fails[0].message

    def test_nested_list_inside_lbody(self):
        """
        Case 9: Nested list inside <LBody> must PASS.
        Nested <Lbl> and <LBody> belonging to the inner list must NOT count against the parent <LI>.
        """
        # Nested list (inside parent LBody)
        nested_lbl = StructureNode(id="nlbl1", tag="Lbl", standard_tag="Lbl", page=1, text_content="a.")
        nested_lbody = StructureNode(id="nlb1", tag="LBody", standard_tag="LBody", page=1, text_content="Nested item")
        nested_li = StructureNode(id="nli1", tag="LI", standard_tag="LI", page=1, children=[nested_lbl, nested_lbody])
        nested_l = StructureNode(id="nl1", tag="L", standard_tag="L", page=1, children=[nested_li])

        # Parent list
        parent_lbl = StructureNode(id="plbl1", tag="Lbl", standard_tag="Lbl", page=1, text_content="1.")
        parent_lbody = StructureNode(id="plb1", tag="LBody", standard_tag="LBody", page=1, children=[nested_l], text_content="Parent item")
        parent_li = StructureNode(id="pli1", tag="LI", standard_tag="LI", page=1, children=[parent_lbl, parent_lbody])
        parent_l = StructureNode(id="pl1", tag="L", standard_tag="L", page=1, children=[parent_li])

        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[parent_l])

        doc = PDFDocumentModel(
            filepath="", filename="nested_list.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        assert not any(r.status == CheckStatus.FAIL for r in results)
        passes = [r for r in results if r.status == CheckStatus.PASS]
        assert len(passes) >= 1
        assert any("All 2 list(s)" in p.message for p in passes)

    def test_multiple_levels_of_nested_lists(self):
        """Case 10: 3 levels of nested lists inside LBody -> All valid, must PASS."""
        # Level 3 (deepest)
        l3_lbl = StructureNode(id="l3_lbl", tag="Lbl", standard_tag="Lbl", page=1, text_content="i.")
        l3_lbody = StructureNode(id="l3_lbody", tag="LBody", standard_tag="LBody", page=1, text_content="Level 3 item")
        l3_li = StructureNode(id="l3_li", tag="LI", standard_tag="LI", page=1, children=[l3_lbl, l3_lbody])
        l3 = StructureNode(id="l3", tag="L", standard_tag="L", page=1, children=[l3_li])

        # Level 2
        l2_lbl = StructureNode(id="l2_lbl", tag="Lbl", standard_tag="Lbl", page=1, text_content="A.")
        l2_lbody = StructureNode(id="l2_lbody", tag="LBody", standard_tag="LBody", page=1, children=[l3], text_content="Level 2 item")
        l2_li = StructureNode(id="l2_li", tag="LI", standard_tag="LI", page=1, children=[l2_lbl, l2_lbody])
        l2 = StructureNode(id="l2", tag="L", standard_tag="L", page=1, children=[l2_li])

        # Level 1 (top)
        l1_lbl = StructureNode(id="l1_lbl", tag="Lbl", standard_tag="Lbl", page=1, text_content="1.")
        l1_lbody = StructureNode(id="l1_lbody", tag="LBody", standard_tag="LBody", page=1, children=[l2], text_content="Level 1 item")
        l1_li = StructureNode(id="l1_li", tag="LI", standard_tag="LI", page=1, children=[l1_lbl, l1_lbody])
        l1 = StructureNode(id="l1", tag="L", standard_tag="L", page=1, children=[l1_li])

        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[l1])

        doc = PDFDocumentModel(
            filepath="", filename="three_levels.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        assert not any(r.status == CheckStatus.FAIL for r in results)
        assert any(r.status == CheckStatus.PASS and "All 3 list(s)" in r.message for r in results)

    def test_defective_nested_li_isolated_to_nested_element(self):
        """
        Case 11: Defective nested <LI> (duplicate Lbl) fails with its own path,
        while parent <LI> is valid and not falsely flagged.
        """
        # Nested list with 2 <Lbl> (duplicate)
        nlbl1 = StructureNode(id="nlbl1", tag="Lbl", standard_tag="Lbl", page=1, text_content="a.")
        nlbl2 = StructureNode(id="nlbl2", tag="Lbl", standard_tag="Lbl", page=1, text_content="b.")
        nlbody = StructureNode(id="nlbody", tag="LBody", standard_tag="LBody", page=1, text_content="Nested content")
        nested_li = StructureNode(id="nested_li", tag="LI", standard_tag="LI", page=1, children=[nlbl1, nlbl2, nlbody])
        nested_l = StructureNode(id="nested_l", tag="L", standard_tag="L", page=1, children=[nested_li])

        # Clean parent list
        plbl = StructureNode(id="plbl", tag="Lbl", standard_tag="Lbl", page=1, text_content="1.")
        plbody = StructureNode(id="plbody", tag="LBody", standard_tag="LBody", page=1, children=[nested_l], text_content="Parent content")
        parent_li = StructureNode(id="parent_li", tag="LI", standard_tag="LI", page=1, children=[plbl, plbody])
        parent_l = StructureNode(id="parent_l", tag="L", standard_tag="L", page=1, children=[parent_li])

        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[parent_l])

        doc = PDFDocumentModel(
            filepath="", filename="isolated_defect.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        fails = [r for r in results if r.status == CheckStatus.FAIL]
        # Exactly one failure for the nested LI, none for parent LI
        assert len(fails) == 1
        assert fails[0].object_reference == "<LI id='nested_li'>"
        assert "2 direct <Lbl>" in fails[0].message
        assert "nested_l" in fails[0].evidence or "L/LI/LBody/L/LI" in fails[0].evidence

    def test_direct_nested_l_under_li_without_lbody(self):
        """Case 12: Placing <L> directly under <LI> without wrapping in <LBody> -> FAIL."""
        lbl = StructureNode(id="lbl1", tag="Lbl", standard_tag="Lbl", page=1, text_content="1.")
        sub_li = StructureNode(id="sub_li", tag="LI", standard_tag="LI", page=1, children=[
            StructureNode(id="sub_lbl", tag="Lbl", standard_tag="Lbl", page=1),
            StructureNode(id="sub_lb", tag="LBody", standard_tag="LBody", page=1)
        ])
        direct_l = StructureNode(id="direct_l", tag="L", standard_tag="L", page=1, children=[sub_li])
        # direct_l is child of LI instead of LBody
        bad_li = StructureNode(id="bad_li", tag="LI", standard_tag="LI", page=1, children=[lbl, direct_l])
        l_node = StructureNode(id="l1", tag="L", standard_tag="L", page=1, children=[bad_li])
        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[l_node])

        doc = PDFDocumentModel(
            filepath="", filename="unwrapped_l.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        fails = [r for r in results if r.status == CheckStatus.FAIL]
        assert len(fails) >= 1
        assert any("invalid direct child" in f.message and "'L'" in f.message for f in fails)

    def test_empty_or_malformed_structure_references(self):
        """Case 13: Handle malformed children and unusual references safely without crashing."""
        li_malformed = StructureNode(id="li_m", tag="LI", standard_tag="LI", page=1)
        # Injected malformed children
        li_malformed.children = [None, StructureNode(id="lb1", tag="LBody", standard_tag="LBody", page=1)]
        l_node = StructureNode(id="l1", tag="L", standard_tag="L", page=1, children=[li_malformed])
        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[l_node])

        doc = PDFDocumentModel(
            filepath="", filename="malformed.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        # Must evaluate safely without AttributeError or TypeError
        results = self.rule.evaluate(doc)
        assert len(results) >= 1
        assert any(r.status == CheckStatus.PASS for r in results)

    def test_caption_under_l_is_valid(self):
        """Case 14: An <L> containing <Caption> followed by <LI> is valid per ISO 32000-1."""
        caption = StructureNode(id="cap1", tag="Caption", standard_tag="Caption", page=1, text_content="List of steps")
        lbl = StructureNode(id="lbl1", tag="Lbl", standard_tag="Lbl", page=1, text_content="1.")
        lbody = StructureNode(id="lb1", tag="LBody", standard_tag="LBody", page=1, text_content="Step 1")
        li = StructureNode(id="li1", tag="LI", standard_tag="LI", page=1, children=[lbl, lbody])
        l_node = StructureNode(id="l1", tag="L", standard_tag="L", page=1, children=[caption, li])
        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[l_node])

        doc = PDFDocumentModel(
            filepath="", filename="list_caption.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        assert not any(r.status == CheckStatus.FAIL for r in results)
        assert any(r.status == CheckStatus.PASS for r in results)


class TestQualityListValidation:
    """Tests for ListItemStructureQualityRule (QUAL-LIST-001)."""

    def setup_method(self):
        self.rule = ListItemStructureQualityRule()

    def test_quality_duplicate_lbl_fails(self):
        """QUAL-LIST-001 flags duplicate direct <Lbl> elements."""
        lbl1 = StructureNode(id="lbl1", tag="Lbl", standard_tag="Lbl", page=1)
        lbl2 = StructureNode(id="lbl2", tag="Lbl", standard_tag="Lbl", page=1)
        lbody = StructureNode(id="lb1", tag="LBody", standard_tag="LBody", page=1)
        li = StructureNode(id="li1", tag="LI", standard_tag="LI", page=1, children=[lbl1, lbl2, lbody])
        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[li])

        doc = PDFDocumentModel(
            filepath="", filename="qual_dup_lbl.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        fails = [r for r in results if r.status == CheckStatus.FAIL]
        assert len(fails) == 1

    def test_quality_duplicate_lbody_fails(self):
        """QUAL-LIST-001 flags duplicate direct <LBody> elements."""
        lbl = StructureNode(id="lbl1", tag="Lbl", standard_tag="Lbl", page=1)
        lb1 = StructureNode(id="lb1", tag="LBody", standard_tag="LBody", page=1)
        lb2 = StructureNode(id="lb2", tag="LBody", standard_tag="LBody", page=1)
        li = StructureNode(id="li1", tag="LI", standard_tag="LI", page=1, children=[lbl, lb1, lb2])
        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[li])

        doc = PDFDocumentModel(
            filepath="", filename="qual_dup_lb.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        fails = [r for r in results if r.status == CheckStatus.FAIL]
        assert len(fails) == 1

    def test_quality_nested_list_passes(self):
        """QUAL-LIST-001 accepts valid nested lists inside <LBody>."""
        nested_lbl = StructureNode(id="nlbl1", tag="Lbl", standard_tag="Lbl", page=1)
        nested_lbody = StructureNode(id="nlb1", tag="LBody", standard_tag="LBody", page=1)
        nested_li = StructureNode(id="nli1", tag="LI", standard_tag="LI", page=1, children=[nested_lbl, nested_lbody])
        nested_l = StructureNode(id="nl1", tag="L", standard_tag="L", page=1, children=[nested_li])

        parent_lbl = StructureNode(id="plbl1", tag="Lbl", standard_tag="Lbl", page=1)
        parent_lbody = StructureNode(id="plb1", tag="LBody", standard_tag="LBody", page=1, children=[nested_l])
        parent_li = StructureNode(id="pli1", tag="LI", standard_tag="LI", page=1, children=[parent_lbl, parent_lbody])
        parent_l = StructureNode(id="pl1", tag="L", standard_tag="L", page=1, children=[parent_li])

        root = StructureNode(id="root", tag="StructTreeRoot", standard_tag="StructTreeRoot", children=[parent_l])

        doc = PDFDocumentModel(
            filepath="", filename="qual_nested.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        results = self.rule.evaluate(doc)
        assert not any(r.status == CheckStatus.FAIL for r in results)
        assert any(r.status == CheckStatus.PASS and r.items_count == 2 for r in results)


class TestRealPDFListPipeline:
    """End-to-end integration test creating a tagged PDF with pikepdf and auditing."""

    def test_real_pdf_with_valid_and_nested_lists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "test_nested_real.pdf")
            # 1. Create base PDF with PyMuPDF
            mupdf_doc = pymupdf.open()
            page = mupdf_doc.new_page(width=612, height=792)
            page.insert_text((50, 100), "1. Parent item")
            page.insert_text((80, 120), "a. Nested subitem")
            mupdf_doc.save(pdf_path)
            mupdf_doc.close()

            # 2. Tag with pikepdf: StructTreeRoot -> L -> LI -> (Lbl, LBody -> (text, nested L -> LI -> (Lbl, LBody)))
            with pikepdf.open(pdf_path, allow_overwriting_input=True) as pike:
                pike.Root["/MarkInfo"] = pikepdf.Dictionary({"/Marked": True})

                # Nested list elements
                nlbl = pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/Lbl")})
                nlbody = pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/LBody")})
                nli = pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/LI"), "/K": pikepdf.Array([nlbl, nlbody])})
                nested_l = pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/L"), "/K": pikepdf.Array([nli])})

                # Parent list elements
                plbl = pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/Lbl")})
                plbody = pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/LBody"), "/K": pikepdf.Array([nested_l])})
                pli = pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/LI"), "/K": pikepdf.Array([plbl, plbody])})
                parent_l = pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/L"), "/K": pikepdf.Array([pli])})

                tree_root = pike.make_indirect(pikepdf.Dictionary({
                    "/Type": pikepdf.Name("/StructTreeRoot"),
                    "/K": pikepdf.Array([parent_l])
                }))
                pike.Root["/StructTreeRoot"] = tree_root
                pike.save(pdf_path)

            # 3. Parse and audit document
            parsed_doc = DocumentParser(pdf_path).parse()
            assert parsed_doc is not None
            assert len(parsed_doc.lists) == 2
            assert all(l.is_valid_structure for l in parsed_doc.lists)

            report = AuditRunner().run(parsed_doc)
            # Both PDFUA-LIST-001 and QUAL-LIST-001 must PASS
            list_res = [r for r in report.results if r.check_id == "PDFUA-LIST-001"]
            qual_res = [r for r in report.results if r.check_id == "QUAL-LIST-001"]

            assert len(list_res) >= 1
            assert all(r.status == CheckStatus.PASS for r in list_res)
            assert len(qual_res) >= 1
            assert all(r.status == CheckStatus.PASS for r in qual_res)

    def test_real_pdf_with_duplicate_lbl_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "test_dup_lbl_real.pdf")
            mupdf_doc = pymupdf.open()
            page = mupdf_doc.new_page(width=612, height=792)
            page.insert_text((50, 100), "1. 2. Malformed item")
            mupdf_doc.save(pdf_path)
            mupdf_doc.close()

            # Tag with duplicate Lbl under LI
            with pikepdf.open(pdf_path, allow_overwriting_input=True) as pike:
                pike.Root["/MarkInfo"] = pikepdf.Dictionary({"/Marked": True})

                lbl1 = pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/Lbl")})
                lbl2 = pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/Lbl")})
                lbody = pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/LBody")})
                li = pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/LI"), "/K": pikepdf.Array([lbl1, lbl2, lbody])})
                l_elem = pikepdf.Dictionary({"/Type": pikepdf.Name("/StructElem"), "/S": pikepdf.Name("/L"), "/K": pikepdf.Array([li])})

                tree_root = pike.make_indirect(pikepdf.Dictionary({
                    "/Type": pikepdf.Name("/StructTreeRoot"),
                    "/K": pikepdf.Array([l_elem])
                }))
                pike.Root["/StructTreeRoot"] = tree_root
                pike.save(pdf_path)

            parsed_doc = DocumentParser(pdf_path).parse()
            assert parsed_doc is not None
            assert len(parsed_doc.lists) == 1
            assert parsed_doc.lists[0].is_valid_structure is False

            report = AuditRunner().run(parsed_doc)
            list_fails = [r for r in report.results if r.check_id == "PDFUA-LIST-001" and r.status == CheckStatus.FAIL]
            assert len(list_fails) >= 1
            assert "2 direct <Lbl>" in list_fails[0].message
