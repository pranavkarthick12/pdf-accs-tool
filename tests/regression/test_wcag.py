"""
Regression tests for WCAG 2.1/2.2 AA Rules:
- WCAG 1.1 Text Alternatives (WCAGTextAlternativesRule)
- WCAG 2.4 Navigable (WCAGNavigableRule)
- WCAG 3.1 Readable (WCAGReadableRule)
- WCAG 3.3 Input Assistance (WCAGInputAssistanceRule)
- WCAG 4.1 Compatible (WCAGCompatibleRule)
"""

import pytest
from src.pdf_inspector.core.models import (
    PDFDocumentModel, StructureNode, ImageModel, LinkModel, FormFieldModel,
    AnnotationModel, CheckStatus, Severity, PageModel
)
from src.pdf_inspector.engine.wcag.wcag_rules import (
    WCAGTextAlternativesRule,
    WCAGDistinguishableRule,
    WCAGNavigableRule,
    WCAGReadableRule,
    WCAGInputAssistanceRule,
    WCAGCompatibleRule,
)


class TestWCAGRegression:
    def test_wcag_navigable_title_and_display(self):
        rule = WCAGNavigableRule()

        # Case 1: Document has no title at all -> SC 2.4.2 FAIL
        doc_no_title = PDFDocumentModel(
            filepath="", filename="notitle.pdf", filesize=100, pdf_version="1.7",
            page_count=1, title=None, xmp_dc_title=None, doc_info_title=None
        )
        res1 = rule.evaluate(doc_no_title)
        assert any(r.status == CheckStatus.FAIL and "Title" in r.message for r in res1)

        # Case 2: Document has title, but DisplayDocTitle is False -> SC 2.4.2 FAIL (per PAC / WCAG SC 2.4.2)
        doc_title_no_disp = PDFDocumentModel(
            filepath="", filename="titled.pdf", filesize=100, pdf_version="1.7",
            page_count=1, title="Test Report", xmp_dc_title="Test Report",
            display_doc_title=False
        )
        res2 = rule.evaluate(doc_title_no_disp)
        assert any(r.status in (CheckStatus.FAIL, CheckStatus.WARNING) and "DisplayDocTitle" in r.message for r in res2)

        # Case 3: Document has title and DisplayDocTitle is True -> SC 2.4.2 PASS
        doc_full_title = PDFDocumentModel(
            filepath="", filename="titled.pdf", filesize=100, pdf_version="1.7",
            page_count=1, title="Test Report", xmp_dc_title="Test Report",
            display_doc_title=True
        )
        res3 = rule.evaluate(doc_full_title)
        assert any(r.status == CheckStatus.PASS and "title" in r.message.lower() for r in res3)

    def test_wcag_navigable_tab_order(self):
        """Pages with interactive annotations must specify /Tabs /S (SC 2.4.3 Focus Order)."""
        rule = WCAGNavigableRule()
        p1 = PageModel(page_number=1, width=612, height=792, tab_order_mode="None")
        link_bad = LinkModel(id="l1", page=1, text="click here", uri="https://example.com", bbox=(10, 10, 50, 20))
        doc_bad_tab = PDFDocumentModel(
            filepath="", filename="link.pdf", filesize=100, pdf_version="1.7",
            page_count=1, pages=[p1], title="Links", xmp_dc_title="Links", display_doc_title=True,
            links=[link_bad]
        )
        res = rule.evaluate(doc_bad_tab)
        assert any(r.status == CheckStatus.FAIL and "tab order" in r.message.lower() for r in res)

    def test_wcag_compatible_rule(self):
        rule = WCAGCompatibleRule()

        # Case 1: Untagged document with interactive controls -> FAIL
        link_bad = LinkModel(id="l1", page=1, text="Click", uri="https://example.com")
        doc_untagged = PDFDocumentModel(
            filepath="", filename="untagged.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=False, structure_tree=None, links=[link_bad]
        )
        res_untagged = rule.evaluate(doc_untagged)
        assert any(r.status == CheckStatus.FAIL and "untagged" in r.message.lower() for r in res_untagged)

        # Case 2: Circular role mapping -> FAIL
        root_circ = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[
            StructureNode("c1", "CustomA", "CustomA", page=1)
        ])
        doc_circ = PDFDocumentModel(
            filepath="", filename="circ.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_circ,
            role_map={"CustomA": "CustomB", "CustomB": "CustomA"}
        )
        res_circ = rule.evaluate(doc_circ)
        assert any(r.status == CheckStatus.FAIL and "Circular" in r.message for r in res_circ)

        # Case 3: Non-standard unmapped role -> WARNING
        root_unmapped = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[
            StructureNode("c1", "MySpecialTag", "MySpecialTag", page=1)
        ])
        doc_unmapped = PDFDocumentModel(
            filepath="", filename="unmapped.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_unmapped,
            role_map={}
        )
        res_unmapped = rule.evaluate(doc_unmapped)
        assert any(r.status == CheckStatus.WARNING and "Non-standard structure" in r.message for r in res_unmapped)

        # Case 4: Semantically incompatible role mapping (e.g. InlineShape -> Sect) -> WARNING
        root_mapped = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[
            StructureNode("s1", "InlineShape", "Sect", page=1)
        ])
        doc_incompat = PDFDocumentModel(
            filepath="", filename="incompat_role.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_mapped,
            role_map={"InlineShape": "Sect"}
        )
        res_incompat = rule.evaluate(doc_incompat)
        assert any(r.status == CheckStatus.WARNING and "semantically incompatible" in r.message.lower() for r in res_incompat)

        # Case 5: Document with accessible link -> PASS
        root_ok = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[
            StructureNode("p1", "P", "P", page=1)
        ])
        link_ok = LinkModel(id="l1", page=1, text="Home Page", uri="https://example.com")
        doc_ok = PDFDocumentModel(
            filepath="", filename="ok.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root_ok, links=[link_ok]
        )
        res_ok = rule.evaluate(doc_ok)
        assert any(r.status == CheckStatus.PASS for r in res_ok)

    def test_wcag_text_alternatives(self):
        rule = WCAGTextAlternativesRule()

        img_no_alt = ImageModel("img1", 1, (10, 10, 100, 100), 100, 100, "RGB", has_alt=False, is_artifact=False)
        doc_bad = PDFDocumentModel(
            filepath="", filename="i.pdf", filesize=100, pdf_version="1.7", page_count=1,
            images=[img_no_alt]
        )
        res_bad = rule.evaluate(doc_bad)
        assert any(r.status == CheckStatus.FAIL for r in res_bad)

        img_alt = ImageModel("img2", 1, (10, 10, 100, 100), 100, 100, "RGB", has_alt=True, alt_text="Sales chart")
        doc_good = PDFDocumentModel(
            filepath="", filename="i.pdf", filesize=100, pdf_version="1.7", page_count=1,
            images=[img_alt]
        )
        res_good = rule.evaluate(doc_good)
        assert any(r.status == CheckStatus.PASS for r in res_good)

    def test_wcag_distinguishable_contrast(self):
        rule = WCAGDistinguishableRule()

        # Case 1: Untagged document with no text -> returns empty list (renders as '- | - | -' in UI)
        doc_empty = PDFDocumentModel(
            filepath="", filename="empty.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=False
        )
        assert rule.evaluate(doc_empty) == []

        # Case 2: Compliant text (Black on White, ratio 21:1 >= 4.5:1) -> CheckStatus.PASS
        p_good = PageModel(
            page_number=1, width=612, height=792, text="Accessible text",
            text_spans=[{"text": "Accessible text", "color": (0, 0, 0), "bg_color": (255, 255, 255), "size": 12.0}]
        )
        doc_good = PDFDocumentModel(
            filepath="", filename="good.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True, pages=[p_good]
        )
        res_good = rule.evaluate(doc_good)
        assert any(r.status == CheckStatus.PASS for r in res_good)
        assert not any(r.status == CheckStatus.FAIL for r in res_good)

        # Case 3: Low contrast text (Light Gray on White, ratio ~1.9:1 < 4.5:1) -> CheckStatus.FAIL with diagnostics
        p_bad = PageModel(
            page_number=2, width=612, height=792, text="Faint text",
            text_spans=[{"text": "Faint text", "color": (200, 200, 200), "bg_color": (255, 255, 255), "size": 11.0}]
        )
        doc_bad = PDFDocumentModel(
            filepath="", filename="bad.pdf", filesize=100, pdf_version="1.7",
            page_count=2, is_tagged=True, pages=[p_bad]
        )
        res_bad = rule.evaluate(doc_bad)
        fails = [r for r in res_bad if r.status == CheckStatus.FAIL]
        assert len(fails) >= 1
        assert fails[0].page == 2
        assert "insufficient contrast" in fails[0].message.lower()
