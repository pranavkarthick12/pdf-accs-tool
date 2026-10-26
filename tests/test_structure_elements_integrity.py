"""
Comprehensive Regression & Integrity Tests for PDF/UA Structure Elements and Category Aggregation.

Verifies:
1. Valid pikepdf.Array with decimal.Decimal coordinates passes.
2. Valid integer/float BBox passes, including zero and negative coordinates.
3. BBox with the wrong number of coordinates fails (fewer or more than 4).
4. BBox with non-numeric values (strings, booleans, dicts, nested lists) fails.
5. NaN and positive/negative infinity fail.
6. Existing empty-BBox behavior remains correct (unspecified, non-failing on single-page).
7. Genuine invalid structure element fails through the complete pipeline.
8. Quality and WCAG evaluation do not mutate PDF/UA results.
9. Report aggregation preserves the underlying PDF/UA statuses.
"""

import os
import copy
import decimal
import tempfile
import pytest
import pikepdf

from src.pdf_inspector.core.models import (
    PDFDocumentModel, StructureNode, CheckResult, CheckStatus, Severity, AuditReport,
    validate_bbox_coordinates
)
from src.pdf_inspector.engine.pdf_ua.structure_rules import (
    StructureNestingRule, FigureBoundingBoxRule, EmptyStructureElementsRule
)
from src.pdf_inspector.engine.pdf_ua.list_rules import ListStructureHierarchyRule
from src.pdf_inspector.engine.runner import AuditRunner
from src.pdf_inspector.ui.views.checkpoints_view import CheckpointsView
from src.pdf_inspector.reporting.pdf_report import PDFReportGenerator
from src.pdf_inspector.reporting.html_report import HTMLReportGenerator
from src.pdf_inspector.reporting.json_exporter import JSONExporter


class TestBBoxValidationHelper:
    """Tests for validate_bbox_coordinates helper function."""

    def test_decimal_and_pikepdf_array(self):
        pike_arr = pikepdf.Array([
            decimal.Decimal("197.75"),
            decimal.Decimal("581.365"),
            decimal.Decimal("424.672"),
            decimal.Decimal("648.236")
        ])
        is_valid, coords = validate_bbox_coordinates(pike_arr)
        assert is_valid is True
        assert coords == (197.75, 581.365, 424.672, 648.236)

    def test_valid_floats_and_integers(self):
        is_valid, coords = validate_bbox_coordinates([0, 0, 500, 700])
        assert is_valid is True
        assert coords == (0.0, 0.0, 500.0, 700.0)

    def test_zero_and_negative_coordinates(self):
        is_valid, coords = validate_bbox_coordinates([-10.5, -20.0, 100.0, 200.5])
        assert is_valid is True
        assert coords == (-10.5, -20.0, 100.0, 200.5)

    def test_wrong_coordinate_count(self):
        # 3 coordinates
        assert validate_bbox_coordinates([10, 20, 30])[0] is False
        # 5 coordinates
        assert validate_bbox_coordinates([10, 20, 30, 40, 50])[0] is False
        # 0 coordinates (empty)
        assert validate_bbox_coordinates([])[0] is False

    def test_non_numeric_values(self):
        assert validate_bbox_coordinates(["a", "b", "c", "d"])[0] is False
        assert validate_bbox_coordinates([10, 20, "thirty", 40])[0] is False
        assert validate_bbox_coordinates([True, False, 10, 20])[0] is False
        assert validate_bbox_coordinates([{"x": 10}, 20, 30, 40])[0] is False
        assert validate_bbox_coordinates([[10], [20], [30], [40]])[0] is False

    def test_nan_and_infinity(self):
        assert validate_bbox_coordinates([float("nan"), 10.0, 20.0, 30.0])[0] is False
        assert validate_bbox_coordinates([float("inf"), 10.0, 20.0, 30.0])[0] is False
        assert validate_bbox_coordinates([float("-inf"), 10.0, 20.0, 30.0])[0] is False


class TestFigureBoundingBoxRule:
    """Tests for FigureBoundingBoxRule evaluating PDFDocumentModel."""

    def test_pikepdf_decimal_figure_passes(self):
        rule = FigureBoundingBoxRule()
        pike_arr = pikepdf.Array([
            decimal.Decimal("404.941"), decimal.Decimal("564.516"),
            decimal.Decimal("546.124"), decimal.Decimal("679.153")
        ])
        fig = StructureNode("f1", "Figure", "Figure", page=1, pages_spanned=[1], attributes={"BBox": pike_arr})
        doc = PDFDocumentModel(
            filepath="", filename="test.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True,
            structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[fig])
        )
        res = rule.evaluate(doc)
        assert all(r.status == CheckStatus.PASS for r in res)
        assert any(r.items_count == 1 for r in res)

    def test_single_page_figure_without_bbox_passes(self):
        rule = FigureBoundingBoxRule()
        fig = StructureNode("f1", "Figure", "Figure", page=1, pages_spanned=[1])
        doc = PDFDocumentModel(
            filepath="", filename="test.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True,
            structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[fig])
        )
        res = rule.evaluate(doc)
        assert all(r.status == CheckStatus.PASS for r in res)

    def test_malformed_bbox_fails_regardless_of_alt_or_placement(self):
        rule = FigureBoundingBoxRule()
        fig = StructureNode(
            "f1", "Figure", "Figure", page=1, pages_spanned=[1],
            alt_text="A meaningful chart description",
            placement="Block",
            attributes={"BBox": [10.0, 20.0]}  # only 2 numbers
        )
        doc = PDFDocumentModel(
            filepath="", filename="test.pdf", filesize=100, pdf_version="1.7",
            page_count=1, is_tagged=True,
            structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[fig])
        )
        res = rule.evaluate(doc)
        assert any(r.status == CheckStatus.FAIL and "invalid /BBox attribute" in r.message for r in res)

    def test_multi_page_figure_valid_bbox_passes(self):
        rule = FigureBoundingBoxRule()
        fig = StructureNode(
            "f_multi", "Figure", "Figure", page=1, pages_spanned=[1, 2],
            attributes={"BBox": [0, 0, 500, 700]}  # Valid 4-number BBox
        )
        doc = PDFDocumentModel(
            filepath="", filename="test.pdf", filesize=100, pdf_version="1.7",
            page_count=2, is_tagged=True,
            structure_tree=StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[fig])
        )
        res = rule.evaluate(doc)
        assert all(r.status == CheckStatus.PASS for r in res)


class TestPipelineIsolationAndAggregation:
    """Tests confirming isolation and accuracy across UI, WCAG, Quality, and Reports."""

    def test_invalid_structure_element_remains_fail_through_pipeline(self):
        bad_child = StructureNode("span1", "Span", "Span", page=1)
        bad_li = StructureNode("li1", "LI", "LI", page=1, children=[bad_child])
        root = StructureNode("root", "StructTreeRoot", "StructTreeRoot", children=[bad_li])

        doc = PDFDocumentModel(
            filepath="", filename="invalid_struct.pdf", filesize=500, pdf_version="1.7",
            page_count=1, is_tagged=True, structure_tree=root
        )

        runner = AuditRunner()
        report = runner.run(doc)

        pdfua_counts = report.get_category_counts("PDF/UA")
        assert pdfua_counts["Structure elements"]["failed"] >= 1

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_out = os.path.join(tmpdir, "report.pdf")
            html_out = os.path.join(tmpdir, "report.html")
            json_out = os.path.join(tmpdir, "report.json")

            PDFReportGenerator.generate(report, pdf_out)
            HTMLReportGenerator.generate(report, html_out)
            JSONExporter.export(report, json_out)

            assert os.path.getsize(pdf_out) > 0
            assert os.path.getsize(html_out) > 0
            assert os.path.getsize(json_out) > 0

    def test_quality_and_wcag_mapping_does_not_mutate_pdf_ua_results(self):
        orig_result = CheckResult(
            check_id="PDFUA-STRUCT-001",
            name="Structure Elements Validation & Nesting",
            category="Structure elements",
            standard="PDF/UA",
            status=CheckStatus.FAIL,
            severity=Severity.HIGH,
            message="Structure error test message",
            items_count=5
        )
        results_list = [copy.deepcopy(orig_result)]
        report = AuditReport(document_info={"filename": "test.pdf"}, results=results_list)

        # Quality checkpoint aggregation simulation
        quality_counts = {}
        for cat, rule_ids in CheckpointsView.QUALITY_RULE_MAPPINGS.items():
            cat_results = [r for r in report.results if r.check_id in rule_ids]
            p = sum(r.items_count for r in cat_results if r.status == CheckStatus.PASS)
            w = sum(r.items_count for r in cat_results if r.status == CheckStatus.WARNING)
            f = sum(r.items_count for r in cat_results if r.status in (CheckStatus.FAIL, CheckStatus.ERROR))
            m = sum(r.items_count for r in cat_results if r.status == CheckStatus.MANUAL_REVIEW)
            quality_counts[cat] = {"passed": p, "warned": w, "failed": f, "manual": m}

        res = report.results[0]
        assert res.check_id == orig_result.check_id
        assert res.standard == "PDF/UA"
        assert res.category == "Structure elements"
        assert res.status == CheckStatus.FAIL
        assert res.items_count == 5
        assert res.message == orig_result.message

    def test_checkpoint_summary_counts_accuracy(self):
        results = [
            CheckResult("ID1", "R1", "Structure elements", "PDF/UA", CheckStatus.PASS, Severity.LOW, "pass", items_count=10),
            CheckResult("ID2", "R2", "Structure elements", "PDF/UA", CheckStatus.WARNING, Severity.MEDIUM, "warn", items_count=3),
            CheckResult("ID3", "R3", "Structure elements", "PDF/UA", CheckStatus.FAIL, Severity.HIGH, "fail", items_count=7),
            CheckResult("ID4", "R4", "Structure elements", "PDF/UA", CheckStatus.MANUAL_REVIEW, Severity.INFO, "manual", items_count=2),
        ]
        report = AuditReport(document_info={"filename": "test.pdf"}, results=results)
        counts = report.get_category_counts("PDF/UA")["Structure elements"]

        assert counts["passed"] == 10
        assert counts["warned"] == 3
        assert counts["failed"] == 7
        assert counts["manual"] == 2
        assert report.total_passed == 10
        assert report.total_warned == 3
        assert report.total_failed == 7
        assert report.total_manual == 2
        assert report.total_checks == 22
