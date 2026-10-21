"""
Comprehensive unit tests for the object-level WCAG 2.1 / 2.2 AA Rules Suite.
Validates individual object evaluations, non-text element alternative text checking,
zero-applicable object behavior, and checkpoint aggregation across synthetic PDF models.
"""

import pytest
from src.pdf_inspector.core.models import (
    PDFDocumentModel, StructureNode, PageModel, ImageModel,
    TableModel, LinkModel, FormFieldModel, FontModel, AnnotationModel,
    CheckStatus
)
from src.pdf_inspector.engine.wcag.wcag_rules import (
    WCAGTextAlternativesRule,
    WCAGTimeBasedMediaRule,
    WCAGAdaptableRule,
    WCAGDistinguishableRule,
    WCAGKeyboardAccessibleRule,
    WCAGEnoughTimeRule,
    WCAGSeizuresRule,
    WCAGNavigableRule,
    WCAGInputModalitiesRule,
    WCAGReadableRule,
    WCAGPredictableRule,
    WCAGInputAssistanceRule,
    WCAGCompatibleRule,
)
from src.pdf_inspector.engine.runner import AuditRunner


def test_wcag_1_1_zero_figures():
    """A. PDF with zero Figures or Formulas returns empty list (0 evaluations)."""
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    p = StructureNode("p1", "P", "P", text_content="Simple paragraph")
    root.children.append(p)
    doc = PDFDocumentModel(
        filepath="", filename="zero_fig.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    rule = WCAGTextAlternativesRule()
    results = rule.evaluate(doc)
    assert len(results) == 0


def test_wcag_1_1_one_figure_with_alt():
    """B. PDF with one Figure + Alt -> 1 PASS."""
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    fig = StructureNode("fig1", "Figure", "Figure", alt_text="Bar chart of sales 2026", page=1)
    root.children.append(fig)
    doc = PDFDocumentModel(
        filepath="", filename="fig_alt.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    rule = WCAGTextAlternativesRule()
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS
    assert "Alternative text is present" in results[0].message


def test_wcag_1_1_one_figure_without_alt():
    """C. PDF with one Figure without Alt -> 1 FAIL."""
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    fig = StructureNode("fig1", "Figure", "Figure", alt_text=None, actual_text=None, page=1)
    root.children.append(fig)
    doc = PDFDocumentModel(
        filepath="", filename="fig_no_alt.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    rule = WCAGTextAlternativesRule()
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.FAIL
    assert "lacks a text alternative" in results[0].message


def test_wcag_1_1_many_figures_aggregation():
    """D. PDF with many Figures (3 figures: 2 with Alt, 1 without) -> 2 PASS, 1 FAIL."""
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    fig1 = StructureNode("fig1", "Figure", "Figure", alt_text="Diagram A", page=1)
    fig2 = StructureNode("fig2", "Figure", "Figure", alt_text="Diagram B", page=2)
    fig3 = StructureNode("fig3", "Figure", "Figure", alt_text=None, page=3)
    root.children.extend([fig1, fig2, fig3])
    doc = PDFDocumentModel(
        filepath="", filename="multi_fig.pdf", filesize=100, pdf_version="1.7",
        page_count=3, is_tagged=True, structure_tree=root
    )
    runner = AuditRunner(custom_rules=[WCAGTextAlternativesRule()])
    report = runner.run(doc)
    counts = report.get_category_counts("WCAG")["1.1 Text Alternatives"]
    assert counts["passed"] == 2
    assert counts["failed"] == 1


def test_wcag_1_1_formula_with_alt_and_actualtext():
    """E. Formula with Alt or ActualText -> PASS."""
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    form1 = StructureNode("form1", "Formula", "Formula", alt_text="E = mc^2", page=1)
    form2 = StructureNode("form2", "Formula", "Formula", actual_text="a^2 + b^2 = c^2", page=1)
    root.children.extend([form1, form2])
    doc = PDFDocumentModel(
        filepath="", filename="formula_alt.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    rule = WCAGTextAlternativesRule()
    results = rule.evaluate(doc)
    assert len(results) == 2
    assert all(r.status == CheckStatus.PASS for r in results)


def test_wcag_1_1_formula_without_alt():
    """F. Formula without Alt/ActualText -> FAIL."""
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    form = StructureNode("form1", "Formula", "Formula", alt_text="", actual_text=None, page=2)
    root.children.append(form)
    doc = PDFDocumentModel(
        filepath="", filename="formula_no_alt.pdf", filesize=100, pdf_version="1.7",
        page_count=2, is_tagged=True, structure_tree=root
    )
    rule = WCAGTextAlternativesRule()
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].status == CheckStatus.FAIL


def test_wcag_1_1_mixed_figures_and_formulas():
    """G. Mixed Figures (2 PASS, 1 FAIL) and Formulas (3 PASS, 2 FAIL) -> 5 PASS, 3 FAIL."""
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    # Figures
    f1 = StructureNode("f1", "Figure", "Figure", alt_text="Fig 1", page=1)
    f2 = StructureNode("f2", "Figure", "Figure", alt_text="Fig 2", page=1)
    f3 = StructureNode("f3", "Figure", "Figure", alt_text=None, page=1)
    # Formulas
    m1 = StructureNode("m1", "Formula", "Formula", alt_text="Math 1", page=2)
    m2 = StructureNode("m2", "Formula", "Formula", actual_text="Math 2", page=2)
    m3 = StructureNode("m3", "Formula", "Formula", alt_text="Math 3", page=2)
    m4 = StructureNode("m4", "Formula", "Formula", alt_text=None, page=2)
    m5 = StructureNode("m5", "Formula", "Formula", actual_text=" ", page=2)

    root.children.extend([f1, f2, f3, m1, m2, m3, m4, m5])
    doc = PDFDocumentModel(
        filepath="", filename="mixed.pdf", filesize=100, pdf_version="1.7",
        page_count=2, is_tagged=True, structure_tree=root
    )
    runner = AuditRunner(custom_rules=[WCAGTextAlternativesRule()])
    report = runner.run(doc)
    counts = report.get_category_counts("WCAG")["1.1 Text Alternatives"]
    assert counts["passed"] == 5
    assert counts["failed"] == 3


def test_wcag_1_1_decorative_artifacts_excluded():
    """H. Decorative/artifact graphics are excluded from text alternative evaluation."""
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    art_fig = StructureNode("art1", "Figure", "Figure", is_artifact=True, page=1)
    real_fig = StructureNode("fig1", "Figure", "Figure", alt_text="Real Figure", page=1)
    root.children.extend([art_fig, real_fig])
    doc = PDFDocumentModel(
        filepath="", filename="artifacts.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, structure_tree=root
    )
    rule = WCAGTextAlternativesRule()
    results = rule.evaluate(doc)
    assert len(results) == 1
    assert results[0].object_reference == "<Figure id='fig1'>"
    assert results[0].status == CheckStatus.PASS


def test_wcag_1_3_adaptable_headings_lists_tables():
    """I, J, K. Evaluates structured Headings, List items, and Tables individually."""
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    h1 = StructureNode("h1", "H1", "H1", page=1)
    h2 = StructureNode("h2", "H2", "H2", page=1)

    # Valid LI: contains Lbl and LBody
    li_valid = StructureNode("li1", "LI", "LI", page=1)
    lbl = StructureNode("lbl1", "Lbl", "Lbl", page=1)
    lbody = StructureNode("lb1", "LBody", "LBody", page=1)
    li_valid.children.extend([lbl, lbody])

    # Invalid LI: contains Span directly
    li_invalid = StructureNode("li2", "LI", "LI", page=1)
    span = StructureNode("sp1", "Span", "Span", page=1)
    li_invalid.children.append(span)

    root.children.extend([h1, h2, li_valid, li_invalid])

    table1 = TableModel(id="tbl1", page=1, rows_count=3, cols_count=3, has_headers=True, header_cells_count=3, data_cells_count=6)
    table2 = TableModel(id="tbl2", page=2, rows_count=2, cols_count=2, has_headers=False, header_cells_count=0, data_cells_count=4)

    doc = PDFDocumentModel(
        filepath="", filename="adaptable.pdf", filesize=100, pdf_version="1.7",
        page_count=2, is_tagged=True, structure_tree=root, tables=[table1, table2]
    )

    rule = WCAGAdaptableRule()
    results = rule.evaluate(doc)

    # Tables: 1 PASS (tbl1), 1 FAIL (tbl2)
    # Headings: 2 PASS (h1, h2)
    # Lists: 1 PASS (li_valid), 1 FAIL (li_invalid)
    tbl_passes = [r for r in results if "Table" in r.message and r.status == CheckStatus.PASS]
    tbl_fails = [r for r in results if "Table" in r.message and r.status == CheckStatus.FAIL]
    head_passes = [r for r in results if "heading" in r.message.lower() and r.status == CheckStatus.PASS]
    li_passes = [r for r in results if "List item <LI>" in r.message and r.status == CheckStatus.PASS]
    li_fails = [r for r in results if "invalid child" in r.message and r.status == CheckStatus.FAIL]

    assert len(tbl_passes) == 1
    assert len(tbl_fails) == 1
    assert len(head_passes) == 2
    assert len(li_passes) == 1
    assert len(li_fails) == 1


def test_wcag_2_1_keyboard_and_tab_order():
    """L, M. Tab order evaluated per page containing interactive links or form fields."""
    p1 = PageModel(page_number=1, width=612, height=792, tab_order_mode="S")
    p2 = PageModel(page_number=2, width=612, height=792, tab_order_mode="None")
    p3 = PageModel(page_number=3, width=612, height=792, tab_order_mode="None")  # No interactive elements

    link1 = LinkModel(id="l1", page=1, text="Visit Website", uri="https://example.com")
    link2 = LinkModel(id="l2", page=2, text="Contact Us", uri="https://example.com/contact")

    doc = PDFDocumentModel(
        filepath="", filename="keyboard.pdf", filesize=100, pdf_version="1.7",
        page_count=3, is_tagged=True, pages=[p1, p2, p3], links=[link1, link2]
    )

    rule_2_1 = WCAGKeyboardAccessibleRule()
    results_2_1 = rule_2_1.evaluate(doc)
    # WCAG 2.1 has zero machine checks in PAC
    assert len(results_2_1) == 0

    # Tab order is evaluated under 2.4 Navigable (SC 2.4.3 Focus Order)
    rule_2_4 = WCAGNavigableRule()
    results_2_4 = rule_2_4.evaluate(doc)
    tab_fails = [r for r in results_2_4 if r.page == 2 and r.status == CheckStatus.FAIL]
    assert len(tab_fails) == 1


def test_wcag_3_3_form_fields_tooltip():
    """N. Form fields evaluated individually for accessible description (/TU)."""
    f1 = FormFieldModel(name="FirstName", field_type="Text", tooltip="Enter your first name", page=1)
    f2 = FormFieldModel(name="LastName", field_type="Text", tooltip="", page=1)

    doc = PDFDocumentModel(
        filepath="", filename="forms.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, form_fields=[f1, f2]
    )

    # In PAC, FormFieldHasTUKey is evaluated under 1.1 Text Alternatives
    rule_1_1 = WCAGTextAlternativesRule()
    results_1_1 = rule_1_1.evaluate(doc)
    form_results = [r for r in results_1_1 if "FormField" in r.object_reference]
    assert len(form_results) == 2
    assert form_results[0].status == CheckStatus.PASS
    assert form_results[1].status == CheckStatus.FAIL

    # 3.3 Input Assistance returns empty list (0 machine checks in PAC)
    rule_3_3 = WCAGInputAssistanceRule()
    results_3_3 = rule_3_3.evaluate(doc)
    assert len(results_3_3) == 0


def test_wcag_3_1_language_and_switches():
    """O, P. Document language and language switch spans evaluated."""
    root = StructureNode("root", "StructTreeRoot", "StructTreeRoot")
    span_fr = StructureNode("sp1", "Span", "Span", lang="fr-FR", page=1)
    root.children.append(span_fr)

    doc = PDFDocumentModel(
        filepath="", filename="lang.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, language="en-US", structure_tree=root
    )

    rule = WCAGReadableRule()
    results = rule.evaluate(doc)

    assert len(results) == 2
    assert results[0].status == CheckStatus.PASS and "en-US" in results[0].message
    assert results[1].status == CheckStatus.PASS and "fr-FR" in results[1].message


def test_wcag_1_4_distinguishable_empty_not_applicable():
    """Empty or untagged documents without text content return empty list (renders as '- | - | -' in UI)."""
    doc = PDFDocumentModel(
        filepath="", filename="empty.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=False
    )
    rule = WCAGDistinguishableRule()
    results = rule.evaluate(doc)
    assert results == []


def test_wcag_1_4_distinguishable_valid_contrast_pass():
    """Text with compliant contrast against background returns CheckStatus.PASS."""
    p1 = PageModel(
        page_number=1, width=612, height=792,
        text="Compliant Black on White Text",
        text_spans=[
            {"text": "Compliant Black on White Text", "color": (0, 0, 0), "bg_color": (255, 255, 255), "size": 12.0}
        ]
    )
    doc = PDFDocumentModel(
        filepath="", filename="compliant.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, pages=[p1]
    )
    rule = WCAGDistinguishableRule()
    results = rule.evaluate(doc)
    assert any(r.status == CheckStatus.PASS for r in results)
    assert not any(r.status == CheckStatus.FAIL for r in results)


def test_wcag_1_4_distinguishable_low_contrast_fail():
    """Text with low contrast (< 4.5:1 standard) produces CheckStatus.FAIL with diagnostics."""
    p1 = PageModel(
        page_number=1, width=612, height=792,
        text="Light Gray Text",
        text_spans=[
            {"text": "Light Gray Text", "color": (180, 180, 180), "bg_color": (255, 255, 255), "size": 11.0}
        ]
    )
    doc = PDFDocumentModel(
        filepath="", filename="low_contrast.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, pages=[p1]
    )
    rule = WCAGDistinguishableRule()
    results = rule.evaluate(doc)
    fail_results = [r for r in results if r.status == CheckStatus.FAIL]
    assert len(fail_results) >= 1
    assert "insufficient contrast" in fail_results[0].message.lower()
    assert fail_results[0].page == 1


def test_wcag_1_4_distinguishable_large_text_threshold():
    """Large text (18pt+ or 14pt+ bold) uses 3.0:1 threshold instead of 4.5:1."""
    # Color #767676 on white has contrast ~4.54:1 (passes 4.5:1).
    # Color #888888 on white has contrast ~3.54:1 (fails 4.5:1, but passes 3.0:1 large text threshold).
    p1 = PageModel(
        page_number=1, width=612, height=792,
        text="Large Heading",
        text_spans=[
            {"text": "Large Heading", "color": (136, 136, 136), "bg_color": (255, 255, 255), "size": 18.0, "is_bold": False}
        ]
    )
    doc = PDFDocumentModel(
        filepath="", filename="large_text.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, pages=[p1]
    )
    rule = WCAGDistinguishableRule()
    results = rule.evaluate(doc)
    assert any(r.status == CheckStatus.PASS for r in results)
    assert not any(r.status == CheckStatus.FAIL for r in results)
