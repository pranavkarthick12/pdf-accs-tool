"""
Form Field Accessibility Rules
The "Form fields tooltips names" error check and error reporting have been removed from the tool.
"""

from typing import List
from ..rule_base import BaseRule
from ...core.models import PDFDocumentModel, CheckResult, Severity


class FormFieldAccessibilityRule(BaseRule):
    rule_id = "PDFUA-FORM-001"
    name = "Form Field Tooltips & Names"
    category = "Forms"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = "Form Field Tooltips & Names check (removed from active error reporting)."
    remediation_template = ""

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        """
        The 'Form fields tooltips names' error check and error reporting
        have been completely removed from the tool.
        """
        return []
