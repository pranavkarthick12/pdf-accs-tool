"""
Regression tests for Structure Tree and Containment Rules:
- ISO 32000-1 Clause 14.8.4 parent-child admissibility & nesting
- Structure tree root and hierarchy integrity (StructureTreeIntegrityRule)
- Structure nesting and containment rules (StructureNestingRule)
- Empty structure elements and containers (EmptyStructureElementsRule)
- Figure explicit BBox and Placement attributes (FigureBoundingBoxRule, StructureNestingRule)
"""

import pytest
from src.pdf_inspector.core.models import (
    PDFDocumentModel, StructureNode, CheckStatus
)
from src.pdf_inspector.engine.pdf_ua.structure_rules import (
    StructureTreeIntegrityRule,
    StructureNestingRule,
    EmptyStructureElementsRule,
    FigureBoundingBoxRule,
)


class TestStructureRegression:
    def test_structure_hierarchy_and_containment(self):
        rule = StructureTreeIntegrityRule()

        # Case 1: InlineShape (mapped to Sect) placed illegally inside P
        sect_node = StructureNode("sect1", "InlineShape", "Sect", page=1)
        p_node = StructureNode("p1", "P", "P", page=1, children=[sect_node])
        root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[p_node])

        doc_bad = PDFDocumentModel(
            filepath="", filename="sect_in_p.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        res_bad = rule.evaluate(doc_bad)
        assert any(
            r.status in (CheckStatus.FAIL, CheckStatus.WARNING)
            and ("inappropriate" in r.message.lower() or "sect" in r.message.lower())
            for r in res_bad
        )

        # Case 2: InlineShape (mapped to Sect) placed illegally inside LBody
        inlineshape_node = StructureNode("inline1", "InlineShape", "Sect", page=1)
        lbody_node = StructureNode("lb1", "LBody", "LBody", page=1, children=[inlineshape_node])
        li_node = StructureNode("li1", "LI", "LI", page=1, children=[lbody_node])
        l_node = StructureNode("l1", "L", "L", page=1, children=[li_node])
        root_lbody_bad = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[l_node])

        doc_lbody_bad = PDFDocumentModel(
            filepath="", filename="sect_in_lbody.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_lbody_bad
        )
        res_lbody = rule.evaluate(doc_lbody_bad)
        assert any(
            r.status in (CheckStatus.FAIL, CheckStatus.WARNING)
            and ("inappropriate" in r.message.lower() or "sect" in r.message.lower())
            for r in res_lbody
        )

        # Case 3: Clean hierarchy: Document -> Sect -> H1, P
        h1 = StructureNode("h1", "H1", "H1", page=1, text_content="Title")
        p = StructureNode("p2", "P", "P", page=1, text_content="Paragraph text")
        sect = StructureNode("s1", "Sect", "Sect", page=1, children=[h1, p])
        doc_node = StructureNode("d1", "Document", "Document", page=1, children=[sect])
        root_clean = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[doc_node])

        doc_clean = PDFDocumentModel(
            filepath="", filename="clean_tree.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_clean
        )
        res_clean = rule.evaluate(doc_clean)
        assert all(r.status != CheckStatus.FAIL for r in res_clean)

    def test_figure_placement_block_vs_inline(self):
        rule = StructureNestingRule()

        # Case 1: Figure at block level under Part without Placement=Block (Must FAIL under Matterhorn 13-007)
        fig_no_attr = StructureNode("fig1", "Figure", "Figure", page=1, attributes={})
        part_bad = StructureNode("part1", "Part", "Part", page=1, children=[fig_no_attr])
        root_bad = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[part_bad])
        doc_bad = PDFDocumentModel(
            filepath="", filename="fig_block_fail.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_bad
        )
        res_bad = rule.evaluate(doc_bad)
        assert any(r.status == CheckStatus.FAIL and "Placement=Block" in r.message for r in res_bad)

        # Case 2: Figure at block level under Part WITH Placement=Block (Must PASS)
        fig_with_attr = StructureNode(
            "fig2", "Figure", "Figure", page=1,
            placement="Block", attributes={"Placement": "Block"}
        )
        part_good = StructureNode("part2", "Part", "Part", page=1, children=[fig_with_attr])
        root_good = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[part_good])
        doc_good = PDFDocumentModel(
            filepath="", filename="fig_block_pass.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_good
        )
        res_good = rule.evaluate(doc_good)
        assert not any(r.status == CheckStatus.FAIL and "Placement=Block" in r.message for r in res_good)

        # Case 3: Figure inline inside Paragraph P (Must PASS)
        fig_inline = StructureNode("fig3", "Figure", "Figure", page=1)
        p_node = StructureNode("p1", "P", "P", page=1, children=[fig_inline])
        doc_p = StructureNode("d1", "Document", "Document", page=1, children=[p_node])
        root_p = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[doc_p])
        doc_inline = PDFDocumentModel(
            filepath="", filename="fig_inline_pass.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_p
        )
        res_inline = rule.evaluate(doc_inline)
        assert not any(r.status == CheckStatus.FAIL for r in res_inline)

    def test_struct_elem_missing_pg_with_mcid(self):
        rule = StructureNestingRule()

        # Structure element with MCIDs but no page reference /Pg
        node_no_pg = StructureNode(
            "span1", "Span", "Span", page=None, mcids=[0], has_pg_attr=False
        )
        p_node = StructureNode("p1", "P", "P", page=1, children=[node_no_pg])
        root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[p_node])
        doc = PDFDocumentModel(
            filepath="", filename="missing_pg.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        res = rule.evaluate(doc)
        assert any(r.status == CheckStatus.FAIL and "/Pg" in r.message for r in res)

    def test_struct_elem_artifact_in_tree(self):
        rule = StructureNestingRule()

        # Artifact node placed in structure tree (Matterhorn 01-001)
        art_node = StructureNode("art1", "Artifact", "Artifact", page=1, is_artifact=True)
        root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[art_node])
        doc = PDFDocumentModel(
            filepath="", filename="art_in_tree.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )
        res = rule.evaluate(doc)
        assert any(r.status == CheckStatus.FAIL and "Artifact" in r.message for r in res)

    def test_list_nesting_rule(self):
        rule = StructureNestingRule()

        # Case 1: LI contains invalid child (e.g. Table directly inside LI without LBody)
        tbl = StructureNode("t1", "Table", "Table", page=1)
        li_bad = StructureNode("li1", "LI", "LI", page=1, children=[tbl])
        l_bad = StructureNode("l1", "L", "L", page=1, children=[li_bad])
        root_bad = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[l_bad])

        doc_bad = PDFDocumentModel(
            filepath="", filename="bad_list.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_bad
        )
        res_bad = rule.evaluate(doc_bad)
        assert any(r.status == CheckStatus.FAIL and "LI" in r.message for r in res_bad)

        # Case 2: LI correctly contains Lbl and LBody
        lbl = StructureNode("lbl1", "Lbl", "Lbl", page=1, text_content="1.")
        lbody = StructureNode("lb1", "LBody", "LBody", page=1, text_content="First item")
        li_good = StructureNode("li2", "LI", "LI", page=1, children=[lbl, lbody])
        l_good = StructureNode("l2", "L", "L", page=1, children=[li_good])
        root_good = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[l_good])

        doc_good = PDFDocumentModel(
            filepath="", filename="good_list.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_good
        )
        res_good = rule.evaluate(doc_good)
        assert any(r.status == CheckStatus.PASS for r in res_good)

    def test_table_nesting_rule(self):
        rule = StructureNestingRule()

        # Case 1: Table contains invalid child (e.g. Span directly inside Table without TR)
        span = StructureNode("sp1", "Span", "Span", page=1, text_content="Bad text")
        tbl_bad = StructureNode("t_bad", "Table", "Table", page=1, children=[span])
        root_bad = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[tbl_bad])

        doc_bad = PDFDocumentModel(
            filepath="", filename="bad_table.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_bad
        )
        res_bad = rule.evaluate(doc_bad)
        assert any(r.status == CheckStatus.FAIL and "Table" in r.message for r in res_bad)

        # Case 2: Valid Table -> TR -> TH, TD
        th = StructureNode("th1", "TH", "TH", page=1, text_content="Header")
        td = StructureNode("td1", "TD", "TD", page=1, text_content="Cell")
        tr1 = StructureNode("tr1", "TR", "TR", page=1, children=[th])
        tr2 = StructureNode("tr2", "TR", "TR", page=1, children=[td])
        tbl_good = StructureNode("t_good", "Table", "Table", page=1, children=[tr1, tr2])
        doc_node = StructureNode("d1", "Document", "Document", page=1, children=[tbl_good])
        root_good = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[doc_node])

        doc_good = PDFDocumentModel(
            filepath="", filename="good_table.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_good
        )
        res_good = rule.evaluate(doc_good)
        assert not any(r.status == CheckStatus.FAIL for r in res_good)

    def test_empty_structure_elements_rule(self):
        rule = EmptyStructureElementsRule()

        # Case 1: Empty leaf P node with no text, no MCID, no children
        empty_p = StructureNode("p_empty", "P", "P", page=1, children=[], mcids=[], text_content="")
        root_empty = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[empty_p])
        doc_empty = PDFDocumentModel(
            filepath="", filename="empty_p.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_empty
        )
        res_empty = rule.evaluate(doc_empty)
        assert any(r.status == CheckStatus.FAIL and "empty" in r.message.lower() for r in res_empty)

        # Case 2: Non-empty leaf node
        valid_p = StructureNode("p_valid", "P", "P", page=1, text_content="Hello world")
        root_valid = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[valid_p])
        doc_valid = PDFDocumentModel(
            filepath="", filename="valid_p.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_valid
        )
        res_valid = rule.evaluate(doc_valid)
        assert len(res_valid) == 1
        assert res_valid[0].status == CheckStatus.PASS

    def test_figure_explicit_bbox_rule(self):
        rule = FigureBoundingBoxRule()

        # Case 1: Multi-page figure spanning pages 1 and 2 without BBox attributes (BBox is optional per ISO 14289-1)
        fig_child1 = StructureNode("fig_p1", "Figure", "Figure", page=1)
        fig_child2 = StructureNode("fig_p2", "Figure", "Figure", page=2)
        fig_multipage = StructureNode(
            "fig_multi", "Figure", "Figure", page=1, children=[fig_child1, fig_child2],
            has_explicit_bbox=False, attributes={}
        )
        root_multi = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[fig_multipage])
        doc_multi = PDFDocumentModel(
            filepath="", filename="multi_page_fig.pdf", filesize=100, pdf_version="1.7",
            page_count=2, is_tagged=True, structure_tree=root_multi
        )
        res_multi = rule.evaluate(doc_multi)
        assert all(r.status == CheckStatus.PASS for r in res_multi)

        # Case 2: Figure with malformed /BBox attribute (Matterhorn 16-001)
        fig_malformed = StructureNode(
            "fig_mal", "Figure", "Figure", page=1, has_explicit_bbox=True,
            attributes={"BBox": [50.0, 100.0]}  # Only 2 numbers instead of 4
        )
        root_malformed = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[fig_malformed])
        doc_malformed = PDFDocumentModel(
            filepath="", filename="malformed_bbox.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_malformed
        )
        res_malformed = rule.evaluate(doc_malformed)
        assert any(r.status == CheckStatus.FAIL and "invalid" in r.message.lower() for r in res_malformed)

        # Case 3: Figure with valid explicit /BBox in attribute dictionary
        fig_bbox = StructureNode(
            "fig2", "Figure", "Figure", page=1, has_explicit_bbox=True,
            attributes={"BBox": [50.0, 100.0, 250.0, 300.0]}
        )
        root_bbox = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[fig_bbox])
        doc_bbox = PDFDocumentModel(
            filepath="", filename="with_bbox.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_bbox
        )
        res_yes = rule.evaluate(doc_bbox)
        assert any(r.status == CheckStatus.PASS for r in res_yes)

        # Case 4: Standard single-page figure without explicit /BBox (valid under PDF/UA-1 Clause 7.18)
        fig_single = StructureNode("fig_single", "Figure", "Figure", page=1, has_explicit_bbox=False, attributes={})
        root_single = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[fig_single])
        doc_single = PDFDocumentModel(
            filepath="", filename="single_fig.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_single
        )
        res_single = rule.evaluate(doc_single)
        assert any(r.status == CheckStatus.PASS for r in res_single)

        # Case 5: Single-page figure with empty /BBox [] (unspecified layout attribute, valid under PDF/UA-1)
        fig_empty_bbox = StructureNode(
            "fig_empty", "Figure", "Figure", page=1, has_explicit_bbox=False,
            attributes={"BBox": [], "O": "/Layout", "Placement": "/Block"}
        )
        root_empty_bbox = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[fig_empty_bbox])
        doc_empty_bbox = PDFDocumentModel(
            filepath="", filename="empty_bbox_fig.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_empty_bbox
        )
        res_empty = rule.evaluate(doc_empty_bbox)
        assert any(r.status == CheckStatus.PASS for r in res_empty)

        # Case 6: Single-page figure with non-numeric malformed BBox (Matterhorn 16-001)
        fig_non_num = StructureNode(
            "fig_non_num", "Figure", "Figure", page=1, has_explicit_bbox=True,
            attributes={"BBox": ["a", "b", "c", "d"]}
        )
        root_non_num = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[fig_non_num])
        doc_non_num = PDFDocumentModel(
            filepath="", filename="non_num_bbox.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_non_num
        )
        res_non_num = rule.evaluate(doc_non_num)
        assert any(r.status == CheckStatus.FAIL and "invalid" in r.message.lower() for r in res_non_num)

        # Case 7: Real PDF12.pdf integration test (verifies 0 false positive BBox failures)
        import os
        from src.pdf_inspector.core.document_parser import DocumentParser
        pdf12_path = os.path.join("test_corpus", "ALL FILES", "PDF12.pdf")
        if os.path.exists(pdf12_path):
            doc12 = DocumentParser(pdf12_path).parse()
            res12 = rule.evaluate(doc12)
            assert not any(r.status == CheckStatus.FAIL for r in res12)
            assert any(r.status == CheckStatus.PASS for r in res12)
