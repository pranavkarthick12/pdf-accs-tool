"""
Audit Runner
Coordinates execution of all registered rules (PDF/UA, WCAG, Quality, AI) against a PDFDocumentModel
and aggregates findings into an AuditReport.
"""

from typing import List, Callable, Optional
import datetime
import logging
from .rule_base import BaseRule
from .pdf_ua import PDF_UA_RULES
from .wcag import WCAG_RULES
from .quality import QUALITY_RULES
from .ai_heuristics import AI_RULES
from ..core.models import PDFDocumentModel, AuditReport, CheckResult, CheckStatus, Severity

logger = logging.getLogger(__name__)


class AuditRunner:
    """Executes all accessibility validation rules against a parsed document."""

    def __init__(self, custom_rules: Optional[List[BaseRule]] = None):
        if custom_rules is not None:
            self.rules = custom_rules
        else:
            self.rules: List[BaseRule] = (
                list(PDF_UA_RULES) +
                list(WCAG_RULES) +
                list(QUALITY_RULES) +
                list(AI_RULES)
            )

    def run(
        self,
        doc: PDFDocumentModel,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> AuditReport:
        """Executes all rules and returns a consolidated AuditReport."""
        results: List[CheckResult] = []
        total_rules = len(self.rules)

        try:
            for idx, rule in enumerate(self.rules, start=1):
                if progress_callback:
                    progress_callback(idx, total_rules, f"Checking {rule.name}...")

                try:
                    rule_results = rule.evaluate(doc)
                    results.extend(rule_results)
                except Exception as e:
                    logger.exception(f"Error running rule {rule.rule_id} ({rule.name}): {e}")
                    results.append(CheckResult(
                        check_id=rule.rule_id,
                        name=rule.name,
                        category=rule.category,
                        standard=rule.standard,
                        status=CheckStatus.ERROR,
                        severity=Severity.HIGH,
                        message=f"Checker error during evaluation: {str(e)}",
                        description=rule.description,
                        evidence=f"Internal rule exception: {type(e).__name__}: {str(e)}",
                        remediation=rule.remediation_template,
                        confidence=0.5
                    ))
        finally:
            if hasattr(doc, "close_fitz_doc"):
                doc.close_fitz_doc()


        doc_info = {
            "filename": doc.filename,
            "filepath": doc.filepath,
            "filesize": doc.filesize,
            "page_count": doc.page_count,
            "pdf_version": doc.pdf_version,
            "title": doc.title or "Untitled",
            "author": doc.author or "",
            "language": doc.language or "Not specified",
            "is_tagged": doc.is_tagged,
            "is_encrypted": doc.is_encrypted,
            "display_doc_title": doc.display_doc_title,
            "pdfua_declared": doc.pdfua_identifier_present,
            "tags_count": len([n for n in doc.structure_tree.find_all_nodes() if n.tag != "StructTreeRoot"]) if doc.structure_tree else 0,
            "fonts_count": len(doc.fonts),
            "images_count": len(doc.images),
            "tables_count": len(doc.tables),
            "links_count": len(doc.links),
            "form_fields_count": len(doc.form_fields),
            "bookmarks_count": len(doc.bookmarks),
        }

        return AuditReport(
            document_info=doc_info,
            results=results,
            timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
