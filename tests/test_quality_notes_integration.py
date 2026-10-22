"""
Integration tests for Quality Note Rules:
- QUAL-NOTE-001 (NoteReferencedQualityRule)
- QUAL-NOTE-002 (NoteContainsLabelQualityRule)
- QUAL-NOTE-003 (ParagraphContainsNoteQualityRule)

Verifies end-to-end execution through the default AuditRunner pipeline,
ensuring findings are generated, evaluated, and aggregated into Quality category results.
"""

import pytest
from src.pdf_inspector.core.models import (
    PDFDocumentModel, PageModel, StructureNode, CheckStatus, Severity
)
from src.pdf_inspector.engine.runner import AuditRunner


def _create_base_doc(filename="test_notes.pdf") -> PDFDocumentModel:
    """Helper to create a standard base tagged PDFDocumentModel."""
    page = PageModel(
        page_number=1,
        width=612.0,
        height=792.0
    )
    return PDFDocumentModel(
        filepath=filename,
        filename=filename,
        filesize=2048,
        pdf_version="1.7",
        page_count=1,
        is_tagged=True,
        title="Notes Integration Test Document",
        display_doc_title=True,
        language="en-US",
        pages=[page]
    )


def test_notes_audit_runner_all_pass():
    """
    Test that fully compliant Note structures pass all three Note rules
    when executed end-to-end through the default AuditRunner.
    
    Structure:
    - StructTreeRoot
      - P (paragraph text)
      - Reference (referencing note1 via Ref attribute)
      - Note (id='note1', sibling to P, containing Lbl and P child)
    """
    doc = _create_base_doc("valid_notes.pdf")

    lbl = StructureNode(
        id="lbl1",
        tag="Lbl",
        standard_tag="Lbl",
        page=1,
        text_content="1"
    )
    note_p = StructureNode(
        id="note_p1",
        tag="P",
        standard_tag="P",
        page=1,
        text_content="Detailed explanatory footnote text."
    )
    note = StructureNode(
        id="note1",
        tag="Note",
        standard_tag="Note",
        page=1,
        children=[lbl, note_p]
    )
    lbl.parent = note
    note_p.parent = note

    ref = StructureNode(
        id="ref1",
        tag="Reference",
        standard_tag="Reference",
        page=1,
        attributes={"Ref": "note1"},
        text_content="1"
    )

    body_p = StructureNode(
        id="p1",
        tag="P",
        standard_tag="P",
        page=1,
        text_content="Primary text referencing footnote."
    )

    root = StructureNode(
        id="root",
        tag="StructTreeRoot",
        standard_tag="StructTreeRoot",
        children=[body_p, ref, note]
    )
    body_p.parent = root
    ref.parent = root
    note.parent = root

    doc.structure_tree = root

    # Execute through the default AuditRunner (all rules enabled)
    runner = AuditRunner()
    report = runner.run(doc)

    # 1. Verify all three check IDs are produced in the audit results
    note_001_res = [r for r in report.results if r.check_id == "QUAL-NOTE-001"]
    note_002_res = [r for r in report.results if r.check_id == "QUAL-NOTE-002"]
    note_003_res = [r for r in report.results if r.check_id == "QUAL-NOTE-003"]

    assert len(note_001_res) == 1, "QUAL-NOTE-001 must produce exactly 1 result"
    assert len(note_002_res) == 1, "QUAL-NOTE-002 must produce exactly 1 result"
    assert len(note_003_res) == 1, "QUAL-NOTE-003 must produce exactly 1 result"

    # 2. Verify all three rules evaluated to PASS
    assert note_001_res[0].status == CheckStatus.PASS
    assert note_001_res[0].items_count == 1
    assert "referenced" in note_001_res[0].message.lower()

    assert note_002_res[0].status == CheckStatus.PASS
    assert note_002_res[0].items_count == 1
    assert "lbl" in note_002_res[0].message.lower()

    assert note_003_res[0].status == CheckStatus.PASS
    assert note_003_res[0].items_count == 1
    assert "outside paragraph" in note_003_res[0].message.lower()

    # 3. Verify aggregation in Quality category counts
    quality_counts = report.get_category_counts("QUALITY")
    assert quality_counts['"Note" elements are referenced'] == {
        "passed": 1, "warned": 0, "failed": 0, "manual": 0
    }
    assert quality_counts['"Note" elements contain "Lbl" elements'] == {
        "passed": 1, "warned": 0, "failed": 0, "manual": 0
    }
    assert quality_counts['"P" elements contain "Note" elements'] == {
        "passed": 1, "warned": 0, "failed": 0, "manual": 0
    }


def test_notes_audit_runner_defects_flagged():
    """
    Test that defective Note structures produce WARNING findings for all three
    Note rules when executed end-to-end through the default AuditRunner.

    Defects introduced:
    - Note without Reference -> QUAL-NOTE-001 WARNING
    - Note without Lbl -> QUAL-NOTE-002 WARNING
    - Note nested inside P -> QUAL-NOTE-003 WARNING
    """
    doc = _create_base_doc("defective_notes.pdf")

    # Defective note: no Lbl, unreferenced, placed inside P
    note_defective = StructureNode(
        id="note_defective",
        tag="Note",
        standard_tag="Note",
        page=1,
        text_content="Defective inline footnote content without label."
    )

    parent_p = StructureNode(
        id="p_parent",
        tag="P",
        standard_tag="P",
        page=1,
        text_content="Paragraph containing an embedded note: ",
        children=[note_defective]
    )
    note_defective.parent = parent_p

    root = StructureNode(
        id="root",
        tag="StructTreeRoot",
        standard_tag="StructTreeRoot",
        children=[parent_p]
    )
    parent_p.parent = root

    doc.structure_tree = root

    # Execute through the default AuditRunner
    runner = AuditRunner()
    report = runner.run(doc)

    # 1. Verify all three check IDs are produced
    note_001_res = [r for r in report.results if r.check_id == "QUAL-NOTE-001"]
    note_002_res = [r for r in report.results if r.check_id == "QUAL-NOTE-002"]
    note_003_res = [r for r in report.results if r.check_id == "QUAL-NOTE-003"]

    assert len(note_001_res) == 1
    assert len(note_002_res) == 1
    assert len(note_003_res) == 1

    # 2. Verify all three rules evaluated to WARNING
    assert note_001_res[0].status == CheckStatus.WARNING
    assert "not referenced" in note_001_res[0].message.lower()

    assert note_002_res[0].status == CheckStatus.WARNING
    assert "does not contain a <lbl>" in note_002_res[0].message.lower()

    assert note_003_res[0].status == CheckStatus.WARNING
    assert "nested inside a <p>" in note_003_res[0].message.lower()

    # 3. Verify Quality category counts reflect the warnings
    quality_counts = report.get_category_counts("QUALITY")
    assert quality_counts['"Note" elements are referenced'] == {
        "passed": 0, "warned": 1, "failed": 0, "manual": 0
    }
    assert quality_counts['"Note" elements contain "Lbl" elements'] == {
        "passed": 0, "warned": 1, "failed": 0, "manual": 0
    }
    assert quality_counts['"P" elements contain "Note" elements'] == {
        "passed": 0, "warned": 1, "failed": 0, "manual": 0
    }


def test_notes_audit_runner_absent_notes():
    """
    Test behavior when no Note structures exist in the document.
    Ensures that QUAL-NOTE-001, QUAL-NOTE-002, and QUAL-NOTE-003 produce no results,
    and that their Quality category counts evaluate to 0 (which renders as '-' in PAC UI).
    """
    doc = _create_base_doc("no_notes.pdf")

    p = StructureNode(
        id="p1",
        tag="P",
        standard_tag="P",
        page=1,
        text_content="Standard document content without any notes or footnotes."
    )
    root = StructureNode(
        id="root",
        tag="StructTreeRoot",
        standard_tag="StructTreeRoot",
        children=[p]
    )
    p.parent = root

    doc.structure_tree = root

    # Execute through the default AuditRunner
    runner = AuditRunner()
    report = runner.run(doc)

    # 1. Verify none of the three check IDs produce results when notes are absent
    note_findings = [
        r for r in report.results
        if r.check_id in ("QUAL-NOTE-001", "QUAL-NOTE-002", "QUAL-NOTE-003")
    ]
    assert len(note_findings) == 0, "No Note findings should be produced when Notes are absent"

    # 2. Verify Quality category counts are all 0 (rendered as '-' in PAC)
    quality_counts = report.get_category_counts("QUALITY")
    assert quality_counts['"Note" elements are referenced'] == {
        "passed": 0, "warned": 0, "failed": 0, "manual": 0
    }
    assert quality_counts['"Note" elements contain "Lbl" elements'] == {
        "passed": 0, "warned": 0, "failed": 0, "manual": 0
    }
    assert quality_counts['"P" elements contain "Note" elements'] == {
        "passed": 0, "warned": 0, "failed": 0, "manual": 0
    }


def test_notes_audit_runner_mixed_notes():
    """
    Test a document with multiple notes containing mixed states:
    - Note 1 (note_valid): referenced by ref1, has Lbl lbl1, sibling outside P -> PASS for all 3
    - Note 2 (note_partial): referenced by ref2, sibling outside P, but lacks Lbl -> PASS 001/003, WARN 002
    """
    doc = _create_base_doc("mixed_notes.pdf")

    # Note 1: valid
    lbl1 = StructureNode(id="lbl1", tag="Lbl", standard_tag="Lbl", page=1, text_content="1")
    note1 = StructureNode(id="note1", tag="Note", standard_tag="Note", page=1, children=[lbl1])
    lbl1.parent = note1
    ref1 = StructureNode(id="ref1", tag="Reference", standard_tag="Reference", page=1, attributes={"Ref": "note1"})

    # Note 2: missing Lbl, but referenced and outside P
    note2 = StructureNode(id="note2", tag="Note", standard_tag="Note", page=1, text_content="Note without label")
    ref2 = StructureNode(id="ref2", tag="Reference", standard_tag="Reference", page=1, attributes={"Ref": "note2"})

    body_p = StructureNode(id="p1", tag="P", standard_tag="P", page=1, text_content="Body with two notes.")

    root = StructureNode(
        id="root",
        tag="StructTreeRoot",
        standard_tag="StructTreeRoot",
        children=[body_p, ref1, note1, ref2, note2]
    )
    body_p.parent = root
    ref1.parent = root
    note1.parent = root
    ref2.parent = root
    note2.parent = root

    doc.structure_tree = root

    # Execute through the default AuditRunner
    runner = AuditRunner()
    report = runner.run(doc)

    quality_counts = report.get_category_counts("QUALITY")

    # QUAL-NOTE-001: both referenced -> passed: 2
    assert quality_counts['"Note" elements are referenced'] == {
        "passed": 2, "warned": 0, "failed": 0, "manual": 0
    }

    # QUAL-NOTE-002: 1 has Lbl, 1 missing -> passed: 1, warned: 1
    assert quality_counts['"Note" elements contain "Lbl" elements'] == {
        "passed": 1, "warned": 1, "failed": 0, "manual": 0
    }

    # QUAL-NOTE-003: both outside P -> passed: 2
    assert quality_counts['"P" elements contain "Note" elements'] == {
        "passed": 2, "warned": 0, "failed": 0, "manual": 0
    }
