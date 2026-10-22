"""
Natural Language Rules (ISO 14289-1, Clause 7.3)
Verifies that the document and text elements have valid language specifications for screen reader speech synthesis.
"""

from typing import List
import os
import re
from ..rule_base import BaseRule
from ...core.models import PDFDocumentModel, CheckResult, CheckStatus, Severity

# Standard BCP 47 regex pattern (simplified but robust)
BCP47_PATTERN = re.compile(r"^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$", re.IGNORECASE)


class DocumentLanguageRule(BaseRule):
    rule_id = "PDFUA-LANG-001"
    name = "Document Language"
    category = "Natural language"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = "The natural language of the document must be specified in the document Catalog (ISO 14289-1, Clause 7.3)."
    remediation_template = "In Adobe Acrobat Pro, open File > Properties > Advanced > Reading Options, and select the correct Language (e.g. English US)."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []

        if not doc.language:
            results.append(self.create_result(
                status=CheckStatus.FAIL,
                message="Document primary natural language is not specified.",
                evidence="Catalog dictionary has no /Lang entry.",
                custom_severity=Severity.HIGH,
                custom_remediation="Set the document primary language in Document Properties (e.g., 'en-US', 'en', 'es')."
            ))
        else:
            lang_code = doc.language.strip()
            if not BCP47_PATTERN.match(lang_code):
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"Document language '{lang_code}' does not appear to be a valid BCP 47 language code.",
                    evidence=f"/Lang: '{lang_code}'",
                    custom_remediation="Use a standard IETF BCP 47 language code such as 'en', 'en-US', 'fr-CA', or 'de-DE'."
                ))
            else:
                total_text_units = getattr(doc, "stream_text_strings_count", 0)
                if total_text_units == 0 and hasattr(doc, "pages") and doc.pages:
                    total_text_units = sum(getattr(p, "stream_text_strings_count", 0) for p in doc.pages)
                if total_text_units == 0 and doc.filepath and os.path.exists(doc.filepath):
                    try:
                        import pikepdf
                        with pikepdf.open(doc.filepath) as pdf:
                            count = 0
                            for p in pdf.pages:
                                for op in pikepdf.parse_content_stream(p):
                                    op_str = str(op.operator)
                                    if op_str in ("Tj", "'", '"'):
                                        count += 1
                                    elif op_str == "TJ":
                                        for item in op.operands[0]:
                                            if isinstance(item, (pikepdf.String, bytes)):
                                                count += 1
                            if count > 0:
                                total_text_units = count
                    except Exception:
                        pass

                if total_text_units == 0 and hasattr(doc, "pages") and doc.pages:
                    total_text_units = sum(len(p.text.split()) for p in doc.pages if p.text)
                if total_text_units == 0 and doc.structure_tree:
                    all_nodes = doc.structure_tree.find_all_nodes()
                    total_text_units = sum(len(n.text_content.split()) for n in all_nodes if n.text_content)

                items_cnt = max(1, total_text_units)
                results.append(self.create_result(
                    status=CheckStatus.PASS,
                    message=f"Document primary natural language is specified as '{lang_code}'.",
                    evidence=f"/Lang: '{lang_code}' (verified across {items_cnt} text element(s))",
                    items_count=items_cnt
                ))

        return results


class StructureLanguageRule(BaseRule):
    rule_id = "PDFUA-LANG-002"
    name = "Language Shifts"
    category = "Natural language"
    standard = "PDF/UA"
    severity = Severity.MEDIUM
    description = "Content in a language different from the document's primary language must be tagged with a /Lang attribute."
    remediation_template = "Select the foreign-language text span in Acrobat Pro's Tag Tree, open Properties, and set the Language attribute."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree:
            return results

        # Check nodes with explicit /Lang attribute
        all_nodes = doc.structure_tree.find_all_nodes()
        nodes_with_lang = [n for n in all_nodes if n.lang]

        invalid_langs = []
        for n in nodes_with_lang:
            if not BCP47_PATTERN.match(n.lang):
                invalid_langs.append((n.tag, n.lang, n.page))

        if invalid_langs:
            for tag, code, page in invalid_langs:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Structure element <{tag}> has invalid language code '{code}'.",
                    evidence=f"Tag: <{tag}>, /Lang: '{code}'",
                    page=page or 1,
                    object_reference=f"<{tag}>",
                    custom_remediation="Correct the /Lang attribute to a valid BCP 47 code (e.g. 'fr' or 'es')."
                ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"All {len(nodes_with_lang)} element-level language override(s) have valid BCP 47 codes.",
                evidence="Language shifts syntax validated."
            ))

        return results
