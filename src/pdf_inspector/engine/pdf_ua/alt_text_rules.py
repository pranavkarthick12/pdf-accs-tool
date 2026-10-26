"""
Alternative Descriptions Rules (ISO 14289-1, Clause 7.18)
Verifies that Figures, Formulas, and other graphical elements have meaningful alternative descriptions.
Matches PAC (PDF Accessibility Checker) visual inspection patterns and error messaging.
"""

from typing import List, Tuple, Optional
import re
from ..rule_base import BaseRule
from ...core.models import PDFDocumentModel, CheckResult, CheckStatus, Severity

# Placeholder and filename regexes
FILENAME_PATTERN = re.compile(r"^.*\.(png|jpe?g|gif|bmp|tiff|svg|webp|ico|pdf)$", re.IGNORECASE)
PLACEHOLDER_PATTERN = re.compile(r"^(image|figure|photo|graphic|picture|placeholder|untitled|alt text)$", re.IGNORECASE)


class FigureAlternativeTextRule(BaseRule):
    rule_id = "PDFUA-ALT-001"
    name = "Alternative Descriptions"
    category = "Alternative Descriptions"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = "Every Figure and Formula element must possess an alternative description (/Alt) or /ActualText (ISO 14289-1, Clause 7.18)."
    remediation_template = "In Acrobat Pro, right-click Figure/Formula tag > Properties > Tag tab > Alternative Text, and enter a descriptive alternative."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.is_tagged or not doc.structure_tree:
            return results

        figure_nodes = doc.structure_tree.find_all_by_standard_tag("Figure")
        formula_nodes = doc.structure_tree.find_all_by_standard_tag("Formula")
        all_graphics = figure_nodes + formula_nodes

        if not all_graphics:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="No graphical figures or formulas found in the document.",
                evidence="Graphic elements count: 0"
            ))
            return results

        missing_alt = []
        placeholder_alt = []

        for node in all_graphics:
            if node.is_decorative():
                continue
            alt_candidate = (node.alt_text or "").strip()
            actual_candidate = (node.actual_text or "").strip()
            alt = alt_candidate if alt_candidate else actual_candidate
            page = node.page
            if page is None and node.pages_spanned:
                page = node.pages_spanned[0]
            page = page or 1

            # Bounding box resolution
            bbox = self._resolve_node_bbox(node, doc, page)

            tag_label = "Formula" if node.standard_tag.upper() == "FORMULA" else "Figure"

            if not alt:
                missing_alt.append((tag_label, page, bbox, node.id, node.text_content))
            elif FILENAME_PATTERN.match(alt) or PLACEHOLDER_PATTERN.match(alt) or len(alt) <= 2:
                placeholder_alt.append((tag_label, alt, page, bbox, node.id, node.text_content))

        if missing_alt:
            for tag_label, pg, bbox, nid, txt in missing_alt:
                snip_str = f" Content: \"{txt[:40]}\"" if txt else ""
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f'Alternative text missing for "{tag_label}" structure element',
                    evidence=f'<{tag_label}> on page {pg} lacks alternative text (/Alt).{snip_str}',
                    page=pg,
                    bounding_box=bbox,
                    object_reference=f"<{tag_label} id='{nid}'>",
                    custom_severity=Severity.HIGH,
                    custom_remediation=f"Add an informative alternative description describing the {tag_label.lower()} in the tag properties.",
                    items_count=1
                ))

        if placeholder_alt:
            for tag_label, text, pg, bbox, nid, txt in placeholder_alt:
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f'Alternative text for "{tag_label}" is suspicious or placeholder: \'{text}\'',
                    evidence=f"Alternative text: '{text}' on page {pg}",
                    page=pg,
                    bounding_box=bbox,
                    object_reference=f"<{tag_label} id='{nid}'>",
                    custom_severity=Severity.MEDIUM,
                    custom_remediation="Replace file names or generic placeholders with meaningful descriptive alt text.",
                    items_count=1
                ))

        passed_cnt = max(0, len(all_graphics) - len(missing_alt) - len(placeholder_alt))
        valid_links = len([l for l in doc.links if l.text or l.uri]) if doc.links else 0
        total_passed = passed_cnt + valid_links
        if total_passed > 0:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"{total_passed} element(s) (figures, formulas, links) have valid alternative descriptions.",
                evidence=f"Passed figures/formulas ({passed_cnt}) and links ({valid_links}) with valid alternative text.",
                items_count=total_passed
            ))

        return results

    def _resolve_node_bbox(self, node, doc: PDFDocumentModel, page_num: int) -> Optional[Tuple[float, float, float, float]]:
        """Finds or computes the bounding box for a structure node."""
        if node.bbox and len(node.bbox) == 4 and any(c > 0 for c in node.bbox):
            return node.bbox

        page_height = 792.0
        if doc.pages and len(doc.pages) >= page_num:
            page_height = doc.pages[page_num - 1].height

        if node.struct_bbox and len(node.struct_bbox) == 4:
            sb = node.struct_bbox
            # If in PDF user coordinates (bottom-up):
            if sb[1] < page_height and sb[3] <= page_height:
                return (sb[0], min(page_height - sb[1], page_height - sb[3]), sb[2], max(page_height - sb[1], page_height - sb[3]))
            return sb

        # Recursive check on children
        for child in node.children:
            cb = self._resolve_node_bbox(child, doc, page_num)
            if cb:
                return cb

        # Check for matching image on that page
        for img in doc.images:
            if img.page == page_num and img.bbox:
                return img.bbox

        return None
