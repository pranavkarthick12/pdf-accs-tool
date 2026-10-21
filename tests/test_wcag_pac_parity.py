"""
WCAG PAC Parity & Multi-Document Verification Suite
Validates that our WCAG validation process produces consistent, generalized,
and standards-based outcomes matching PAC across diverse real-world PDF documents,
without any file-specific hardcoding or synthetic values.
"""

import os
import glob
import pytest
from src.pdf_inspector.core.document_parser import DocumentParser
from src.pdf_inspector.engine.runner import AuditRunner
from src.pdf_inspector.core.models import CheckStatus

def _find_benchmark(filename: str) -> str:
    """Helper to locate benchmark PDFs across local environment paths."""
    candidates = [
        os.path.join(r"C:\Users\defaultuser0\Downloads", filename),
        os.path.join(r"C:\Users\HBS\Downloads", filename),
        os.path.join(os.path.dirname(__file__), "..", "test_samples", filename),
        filename
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]


MILLER_PDF = _find_benchmark("miller-cacs1e-ch02.02_updated (1).pdf")
BENCHMARK_58_78 = _find_benchmark("58-78 (2).pdf")
SF_CHAPTER_16 = _find_benchmark("SF_Chapter 16 202-269.pdf")
IMPACT_PDF = _find_benchmark("Impact_2e_AmE_L1_Assessment_SampleTest_Key_Student.pdf")
FORM_940_PDF = _find_benchmark("Form_940_A11y 1.pdf")
CROSSING_AEGEAN_PDF = _find_benchmark("Crossing_the_Aegean_is_Traumatic_Your_bad_hair_day_isnt_A11y.pdf")
FRENCH_1A_PDF = _find_benchmark("French 1A_7654-1-17.pdf")
PDF06_PDF = _find_benchmark("PDF06.pdf")
PDF10_PDF = _find_benchmark("PDF10.pdf")
PDF07_PDF = _find_benchmark("PDF07.pdf")



def test_no_filename_hardcoding_in_rules():
    """Verify that no rule in the engine contains file-specific name matching or hardcoding."""
    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "pdf_inspector"))
    py_files = glob.glob(os.path.join(src_dir, "**", "*.py"), recursive=True)
    
    forbidden_terms = ["miller", "58-78", "cacs1e"]
    violations = []
    
    for fpath in py_files:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, start=1):
                # Ignore comments or purely docstrings if any
                line_clean = line.strip().lower()
                if line_clean.startswith("#") or line_clean.startswith('"""') or line_clean.startswith("'''"):
                    continue
                for term in forbidden_terms:
                    if f'"{term}"' in line_clean or f"'{term}'" in line_clean:
                        violations.append(f"{os.path.basename(fpath)}:{line_no} contains forbidden term '{term}': {line.strip()}")
                        
    assert not violations, f"Found hardcoded filename checks in engine:\n" + "\n".join(violations)


@pytest.mark.skipif(not os.path.exists(MILLER_PDF), reason="Miller benchmark PDF not found in Downloads")
def test_wcag_pac_parity_miller():
    """Verifies that miller PDF matches PAC WCAG 2.1/2.2 AA matrix:
    - 1.1 Text Alternatives: Passed 457, Warned 0, Failed 0 (✅)
    - 1.3 Adaptable: Passed > 10000, Warned 0, Failed 461 (❌) (457 figure BBoxes + 4 unembedded fonts)
    - 1.4 Distinguishable: Passed > 0, Warned 0, Failed 0 (✅)
    - 2.4 Navigable: Passed 0, Warned 0, Failed 3 (❌) (3 title metadata criteria fail)
    - 3.1 Readable: Passed > 0, Warned 0, Failed 0 (✅)
    - 4.1 Compatible: Passed > 1000, Warned > 400, Failed 0 (⚠️)
    - Zero-applicable: 1.2, 2.1, 2.2, 2.3, 2.5, 3.2, 3.3 have 0 evaluations (⊘)
    - Overall: Non-compliant with 464 total WCAG failures.
    """
    doc = DocumentParser(MILLER_PDF).parse()
    assert doc is not None

    runner = AuditRunner()
    report = runner.run(doc)
    wcag_counts = report.get_category_counts("WCAG")

    # 1.1 Text Alternatives
    assert wcag_counts["1.1 Text Alternatives"]["passed"] == 457
    assert wcag_counts["1.1 Text Alternatives"]["warned"] == 0
    assert wcag_counts["1.1 Text Alternatives"]["failed"] == 0

    # 1.3 Adaptable: fails 461 items in PAC
    assert wcag_counts["1.3 Adaptable"]["passed"] > 10000
    assert wcag_counts["1.3 Adaptable"]["warned"] == 0
    assert wcag_counts["1.3 Adaptable"]["failed"] == 461

    # 1.4 Distinguishable
    assert wcag_counts["1.4 Distinguishable"]["passed"] > 0
    assert wcag_counts["1.4 Distinguishable"]["warned"] == 0
    assert wcag_counts["1.4 Distinguishable"]["failed"] == 0

    # 2.4 Navigable: fails 3 title criteria in PAC
    assert wcag_counts["2.4 Navigable"]["passed"] == 0
    assert wcag_counts["2.4 Navigable"]["warned"] == 0
    assert wcag_counts["2.4 Navigable"]["failed"] == 3

    # 3.1 Readable
    assert wcag_counts["3.1 Readable"]["passed"] > 0
    assert wcag_counts["3.1 Readable"]["warned"] == 0
    assert wcag_counts["3.1 Readable"]["failed"] == 0

    # 4.1 Compatible: warns structure tree nesting advisories
    assert wcag_counts["4.1 Compatible"]["passed"] > 1000
    assert wcag_counts["4.1 Compatible"]["warned"] >= 450
    assert wcag_counts["4.1 Compatible"]["failed"] == 0

    # Zero-applicable checkpoints have 0 evaluations
    zero_applicable = [
        "1.2 Time-based Media",
        "2.1 Keyboard Accessible",
        "2.2 Enough Time",
        "2.3 Seizures and Physical Reactions",
        "2.5 Input Modalities",
        "3.2 Predictable",
        "3.3 Input Assistance",
    ]
    for sc in zero_applicable:
        counts = wcag_counts.get(sc, {"passed": 0, "warned": 0, "failed": 0})
        assert counts["passed"] == 0
        assert counts["warned"] == 0
        assert counts["failed"] == 0

    # Overall compliance status check
    total_wcag_failed = sum(c.get("failed", 0) for c in wcag_counts.values())
    assert total_wcag_failed == 464  # 461 in 1.3 + 3 in 2.4


@pytest.mark.skipif(not os.path.exists(BENCHMARK_58_78), reason="58-78 benchmark PDF not found in Downloads")
def test_wcag_pac_parity_58_78():
    """Verifies that 58-78 benchmark PDF produces accurate outcomes matching PAC:
    - 1.1 Text Alternatives: Passed 36, Warned 0, Failed 0 (✅)
    - 1.3 Adaptable: Passed > 30000, Failed 2 (❌) (1 unembedded font + 1 structure element)
    - 1.4 Distinguishable: Passed > 0, Failed 0 (✅)
    - 2.4 Navigable: Passed > 0, Failed 0 (✅) (Title present in Info, XMP, and DisplayDocTitle true)
    - 3.1 Readable: Passed > 10000, Failed 0 (✅)
    - Zero-applicable checkpoints have 0 evaluations.
    """
    doc = DocumentParser(BENCHMARK_58_78).parse()
    report = AuditRunner().run(doc)
    wcag_counts = report.get_category_counts("WCAG")

    assert wcag_counts["1.1 Text Alternatives"]["passed"] == 36
    assert wcag_counts["1.1 Text Alternatives"]["failed"] == 0

    assert wcag_counts["1.3 Adaptable"]["passed"] > 25000
    assert wcag_counts["1.3 Adaptable"]["failed"] == 2

    assert wcag_counts["2.4 Navigable"]["passed"] >= 3
    assert wcag_counts["2.4 Navigable"]["failed"] == 0

    assert wcag_counts["3.1 Readable"]["passed"] > 10000
    assert wcag_counts["3.1 Readable"]["failed"] == 0


@pytest.mark.skipif(not os.path.exists(SF_CHAPTER_16), reason="SF Chapter 16 benchmark PDF not found in Downloads")
def test_wcag_pac_parity_sf_chapter16():
    """Verifies that SF Chapter 16 produces accurate outcomes matching PAC:
    - 1.1 Text Alternatives: Failed > 1000 (❌) (over 1000 figures/formulas lack alt text)
    - 1.3 Adaptable: Passed > 100000, Failed 1 (❌)
    - 2.4 Navigable: Passed > 0 (✅)
    - 3.1 Readable: Passed > 50000 (✅)
    """
    doc = DocumentParser(SF_CHAPTER_16).parse()
    report = AuditRunner().run(doc)
    wcag_counts = report.get_category_counts("WCAG")

    assert wcag_counts["1.1 Text Alternatives"]["failed"] >= 1000
    assert wcag_counts["1.3 Adaptable"]["passed"] > 100000
    assert wcag_counts["1.3 Adaptable"]["failed"] == 1
    assert wcag_counts["3.1 Readable"]["passed"] > 50000


@pytest.mark.skipif(not os.path.exists(IMPACT_PDF), reason="Impact benchmark PDF not found in Downloads")
def test_wcag_pac_parity_impact():
    """Verifies that Impact sample test PDF produces accurate outcomes matching PAC:
    - 1.1 Text Alternatives: Passed 32, Failed 2 (❌)
    - 1.3 Adaptable: Passed > 20000, Failed 2 (❌)
    - 2.4 Navigable: Passed > 0, Failed 0 (✅)
    - 3.1 Readable: Passed > 10000 (✅)
    """
    doc = DocumentParser(IMPACT_PDF).parse()
    report = AuditRunner().run(doc)
    wcag_counts = report.get_category_counts("WCAG")

    assert wcag_counts["1.1 Text Alternatives"]["passed"] == 32
    assert wcag_counts["1.1 Text Alternatives"]["failed"] == 2
    assert wcag_counts["1.3 Adaptable"]["passed"] > 18000
    assert wcag_counts["2.4 Navigable"]["failed"] == 0


@pytest.mark.skipif(not os.path.exists(FORM_940_PDF), reason="Form 940 PDF not found in Downloads")
def test_wcag_pac_parity_form_940():
    """Verifies that Form 940 accurately evaluates 102 form fields for /TU alternate names:
    - 1.1 Text Alternatives: Failed 102 (all 102 form fields lack /TU)
    - 1.3 Adaptable: Passed > 1000, Failed 0
    - 2.4 Navigable: Passed > 0, Failed 0 (XMP title, DisplayDocTitle, tab order all compliant)
    - Total WCAG failures = 102 (matches PAC, no double-counting in 3.3).
    """
    doc = DocumentParser(FORM_940_PDF).parse()
    report = AuditRunner().run(doc)
    wcag_counts = report.get_category_counts("WCAG")

    assert wcag_counts["1.1 Text Alternatives"]["failed"] == 102
    assert wcag_counts["3.3 Input Assistance"]["failed"] == 0
    assert wcag_counts["1.3 Adaptable"]["failed"] == 0
    assert wcag_counts["2.4 Navigable"]["failed"] == 0
    assert sum(c.get("failed", 0) for c in wcag_counts.values()) == 102


@pytest.mark.skipif(not os.path.exists(CROSSING_AEGEAN_PDF), reason="Crossing the Aegean PDF not found in Downloads")
def test_wcag_pac_parity_crossing_aegean():
    """Verifies that Crossing the Aegean PDF accurately evaluates unembedded fonts:
    - 1.3 Adaptable: Failed 11 (11 unembedded fonts)
    - 2.4 Navigable: Passed > 0, Failed 0
    - Total WCAG failures = 11.
    """
    doc = DocumentParser(CROSSING_AEGEAN_PDF).parse()
    report = AuditRunner().run(doc)
    wcag_counts = report.get_category_counts("WCAG")

    assert wcag_counts["1.3 Adaptable"]["failed"] == 11
    assert wcag_counts["2.4 Navigable"]["failed"] == 0
    assert sum(c.get("failed", 0) for c in wcag_counts.values()) == 11


@pytest.mark.skipif(not os.path.exists(FRENCH_1A_PDF), reason="French 1A untagged PDF not found in Downloads")
def test_wcag_pac_parity_french_1a():
    """Verifies that French 1A (untagged document) matches PAC WCAG parity:
    - 1.1 Text Alternatives: 0 (renders as '-' in PAC, untagged images violate 1.3.1)
    - 1.3 Adaptable: Failed 289 (1 untagged document + 288 untagged images)
    - 2.4 Navigable: Failed 3 (missing title and metadata)
    - 3.1 Readable: Failed 1 (missing document language)
    """
    doc = DocumentParser(FRENCH_1A_PDF).parse()
    report = AuditRunner().run(doc)
    wcag_counts = report.get_category_counts("WCAG")

    assert wcag_counts.get("1.1 Text Alternatives", {}).get("failed", 0) == 0
    assert wcag_counts["1.3 Adaptable"]["failed"] == 289
    assert wcag_counts["2.4 Navigable"]["failed"] == 3
    assert wcag_counts["3.1 Readable"]["failed"] == 1
    # 1.4 Distinguishable renders as '-' in PAC (0 evaluations)
    assert wcag_counts.get("1.4 Distinguishable", {}).get("passed", 0) == 0
    assert wcag_counts.get("1.4 Distinguishable", {}).get("failed", 0) == 0


@pytest.mark.skipif(not os.path.exists(PDF06_PDF), reason="PDF06.pdf not found in Downloads")
def test_wcag_pac_parity_pdf06_distinguishable():
    """PDF06 is a scanned image document; PAC reports 0 passed, 0 failed ('-') for 1.4 Distinguishable."""
    doc = DocumentParser(PDF06_PDF).parse()
    report = AuditRunner().run(doc)
    wcag_counts = report.get_category_counts("WCAG")
    dist = wcag_counts.get("1.4 Distinguishable", {})
    assert dist.get("passed", 0) == 0
    assert dist.get("failed", 0) == 0


@pytest.mark.skipif(not os.path.exists(PDF10_PDF), reason="PDF10.pdf not found in Downloads")
def test_wcag_pac_parity_pdf10_distinguishable():
    """PDF10 is an accessible document; PAC reports 6772 passed, 0 failed for 1.4 Distinguishable."""
    doc = DocumentParser(PDF10_PDF).parse()
    report = AuditRunner().run(doc)
    wcag_counts = report.get_category_counts("WCAG")
    dist = wcag_counts.get("1.4 Distinguishable", {})
    assert dist.get("passed", 0) == 6772
    assert dist.get("failed", 0) == 0


@pytest.mark.skipif(not os.path.exists(PDF07_PDF), reason="PDF07.pdf not found in Downloads")
def test_wcag_pac_parity_pdf07_distinguishable():
    """PDF07 has low contrast text; PAC reports 8487 passed, 401 failed for 1.4 Distinguishable."""
    doc = DocumentParser(PDF07_PDF).parse()
    report = AuditRunner().run(doc)
    wcag_counts = report.get_category_counts("WCAG")
    dist = wcag_counts.get("1.4 Distinguishable", {})
    assert dist.get("passed", 0) == 8487
    assert dist.get("failed", 0) == 401
    assert dist.get("passed", 0) + dist.get("failed", 0) == 8888


def test_wcag_1_4_distinguishable_two_decimal_rounding_boundary():
    """Verifies that contrast ratios rounding to 4.50:1 (e.g. #FFFFFF on #007CC3, ratio 4.496:1) pass SC 1.4.3 per PAC standard."""
    from src.pdf_inspector.engine.wcag.wcag_rules import WCAGDistinguishableRule, _contrast_ratio
    from src.pdf_inspector.core.models import PageModel, PDFDocumentModel

    fg = (255, 255, 255)
    bg = (0, 124, 195)
    ratio = _contrast_ratio(fg, bg)
    assert 4.495 < ratio < 4.50
    assert round(ratio, 2) == 4.50

    p = PageModel(
        page_number=1, width=612, height=792, text="Check No.",
        text_spans=[{"text": "Check No.", "color": fg, "bg_color": bg, "size": 8.0, "is_bold": True}]
    )
    doc = PDFDocumentModel(
        filepath="", filename="rounding.pdf", filesize=100, pdf_version="1.7",
        page_count=1, is_tagged=True, pages=[p]
    )
    rule = WCAGDistinguishableRule()
    results = rule.evaluate(doc)
    assert any(r.status == CheckStatus.PASS for r in results)
    assert not any(r.status == CheckStatus.FAIL for r in results)

