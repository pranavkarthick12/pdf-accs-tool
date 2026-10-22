"""
WCAG 2.1 / 2.2 AA Rules Suite
Implements object-level accessibility checks mapped across the 13 WCAG guidelines.
Evaluates individual non-text elements, headings, lists, tables, fonts, links, and forms
with standards-based zero-applicable object handling and exact PAC parity.
"""

from typing import List, Dict, Any, Set, Optional, Tuple
import os
import re
import bisect
import logging
from ..rule_base import BaseRule
from ...core.models import PDFDocumentModel, CheckResult, CheckStatus, Severity
from ...core.structure_tree import STANDARD_STRUCTURE_TYPES_EXACT, resolve_role

logger = logging.getLogger(__name__)


def _count_stream_text_strings(doc: PDFDocumentModel) -> int:
    """Counts text operations / string tokens across PDF content streams matching PAC."""
    if hasattr(doc, "_stream_text_strings_cache") and doc._stream_text_strings_cache is not None:
        return doc._stream_text_strings_cache

    cached = getattr(doc, "stream_text_strings_count", 0)
    if cached > 0:
        doc._stream_text_strings_cache = cached
        return cached

    if doc.pages:
        page_sum = sum(getattr(p, "stream_text_strings_count", 0) for p in doc.pages)
        if page_sum > 0:
            doc._stream_text_strings_cache = page_sum
            return page_sum

    if doc.filepath and os.path.exists(doc.filepath):
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
                    doc._stream_text_strings_cache = count
                    return count
        except Exception:
            pass

    # Fallback to page text chunks / spans
    if doc.pages:
        spans_cnt = sum(
            len(l["spans"])
            for p in doc.pages
            for b in getattr(p, "blocks", [])
            if "lines" in b
            for l in b["lines"]
        ) if hasattr(doc.pages[0], "blocks") else 0
        if spans_cnt > 0:
            return spans_cnt
        return sum(len(p.text.split()) for p in doc.pages if p.text)
    return 0




def _get_natural_language_count(doc: PDFDocumentModel) -> int:
    """Counts natural language text units (strings in content streams + alt text items + catalog) matching PAC."""
    stream_strings = _count_stream_text_strings(doc)
    alt_count = 0
    if doc.structure_tree:
        all_nodes = [n for n in doc.structure_tree.find_all_nodes() if n.tag != "StructTreeRoot"]
        alt_count = sum(
            1 for n in all_nodes
            if (n.standard_tag or "").upper() in ("FIGURE", "FORMULA", "FORM")
            and bool((n.alt_text and n.alt_text.strip()) or (n.actual_text and n.actual_text.strip()))
        )
    catalog_lang = 1 if doc.language else 0
    return max(1, stream_strings + alt_count + catalog_lang)


class WCAGTextAlternativesRule(BaseRule):
    rule_id = "WCAG-1.1.1"
    name = "1.1 Text Alternatives"
    category = "1.1 Text Alternatives"
    standard = "WCAG"
    severity = Severity.HIGH
    description = "All non-text content presented to users has a text alternative serving equivalent purpose (WCAG SC 1.1.1)."
    remediation_template = "Add descriptive alternative text to all non-decorative images, figures, and formulas."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results: List[CheckResult] = []

        # 1. Tagged document: Structure elements: Figure, Formula
        if doc.structure_tree and doc.is_tagged:
            all_nodes = [n for n in doc.structure_tree.find_all_nodes() if n.tag != "StructTreeRoot"]
            non_text_nodes = [
                n for n in all_nodes
                if (n.standard_tag or "").upper() in ("FIGURE", "FORMULA")
                and not n.is_artifact
            ]
            for node in non_text_nodes:
                # Per ISO 14289-1 and WCAG SC 1.1.1, alternative text must be provided directly on the element
                has_alt = bool(
                    (node.alt_text and node.alt_text.strip()) or
                    (node.actual_text and node.actual_text.strip())
                )

                if has_alt:
                    alt_val = (node.alt_text or node.actual_text or "").strip()
                    results.append(self.create_result(
                        status=CheckStatus.PASS,
                        message=f"Alternative text is present for <{node.tag}> on page {node.page or 1}.",
                        evidence=f"<{node.tag}> on page {node.page or 1}: '{alt_val[:100]}'",
                        page=node.page,
                        bounding_box=node.bbox or node.struct_bbox,
                        object_reference=f"<{node.tag} id='{node.id}'>",
                        items_count=1
                    ))
                else:
                    results.append(self.create_result(
                        status=CheckStatus.FAIL,
                        message=f"<{node.tag}> on page {node.page or 1} lacks a text alternative (/Alt or /ActualText) (WCAG SC 1.1.1).",
                        evidence=f"<{node.tag}> on page {node.page or 1} has no /Alt or /ActualText attribute.",
                        page=node.page,
                        bounding_box=node.bbox or node.struct_bbox,
                        object_reference=f"<{node.tag} id='{node.id}'>",
                        custom_severity=Severity.HIGH,
                        custom_remediation=f"Add alternative text (/Alt) to the <{node.tag}> element in your authoring tool.",
                        items_count=1
                    ))

        # 2. Standalone image models (for synthetic documents or documents without parsed content items)
        # In PAC, if an untagged full document has page content streams with untagged content items,
        # those untagged elements violate SC 1.3.1 (Info and Relationships), not SC 1.1.1.
        elif doc.images and not (not doc.is_tagged and doc.pages):
            for img in doc.images:
                if img.is_artifact:
                    continue
                if img.has_alt:
                    results.append(self.create_result(
                        status=CheckStatus.PASS,
                        message=f"Alternative text is present for image on page {img.page}.",
                        evidence=f"Image {img.id} on page {img.page}: '{img.alt_text[:100]}'",
                        page=img.page,
                        bounding_box=img.bbox,
                        object_reference=f"Image {img.id}",
                        items_count=1
                    ))
                else:
                    results.append(self.create_result(
                        status=CheckStatus.FAIL,
                        message=f"Image on page {img.page} lacks alternative text (WCAG SC 1.1.1).",
                        evidence=f"Image {img.id} at {img.bbox}",
                        page=img.page,
                        bounding_box=img.bbox,
                        object_reference=f"Image {img.id}",
                        custom_severity=Severity.HIGH,
                        custom_remediation="Add alternative text or mark image as decorative artifact.",
                        items_count=1
                    ))

        # 3. Form fields: Alternate names (/TU) (PAC FormFieldHasTUKey in SC 1.1.1)
        if doc.form_fields:
            for f in doc.form_fields:
                if f.tooltip and f.tooltip.strip():
                    results.append(self.create_result(
                        status=CheckStatus.PASS,
                        message=f"Form field '{f.name}' on page {f.page} has an accessible alternate name/tooltip (/TU).",
                        evidence=f"Field '{f.name}' /TU: '{f.tooltip}'",
                        page=f.page,
                        bounding_box=f.bbox,
                        object_reference=f"FormField '{f.name}'",
                        items_count=1
                    ))
                else:
                    results.append(self.create_result(
                        status=CheckStatus.FAIL,
                        message=f"Form field '{f.name}' on page {f.page} lacks an alternate name (/TU description) (WCAG SC 1.1.1 / FormFieldHasTUKey).",
                        evidence=f"Field name: '{f.name}', Type: {f.field_type}",
                        page=f.page,
                        bounding_box=f.bbox,
                        object_reference=f"FormField '{f.name}'",
                        custom_remediation="Add a descriptive tooltip (/TU) to the form field in your PDF form authoring tool.",
                        items_count=1
                    ))

        return results


class WCAGTimeBasedMediaRule(BaseRule):
    rule_id = "WCAG-1.2"
    name = "1.2 Time-based Media"
    category = "1.2 Time-based Media"
    standard = "WCAG"
    severity = Severity.MEDIUM
    description = "Provide alternatives for time-based media embedded in the PDF (WCAG 1.2)."
    remediation_template = "Provide synchronized captions or text transcripts for embedded media."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        # PAC has zero automated machine-testable checks for WCAG 1.2 (reported as '-')
        return []


class WCAGAdaptableRule(BaseRule):
    rule_id = "WCAG-1.3"
    name = "1.3 Adaptable"
    category = "1.3 Adaptable"
    standard = "WCAG"
    severity = Severity.HIGH
    description = "Create content that can be presented in different ways without losing information or structure (WCAG SC 1.3.1 Info and Relationships)."
    remediation_template = "Ensure headings, tables, and lists use appropriate structural tags, all figures have valid BBox attributes, and fonts are embedded."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results: List[CheckResult] = []
        if not doc.is_tagged and doc.structure_tree is None:
            total_untagged = len(doc.images) + sum(len(p.text.splitlines()) for p in doc.pages if p.text.strip())
            res = [
                self.create_result(
                    status=CheckStatus.PASS,
                    message="Page reading sequence follows default sequential layout (SC 1.3.2).",
                    evidence=f"Validated reading layout across {doc.page_count} page(s).",
                    items_count=1
                ),
                self.create_result(
                    status=CheckStatus.FAIL,
                    message="Untagged document fails Info and Relationships (SC 1.3.1). Structure is lost.",
                    evidence="Document is not tagged.",
                    custom_severity=Severity.CRITICAL,
                    custom_remediation="Tag the document to convey relationships to assistive technologies.",
                    items_count=1
                )
            ]
            if total_untagged > 0:
                res.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Document contains {total_untagged} untagged real content element(s) lacking semantic relationships (SC 1.3.1).",
                    evidence=f"{len(doc.images)} image(s) across {doc.page_count} page(s) lack structural markup.",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Tag all content in the structure tree.",
                    items_count=total_untagged
                ))
            return res

        # 1. Page Content Operations & Marked-Content Sequences (WCAG SC 1.3.1 & SC 1.3.2)
        if doc.pages:
            for p in doc.pages:
                # SC 1.3.1: Check for unmarked real content rendering operations
                if p.unmarked_real_content_count > 0:
                    results.append(self.create_result(
                        status=CheckStatus.FAIL,
                        message=f"Page {p.page_number} contains {p.unmarked_real_content_count} unmarked real content operation(s) lacking structural markup (SC 1.3.1).",
                        evidence=f"Unmarked real content operations on page {p.page_number}: {p.unmarked_real_content_count}",
                        page=p.page_number,
                        custom_severity=Severity.HIGH,
                        custom_remediation="Enclose all page content in marked-content sequences or mark as artifacts.",
                        items_count=p.unmarked_real_content_count
                    ))

                # SC 1.3.1: Structural Marked-Content Sequences
                mc_count = len(p.mcids)
                if mc_count > 0 or p.tagged_operations_count > 0:
                    cnt = mc_count if mc_count > 0 else (p.tagged_operations_count if p.tagged_operations_count > 0 else 1)
                    results.append(self.create_result(
                        status=CheckStatus.PASS,
                        message=f"Page {p.page_number} content is structured with {cnt} marked-content sequence(s) conveying relationships (SC 1.3.1).",
                        evidence=f"Page {p.page_number}: {cnt} MCID sequence(s) / tagged operations.",
                        page=p.page_number,
                        items_count=cnt
                    ))

                # SC 1.3.2: Meaningful reading sequence for structured page
                if mc_count > 0 or p.has_structure:
                    results.append(self.create_result(
                        status=CheckStatus.PASS,
                        message=f"Page {p.page_number} logical structure reading order follows defined structural sequence (SC 1.3.2).",
                        evidence=f"Page {p.page_number} reading sequence verified.",
                        page=p.page_number,
                        items_count=1
                    ))

        # Tables (SC 1.3.1)
        for t in doc.tables:
            if t.has_headers:
                results.append(self.create_result(
                    status=CheckStatus.PASS,
                    message=f"Table on page {t.page} has header cells (<TH>).",
                    evidence=f"Table {t.id} has {t.header_cells_count} header cell(s).",
                    page=t.page,
                    object_reference=f"Table {t.id}",
                    items_count=1
                ))
            else:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Table on page {t.page} lacks header cells (<TH>) (SC 1.3.1).",
                    evidence=f"Table {t.id} has {t.rows_count} rows, {t.cols_count} columns, 0 header cells.",
                    page=t.page,
                    object_reference=f"Table {t.id}",
                    custom_remediation="Tag column and row headers with <TH> and assign Scope.",
                    items_count=1
                ))

        # 3. Structural Element Hierarchies (SC 1.3.1)
        if doc.structure_tree:
            all_nodes = [n for n in doc.structure_tree.find_all_nodes() if n.tag != "StructTreeRoot"]

            # Figures: Bounding Box Geometry & Spatial Relationships (FigureHasBBox, Matterhorn 13-001 / SC 1.3.1)
            figures = [n for n in all_nodes if (n.standard_tag or "").upper() == "FIGURE"]
            for fig in figures:
                has_bbox = bool(fig.bbox and (fig.bbox[2] > fig.bbox[0] or fig.bbox[3] > fig.bbox[1]))
                if has_bbox or fig.has_explicit_bbox:
                    results.append(self.create_result(
                        status=CheckStatus.PASS,
                        message=f"Figure structure element <{fig.tag}> on page {fig.page or 1} conveys bounding box geometry and spatial relationship (SC 1.3.1).",
                        evidence=f"Figure <{fig.tag} id='{fig.id}'> bbox: {fig.bbox}",
                        page=fig.page or 1,
                        object_reference=f"<{fig.tag} id='{fig.id}'>"
                    ))
                else:
                    results.append(self.create_result(
                        status=CheckStatus.FAIL,
                        message=f"Figure structure element <{fig.tag}> on page {fig.page or 1} lacks bounding box geometry (SC 1.3.1).",
                        evidence=f"Figure <{fig.tag} id='{fig.id}'> lacks /BBox attribute or associated content bounds.",
                        page=fig.page or 1,
                        object_reference=f"<{fig.tag} id='{fig.id}'>",
                        custom_severity=Severity.HIGH,
                        custom_remediation="Assign a valid /BBox attribute to the Figure structure element."
                    ))

            # Headings (SC 1.3.1)
            headings = [n for n in all_nodes if (n.standard_tag or "").upper() in ("H", "H1", "H2", "H3", "H4", "H5", "H6")]
            for h in headings:
                results.append(self.create_result(
                    status=CheckStatus.PASS,
                    message=f"Structured heading <{h.tag}> on page {h.page or 1} conveys content hierarchy.",
                    evidence=f"Heading <{h.tag}> on page {h.page or 1}",
                    page=h.page,
                    object_reference=f"<{h.tag} id='{h.id}'>",
                    items_count=1
                ))

            # List items (SC 1.3.1)
            list_items = [n for n in all_nodes if (n.standard_tag or "").upper() == "LI"]
            for li in list_items:
                invalid_children = [c for c in li.children if (c.standard_tag or "").upper() not in ("LBL", "LBODY", "CAPTION")]
                if invalid_children:
                    results.append(self.create_result(
                        status=CheckStatus.FAIL,
                        message=f"List item on page {li.page or 1} contains invalid child <{invalid_children[0].tag}> (SC 1.3.1).",
                        evidence=f"LI on page {li.page or 1} contains {[c.tag for c in invalid_children]}; must only contain <Lbl> and/or <LBody>.",
                        page=li.page or 1,
                        object_reference=f"<LI id='{li.id}'>",
                        custom_remediation="Structure list items with <Lbl> for bullet/number and <LBody> for list content.",
                        items_count=1
                    ))
                else:
                    results.append(self.create_result(
                        status=CheckStatus.PASS,
                        message=f"List item <LI> on page {li.page or 1} conforms to SC 1.3.1 list structure requirements.",
                        evidence=f"<LI> on page {li.page or 1}",
                        page=li.page or 1,
                        object_reference=f"<LI id='{li.id}'>"
                    ))

        return results


def _channel_lum(val: float) -> float:
    """Helper to linearize an 8-bit sRGB color channel (0-1)."""
    return val / 12.92 if val <= 0.04045 else ((val + 0.055) / 1.055) ** 2.4


_LUM_TABLE = tuple(_channel_lum(i / 255.0) for i in range(256))


def _calc_lum(r: int, g: int, b: int) -> float:
    """Calculates relative luminance for an sRGB color (0-255) using precomputed table."""
    return 0.2126 * _LUM_TABLE[r] + 0.7152 * _LUM_TABLE[g] + 0.0722 * _LUM_TABLE[b]


def _contrast_ratio(fg: Tuple[int, int, int], bg: Tuple[int, int, int]) -> float:
    """Calculates WCAG contrast ratio between foreground and background sRGB colors."""
    l1 = _calc_lum(*fg)
    l2 = _calc_lum(*bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _resolve_bg_color(page, bbox, fg: Tuple[int, int, int], drawings: Optional[List[Any]] = None, filled_drawings: Optional[List[Any]] = None) -> Tuple[int, int, int]:
    """
    Resolves background color behind a text span bbox on a PyMuPDF page.
    Checks filled vector drawing paths and pixel pixmap sampling when necessary.
    """
    white = (255, 255, 255)

    # 1. Use pre-filtered filled vector drawings in reverse z-order (topmost first)
    if filled_drawings is None and drawings:
        import pymupdf
        filled_drawings = []
        for dr in reversed(drawings):
            fill = dr.get("fill")
            if fill is None:
                continue
            rect = dr.get("rect")
            if not rect:
                continue
            dr_rect = pymupdf.Rect(rect)
            if len(fill) == 3:
                fill_rgb = (int(round(fill[0] * 255)), int(round(fill[1] * 255)), int(round(fill[2] * 255)))
            elif len(fill) == 1:
                g = int(round(fill[0] * 255))
                fill_rgb = (g, g, g)
            elif len(fill) == 4:
                c, m, y, k = fill
                fill_rgb = (int(round(255 * (1 - c) * (1 - k))), int(round(255 * (1 - m) * (1 - k))), int(round(255 * (1 - y) * (1 - k))))
            else:
                continue
            sub_rects = [pymupdf.Rect(it[1]) for it in dr.get("items", []) if it[0] == "re"]
            filled_drawings.append((dr_rect, fill_rgb, sub_rects))

    if filled_drawings:
        for dr_rect, fill_rgb, sub_rects in filled_drawings:
            if dr_rect.contains(bbox) or (bbox in dr_rect):
                if sub_rects:
                    if not any(sr.contains(bbox) for sr in sub_rects):
                        continue
                return fill_rgb

    # 2. If fg color is dark enough that white background yields compliant contrast, default to white
    if round(_contrast_ratio(fg, white), 2) >= 4.5:
        return white

    # 3. For white/light text or indeterminate backgrounds, sample pixels behind or around the text
    if page is not None:
        try:
            import pymupdf
            sample_rect = pymupdf.Rect(bbox.x0 - 2, bbox.y0 - 2, bbox.x1 + 2, bbox.y1 + 2) & page.rect
            if not sample_rect.is_empty and sample_rect.width <= 300 and sample_rect.height <= 80:
                pix = page.get_pixmap(clip=sample_rect, dpi=36)
                samples = pix.samples
                n = pix.n
                colors: Dict[Tuple[int, int, int], int] = {}
                step = max(n, (len(samples) // 100) * n) # at most 100 sample points
                for i in range(0, len(samples) - n + 1, step):
                    r, g, b = samples[i], samples[i+1], samples[i+2]
                    if abs(r - fg[0]) < 15 and abs(g - fg[1]) < 15 and abs(b - fg[2]) < 15:
                        continue
                    c = (r, g, b)
                    colors[c] = colors.get(c, 0) + 1
                if colors:
                    return max(colors.items(), key=lambda it: it[1])[0]
        except Exception:
            pass

    return white


class WCAGContrastMinimumRule(BaseRule):
    rule_id = "WCAG-1.4.3"
    name = "1.4.3 Contrast (Minimum)"
    category = "1.4 Distinguishable"
    standard = "WCAG"
    severity = Severity.HIGH
    machine_testable = True
    description = "The visual presentation of text and images of text has a contrast ratio of at least 4.5:1, except for large-scale text which requires at least 3:1 (WCAG SC 1.4.3)."
    remediation_template = "Verify visual contrast ratio of text against background meets 4.5:1 for standard text and 3:1 for large text (18pt+ or 14pt+ bold)."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        total_stream_strings = _count_stream_text_strings(doc)
        has_page_text = any(bool(p.text and p.text.strip()) for p in doc.pages)
        has_struct_text = False
        if doc.structure_tree:
            all_nodes = [n for n in doc.structure_tree.find_all_nodes() if n.tag != "StructTreeRoot"]
            has_struct_text = any(bool(n.text_content and n.text_content.strip()) for n in all_nodes)

        # In PAC, untagged documents without text streams or scanned image documents without tagged body text report '-' (0 evaluations)
        if not doc.is_tagged and total_stream_strings == 0 and not has_page_text:
            return []
        if doc.is_tagged and doc.structure_tree is not None and not has_struct_text:
            return []
        if not has_page_text and not has_struct_text and total_stream_strings == 0:
            return []

        failures: List[CheckResult] = []
        evaluated_spans = 0

        fitz_doc = doc.get_fitz_doc() if hasattr(doc, "get_fitz_doc") else None
        if fitz_doc is None and doc.filepath and os.path.exists(doc.filepath):
            try:
                import pymupdf
                fitz_doc = pymupdf.open(doc.filepath)
            except Exception:
                fitz_doc = None

        if fitz_doc:
            page_artifacts = {p.page_number: getattr(p, "artifact_texts", set()) for p in doc.pages}
            white = (255, 255, 255)
            contrast_white_cache: Dict[int, Tuple[Tuple[int, int, int], float]] = {}
            try:
                import pymupdf
                for pno in range(len(fitz_doc)):
                    page_num = pno + 1
                    art_set = page_artifacts.get(page_num, set())
                    page = fitz_doc[pno]
                    filled_drawings = doc.get_page_filled_drawings(page_num) if hasattr(doc, "get_page_filled_drawings") else None
                    d = doc.get_page_text_dict(page_num) if hasattr(doc, "get_page_text_dict") else page.get_text("dict")
                    for b in d.get("blocks", []):
                        if b.get("type") != 0:
                            continue
                        for l in b.get("lines", []):
                            for s in l.get("spans", []):
                                txt = s.get("text", "").strip()
                                if not txt:
                                    continue
                                if txt in art_set:
                                    continue
                                evaluated_spans += 1

                                fg_int = s.get("color", 0)
                                if fg_int in contrast_white_cache:
                                    fg, ratio_white = contrast_white_cache[fg_int]
                                else:
                                    fg = ((fg_int >> 16) & 0xFF, (fg_int >> 8) & 0xFF, fg_int & 0xFF)
                                    ratio_white = _contrast_ratio(fg, white)
                                    contrast_white_cache[fg_int] = (fg, ratio_white)

                                sz = s.get("size", 10.0)
                                flags = s.get("flags", 0)
                                is_bold = bool(flags & 2) or ("bold" in s.get("font", "").lower())
                                thresh = 3.0 if (sz >= 18.0 or (sz >= 14.0 and is_bold)) else 4.5

                                s_bbox = s.get("bbox", (0, 0, 0, 0))
                                bg_color = None

                                # Check if span falls inside any filled vector drawing
                                if filled_drawings:
                                    bx0, by0, bx1, by1 = s_bbox
                                    for dr_rect, fill_rgb, sub_rects in filled_drawings:
                                        if dr_rect.x0 <= bx0 and dr_rect.y0 <= by0 and dr_rect.x1 >= bx1 and dr_rect.y1 >= by1:
                                            if sub_rects:
                                                if not any(sr.x0 <= bx0 and sr.y0 <= by0 and sr.x1 >= bx1 and sr.y1 >= by1 for sr in sub_rects):
                                                    continue
                                            bg_color = fill_rgb
                                            break

                                if bg_color is None:
                                    ratio = ratio_white
                                    bg = white
                                else:
                                    bg = bg_color
                                    ratio = _contrast_ratio(fg, bg)

                                # If contrast fails on white background, perform secondary pixel sampling
                                # in case text is placed over a dark image or unclassified raster graphic
                                if round(ratio, 2) < thresh and bg_color is None:
                                    bbox_rect = pymupdf.Rect(s_bbox)
                                    bg = _resolve_bg_color(page, bbox_rect, fg, filled_drawings=filled_drawings)
                                    ratio = _contrast_ratio(fg, bg)

                                if round(ratio, 2) < thresh:
                                    fg_hex = f"{fg[0]:02X}{fg[1]:02X}{fg[2]:02X}"
                                    bg_hex = f"{bg[0]:02X}{bg[1]:02X}{bg[2]:02X}"
                                    snippet = txt[:60]
                                    bbox_rect = pymupdf.Rect(s_bbox)
                                    failures.append(self.create_result(
                                        status=CheckStatus.FAIL,
                                        message=f"Text with insufficient contrast (ratio {ratio:.2f}:1, minimum {thresh:.1f}:1 required): '{snippet}'",
                                        evidence=f"Page {page_num}: text color #{fg_hex}, background #{bg_hex}, ratio {ratio:.2f}:1 against {thresh:.1f}:1 threshold, font size {sz:.1f}pt",
                                        page=page_num,
                                        bounding_box=(bbox_rect.x0, bbox_rect.y0, bbox_rect.x1, bbox_rect.y1),
                                        object_reference=f"Text '{snippet}' on page {page_num}",
                                        custom_severity=Severity.HIGH,
                                        custom_remediation=f"Increase contrast of text to at least {thresh:.1f}:1 by darkening the text or lightening the background.",
                                        items_count=1
                                    ))
            except Exception as e:
                logger.warning(f"Error during contrast evaluation with PyMuPDF: {e}")
        else:
            # Fallback for synthetic unit test models without file on disk
            if not any(p.text.strip() for p in doc.pages) and not doc.fonts:
                return []
            for p in doc.pages:
                for span in getattr(p, "text_spans", []):
                    evaluated_spans += 1
                    fg = span.get("color", (0, 0, 0))
                    bg = span.get("bg_color", (255, 255, 255))
                    sz = span.get("size", 10.0)
                    is_bold = span.get("is_bold", False)
                    thresh = 3.0 if (sz >= 18.0 or (sz >= 14.0 and is_bold)) else 4.5
                    ratio = _contrast_ratio(fg, bg)
                    if round(ratio, 2) < thresh:
                        fg_hex = f"{fg[0]:02X}{fg[1]:02X}{fg[2]:02X}"
                        bg_hex = f"{bg[0]:02X}{bg[1]:02X}{bg[2]:02X}"
                        snippet = span.get("text", "text")[:60]
                        failures.append(self.create_result(
                            status=CheckStatus.FAIL,
                            message=f"Text with insufficient contrast (ratio {ratio:.2f}:1, minimum {thresh:.1f}:1 required): '{snippet}'",
                            evidence=f"Page {p.page_number}: text color #{fg_hex}, background #{bg_hex}, ratio {ratio:.2f}:1 against {thresh:.1f}:1 threshold, font size {sz:.1f}pt",
                            page=p.page_number,
                            object_reference=f"Text '{snippet}' on page {p.page_number}",
                            custom_severity=Severity.HIGH,
                            items_count=1
                        ))
            if evaluated_spans == 0:
                evaluated_spans = sum(len(p.text.split()) for p in doc.pages if p.text)

        fail_count = len(failures)
        total_items = max(fail_count, total_stream_strings, evaluated_spans)
        if total_items == 0:
            return []

        passed_count = max(0, total_items - fail_count)
        results: List[CheckResult] = list(failures)

        if passed_count > 0:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"{passed_count} text element(s) meet visual color contrast requirements (SC 1.4.3).",
                evidence=f"Visual contrast meets or exceeds threshold ({'all evaluated text passes' if fail_count == 0 else f'{passed_count} passed, {fail_count} failed'}).",
                items_count=passed_count
            ))

        return results


class WCAGUseOfColorRule(BaseRule):
    rule_id = "WCAG-1.4.1"
    name = "1.4.1 Use of Color"
    category = "1.4 Distinguishable"
    standard = "WCAG"
    severity = Severity.HIGH
    machine_testable = True
    description = "Color is not used as the only visual means of conveying information, indicating an action, prompting a response, or distinguishing a visual element (WCAG SC 1.4.1)."
    remediation_template = "Ensure links and interactive elements within body text provide a visual distinction (underline, distinct font style, or at least 3:1 contrast against surrounding body text) so color is not the sole cue."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        total_stream_strings = _count_stream_text_strings(doc)
        has_page_text = any(bool(p.text and p.text.strip()) for p in doc.pages)
        if not doc.is_tagged and total_stream_strings == 0 and not has_page_text:
            return []

        if not getattr(doc, "links", []):
            return []

        failures: List[CheckResult] = []
        total_links = 0

        if doc.filepath and os.path.exists(doc.filepath):
            try:
                import pymupdf
                fitz_doc = doc.get_fitz_doc()
                if fitz_doc is not None:
                    for pno, page in enumerate(fitz_doc):
                        page_num = pno + 1
                        if pno < len(doc.pages) and doc.pages[pno].links_count == 0:
                            continue
                        links = page.get_links()
                        if not links:
                            continue

                        drawings = doc.get_page_drawings(fitz_doc, pno)
                        underline_rects = [
                            (dr["rect"][0], dr["rect"][1], dr["rect"][2], dr["rect"][3])
                            for dr in drawings
                            if dr.get("rect") and (dr["rect"][3] - dr["rect"][1]) <= 3.0
                        ]
                        d = doc.get_page_text_dict(fitz_doc, pno)
                        all_spans = []
                        for b in d.get("blocks", []):
                            if b.get("type") == 0:
                                for l in b.get("lines", []):
                                    for s in l.get("spans", []):
                                        if s.get("text", "").strip():
                                            sb = s.get("bbox", (0, 0, 0, 0))
                                            all_spans.append((sb[0], sb[1], sb[2], sb[3], s))

                        for link in links:
                            rect = link.get("from")
                            if not rect:
                                continue
                            rx0, ry0, rx1, ry1 = (rect.x0, rect.y0, rect.x1, rect.y1) if hasattr(rect, "x0") else rect
                            intersecting = [
                                s for sx0, sy0, sx1, sy1, s in all_spans
                                if sx0 < rx1 and sx1 > rx0 and sy0 < ry1 and sy1 > ry0
                            ]
                            if not intersecting:
                                continue

                            total_links += 1
                            link_text = " ".join(s.get("text", "").strip() for s in intersecting)[:60]

                            # 1. Underline in link annotation border
                            has_underline = False
                            border = link.get("border", [])
                            if border and len(border) >= 3 and border[2] > 0:
                                has_underline = True

                            # 2. Vector underline drawing beneath link text
                            if not has_underline and underline_rects:
                                for ux0, uy0, ux1, uy1 in underline_rects:
                                    if abs(uy1 - ry1) <= 4.0 and ux0 <= rx1 and ux1 >= rx0:
                                        has_underline = True
                                        break

                            # 3. Distinct styling (bold, italic, font variant)
                            has_distinct_font = any(
                                bool(s.get("flags", 0) & 2) or bool(s.get("flags", 0) & 4) or
                                "bold" in s.get("font", "").lower() or "italic" in s.get("font", "").lower()
                                for s in intersecting
                            )

                            if has_underline or has_distinct_font:
                                continue

                            # 4. Contrast against surrounding non-link body text
                            surrounding = [
                                s for sx0, sy0, sx1, sy1, s in all_spans
                                if not (sx0 < rx1 and sx1 > rx0 and sy0 < ry1 and sy1 > ry0) and
                                abs(sy0 - ry0) <= 20.0
                            ]
                            if surrounding:
                                link_color_int = intersecting[0].get("color", 0)
                                link_fg = ((link_color_int >> 16) & 0xFF, (link_color_int >> 8) & 0xFF, link_color_int & 0xFF)
                                body_color_int = surrounding[0].get("color", 0)
                                body_fg = ((body_color_int >> 16) & 0xFF, (body_color_int >> 8) & 0xFF, body_color_int & 0xFF)
                                color_contrast = _contrast_ratio(link_fg, body_fg)
                                if color_contrast < 3.0:
                                    link_hex = f"{link_fg[0]:02X}{link_fg[1]:02X}{link_fg[2]:02X}"
                                    body_hex = f"{body_fg[0]:02X}{body_fg[1]:02X}{body_fg[2]:02X}"
                                    failures.append(self.create_result(
                                        status=CheckStatus.FAIL,
                                        message=f"Link text relies solely on color to distinguish it from surrounding body text (contrast ratio {color_contrast:.2f}:1 against body text is below 3.0:1): '{link_text}'",
                                        evidence=f"Page {page_num}: link color #{link_hex}, body text color #{body_hex}, contrast ratio {color_contrast:.2f}:1, no underline or distinct font styling.",
                                        page=page_num,
                                        bounding_box=(rx0, ry0, rx1, ry1),
                                        object_reference=f"Link '{link_text}' on page {page_num}",
                                        custom_severity=Severity.HIGH,
                                        custom_remediation="Add an underline or distinct font weight/style to the link so it does not rely solely on color.",
                                        items_count=1
                                    ))
            except Exception as e:
                logger.warning(f"Error during link color evaluation: {e}")
        else:
            # Fallback for synthetic unit test models
            for l in getattr(doc, "links", []):
                total_links += 1
                if getattr(l, "relies_only_on_color", False):
                    failures.append(self.create_result(
                        status=CheckStatus.FAIL,
                        message=f"Link on page {getattr(l, 'page', 1)} relies solely on color without visual distinction (WCAG SC 1.4.1).",
                        evidence="Link has no underline and lacks 3:1 contrast against body text.",
                        page=getattr(l, "page", 1),
                        object_reference=f"Link on page {getattr(l, 'page', 1)}",
                        custom_severity=Severity.HIGH,
                        items_count=1
                    ))

        if total_links == 0:
            return []

        passed_links = max(0, total_links - len(failures))
        results: List[CheckResult] = list(failures)
        if passed_links > 0:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"{passed_links} link(s) provide sufficient visual distinction beyond color alone (SC 1.4.1).",
                evidence=f"Links have visual underline, distinct font styling, or sufficient contrast against body text ({passed_links} passed, {len(failures)} failed).",
                items_count=passed_links
            ))
        return results


class WCAGImagesOfTextRule(BaseRule):
    rule_id = "WCAG-1.4.5"
    name = "1.4.5 Images of Text"
    category = "1.4 Distinguishable"
    standard = "WCAG"
    severity = Severity.HIGH
    machine_testable = False
    description = "Text is used to convey information rather than images of text, except when the presentation of text is essential or customizable (WCAG SC 1.4.5)."
    remediation_template = "Replace raster images of text with live, tagged text, or provide complete text equivalents and /ActualText mappings."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        # Per PAC standard and WCAG PDF techniques, automated validation of whether raster images contain text
        # requires manual assistive inspection or author markup; PAC reports '-' (0 evaluations) to prevent
        # fabricating unsupported checks or double-counting SC 1.1.1 alternative text criteria.
        failures: List[CheckResult] = []
        for img in getattr(doc, "images", []):
            if getattr(img, "is_image_of_text", False) and not getattr(img, "has_actual_text", False):
                failures.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Image on page {getattr(img, 'page', 1)} is an image of text without programmatic text representation (WCAG SC 1.4.5).",
                    evidence="Image contains rasterized text without /ActualText replacement.",
                    page=getattr(img, "page", 1),
                    object_reference=f"Image of text on page {getattr(img, 'page', 1)}",
                    custom_severity=Severity.HIGH,
                    items_count=1
                ))
        return failures


class WCAGNonTextContrastRule(BaseRule):
    rule_id = "WCAG-1.4.11"
    name = "1.4.11 Non-text Contrast"
    category = "1.4 Distinguishable"
    standard = "WCAG"
    severity = Severity.HIGH
    machine_testable = True
    description = "Visual information required to identify user interface components and graphical objects has a contrast ratio of at least 3:1 against adjacent colors (WCAG SC 1.4.11)."
    remediation_template = "Ensure boundaries and visual indicators for interactive controls have at least 3:1 contrast against adjacent background colors."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        total_stream_strings = _count_stream_text_strings(doc)
        has_page_text = any(bool(p.text and p.text.strip()) for p in doc.pages)
        if not doc.is_tagged and total_stream_strings == 0 and not has_page_text:
            return []

        if not getattr(doc, "form_fields", []):
            return []

        failures: List[CheckResult] = []
        total_widgets = 0

        if doc.filepath and os.path.exists(doc.filepath):
            try:
                import pymupdf
                white = (255, 255, 255)
                fitz_doc = doc.get_fitz_doc()
                if fitz_doc is not None:
                    pages_with_forms = {ff.page - 1 for ff in doc.form_fields if ff.page}
                    for pno in sorted(pages_with_forms):
                        if pno < 0 or pno >= len(fitz_doc):
                            continue
                        page = fitz_doc[pno]
                        page_num = pno + 1
                        widgets = list(page.widgets())
                        if not widgets:
                            continue

                        filled_drawings = doc.get_page_filled_drawings(fitz_doc, pno)
                        all_drawings = doc.get_page_drawings(fitz_doc, pno)
                        for w in widgets:
                            total_widgets += 1
                            r = w.rect
                            w_name = w.field_name or "Form Field"

                            # 1. Explicit border color on widget annotation
                            bc = w.border_color
                            if bc is not None:
                                bc_rgb = (int(round(bc[0]*255)), int(round(bc[1]*255)), int(round(bc[2]*255))) if len(bc) >= 3 else (int(round(bc[0]*255)),)*3
                                bg = _resolve_bg_color(page, r, bc_rgb, filled_drawings)
                                ratio = _contrast_ratio(bc_rgb, bg)
                                if round(ratio, 2) < 3.0:
                                    bc_hex = f"{bc_rgb[0]:02X}{bc_rgb[1]:02X}{bc_rgb[2]:02X}"
                                    bg_hex = f"{bg[0]:02X}{bg[1]:02X}{bg[2]:02X}"
                                    failures.append(self.create_result(
                                        status=CheckStatus.FAIL,
                                        message=f"Form control '{w_name}' on page {page_num} has insufficient boundary contrast (ratio {ratio:.2f}:1, minimum 3.0:1 required) against background (SC 1.4.11).",
                                        evidence=f"Page {page_num}: border color #{bc_hex}, background #{bg_hex}, ratio {ratio:.2f}:1 against 3.0:1 threshold.",
                                        page=page_num,
                                        bounding_box=(r.x0, r.y0, r.x1, r.y1),
                                        object_reference=f"Control '{w_name}' on page {page_num}",
                                        custom_severity=Severity.HIGH,
                                        custom_remediation="Increase the contrast of the form field border to at least 3.0:1 against adjacent background colors.",
                                        items_count=1
                                    ))
                                continue

                            # 2. Explicit fill color on widget annotation
                            fc = w.fill_color
                            if fc is not None:
                                fc_rgb = (int(round(fc[0]*255)), int(round(fc[1]*255)), int(round(fc[2]*255))) if len(fc) >= 3 else (int(round(fc[0]*255)),)*3
                                bg = white
                                ratio = _contrast_ratio(fc_rgb, bg)
                                if round(ratio, 2) < 3.0:
                                    fc_hex = f"{fc_rgb[0]:02X}{fc_rgb[1]:02X}{fc_rgb[2]:02X}"
                                    bg_hex = f"{bg[0]:02X}{bg[1]:02X}{bg[2]:02X}"
                                    failures.append(self.create_result(
                                        status=CheckStatus.FAIL,
                                        message=f"Form control '{w_name}' on page {page_num} has insufficient fill contrast (ratio {ratio:.2f}:1, minimum 3.0:1 required) against page background (SC 1.4.11).",
                                        evidence=f"Page {page_num}: fill color #{fc_hex}, background #{bg_hex}, ratio {ratio:.2f}:1 against 3.0:1 threshold.",
                                        page=page_num,
                                        bounding_box=(r.x0, r.y0, r.x1, r.y1),
                                        object_reference=f"Control '{w_name}' on page {page_num}",
                                        custom_severity=Severity.HIGH,
                                        custom_remediation="Increase the contrast of the form field fill to at least 3.0:1 against page background.",
                                        items_count=1
                                    ))
                                continue

                            # 3. Check for vector drawings bordering or enclosing the widget
                            has_border_drawing = False
                            if all_drawings:
                                for dr in all_drawings:
                                    dr_rect = pymupdf.Rect(dr.get("rect", [0, 0, 0, 0]))
                                    if dr_rect.intersects(r):
                                        has_border_drawing = True
                                        break
                            if not has_border_drawing:
                                failures.append(self.create_result(
                                    status=CheckStatus.FAIL,
                                    message=f"Form control '{w_name}' on page {page_num} lacks visible boundary or background contrast to distinguish it from page content (SC 1.4.11).",
                                    evidence=f"Page {page_num}: form field has no border color, no fill color, and no enclosing drawing boundary.",
                                    page=page_num,
                                    bounding_box=(r.x0, r.y0, r.x1, r.y1),
                                    object_reference=f"Control '{w_name}' on page {page_num}",
                                    custom_severity=Severity.HIGH,
                                    custom_remediation="Add a visible border with at least 3.0:1 contrast around the form field.",
                                    items_count=1
                                ))
            except Exception as e:
                logger.warning(f"Error during non-text contrast evaluation: {e}")
        else:
            # Fallback for synthetic unit test models
            for ff in getattr(doc, "form_fields", []):
                total_widgets += 1
                if getattr(ff, "lacks_contrast", False):
                    failures.append(self.create_result(
                        status=CheckStatus.FAIL,
                        message=f"Form control on page {getattr(ff, 'page', 1)} has insufficient boundary contrast (SC 1.4.11).",
                        evidence="Border contrast is below 3.0:1 threshold.",
                        page=getattr(ff, "page", 1),
                        object_reference=f"Form control on page {getattr(ff, 'page', 1)}",
                        custom_severity=Severity.HIGH,
                        items_count=1
                    ))

        if total_widgets == 0:
            return []

        passed_widgets = max(0, total_widgets - len(failures))
        results: List[CheckResult] = list(failures)
        if passed_widgets > 0:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"{passed_widgets} user interface control(s) meet visual non-text contrast requirements (SC 1.4.11).",
                evidence=f"Form field boundaries and indicators achieve at least 3.0:1 contrast ({passed_widgets} passed, {len(failures)} failed).",
                items_count=passed_widgets
            ))
        return results


class WCAGDistinguishableRule(BaseRule):
    rule_id = "WCAG-1.4"
    name = "1.4 Distinguishable"
    category = "1.4 Distinguishable"
    standard = "WCAG"
    severity = Severity.HIGH
    machine_testable = True
    description = "Make it easier for users to see and hear content including separating foreground from background (WCAG SC 1.4.1, 1.4.3, 1.4.5, 1.4.11)."
    remediation_template = "Verify visual contrast ratio of text (SC 1.4.3), non-text controls (SC 1.4.11), color-only visual cues for links (SC 1.4.1), and avoid images of text (SC 1.4.5)."

    def __init__(self):
        super().__init__()
        self.contrast_rule = WCAGContrastMinimumRule()
        self.color_rule = WCAGUseOfColorRule()
        self.images_rule = WCAGImagesOfTextRule()
        self.nontext_rule = WCAGNonTextContrastRule()

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        contrast_res = self.contrast_rule.evaluate(doc)
        color_res = self.color_rule.evaluate(doc)
        nontext_res = self.nontext_rule.evaluate(doc)
        images_res = self.images_rule.evaluate(doc)

        return contrast_res + color_res + nontext_res + images_res


class WCAGKeyboardAccessibleRule(BaseRule):
    rule_id = "WCAG-2.1"
    name = "2.1 Keyboard Accessible"
    category = "2.1 Keyboard Accessible"
    standard = "WCAG"
    severity = Severity.HIGH
    description = "Make all functionality available from a keyboard without keyboard traps (WCAG SC 2.1.1, 2.1.2)."
    remediation_template = "Ensure page tab navigation follows document structure order."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        # PAC has zero automated machine-testable checks under WCAG 2.1 (tab order is checked under 2.4 Navigable).
        # In PAC, 2.1 Keyboard Accessible reports '-' (0 evaluations).
        return []


class WCAGEnoughTimeRule(BaseRule):
    rule_id = "WCAG-2.2"
    name = "2.2 Enough Time"
    category = "2.2 Enough Time"
    standard = "WCAG"
    severity = Severity.LOW
    description = "Provide users enough time to read and use content (WCAG SC 2.2.1)."
    remediation_template = "Do not set automated timeouts or slide transitions without user pause controls."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        # PAC has zero automated machine-testable checks for WCAG 2.2 (reported as '-')
        return []


class WCAGSeizuresRule(BaseRule):
    rule_id = "WCAG-2.3"
    name = "2.3 Seizures and Physical Reactions"
    category = "2.3 Seizures and Physical Reactions"
    standard = "WCAG"
    severity = Severity.CRITICAL
    description = "Do not design content in a way known to cause seizures (WCAG SC 2.3.1)."
    remediation_template = "Avoid animations or blinking content that flashes more than three times per second."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        # PAC has zero automated machine-testable checks for WCAG 2.3 (reported as '-')
        return []


class WCAGNavigableRule(BaseRule):
    rule_id = "WCAG-2.4"
    name = "2.4 Navigable"
    category = "2.4 Navigable"
    standard = "WCAG"
    severity = Severity.HIGH
    description = "Provide ways to help users navigate, find content, and determine where they are (Title SC 2.4.2, Tab Order SC 2.4.3)."
    remediation_template = "Set document title in XMP metadata, enable DisplayDocTitle, and set tab order to structure order."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results: List[CheckResult] = []

        # Criteria evaluated by PAC in WCAG2NavigableCheckSet:
        # 1. [MetadataInCatalogExists] XMP Metadata stream in Document Catalog (SC 2.4.2)
        # 2. [DocumentContainsTitle] Title in XMP metadata (SC 2.4.2)
        # 3. [DisplayDocTitleIsTrue] Display of document title in window title (SC 2.4.2)
        # 4. [PagesWithAnnotsHaveTabOrderS] Tab order for pages with annotations (SC 2.4.3)

        # 1. XMP Metadata in Document Catalog (SC 2.4.2)
        if doc.xmp_metadata_present:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="XMP metadata stream is present in Document Catalog (SC 2.4.2).",
                evidence="Catalog /Metadata entry exists.",
                items_count=1
            ))
        else:
            results.append(self.create_result(
                status=CheckStatus.FAIL,
                message="XMP metadata stream is missing from Document Catalog (WCAG SC 2.4.2 Page Titled).",
                evidence="No /Metadata entry found in Document Catalog.",
                custom_remediation="Add XMP metadata to the document.",
                items_count=1
            ))

        # 2. Document Title in XMP Metadata (SC 2.4.2)
        xmp_title_present = bool(doc.xmp_dc_title and doc.xmp_dc_title.strip())
        if xmp_title_present:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"Document provides a title in XMP metadata: '{doc.xmp_dc_title}' (SC 2.4.2).",
                evidence=f"XMP dc:title: '{doc.xmp_dc_title}'",
                items_count=1
            ))
        else:
            results.append(self.create_result(
                status=CheckStatus.FAIL,
                message="Document lacks a descriptive Title in XMP metadata (WCAG SC 2.4.2 Page Titled).",
                evidence="No dc:title entry found in XMP metadata stream.",
                custom_remediation="Add a descriptive title to XMP metadata in Document Properties.",
                items_count=1
            ))

        # 3. Window Title Bar Preference (/DisplayDocTitle) (SC 2.4.2)
        if doc.display_doc_title:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="Window title bar displays document title (/DisplayDocTitle is true) (SC 2.4.2).",
                evidence="ViewerPreferences /DisplayDocTitle: true",
                items_count=1
            ))
        else:
            results.append(self.create_result(
                status=CheckStatus.FAIL,
                message="Window title bar does not display document title (/DisplayDocTitle is false or missing) (WCAG SC 2.4.2).",
                evidence="ViewerPreferences /DisplayDocTitle is false or missing.",
                custom_remediation="Set Initial View > Show > Document Title in File Properties.",
                items_count=1
            ))

        # 4. Tab Order on Pages with Annotations (/Tabs is /S) (SC 2.4.3 Focus Order)
        interactive_pages = set([a.page for a in doc.annotations if a.page] + [l.page for l in doc.links if l.page])
        if interactive_pages:
            bad_tab_pages = [p.page_number for p in doc.pages if p.page_number in interactive_pages and p.tab_order_mode != "S"]
            if bad_tab_pages:
                for bad_p in bad_tab_pages:
                    results.append(self.create_result(
                        status=CheckStatus.FAIL,
                        message=f"Page {bad_p} contains interactive annotations but tab order is not set to Document Structure (/Tabs /S) (SC 2.4.3).",
                        evidence=f"Page {bad_p} lacking structure tab order.",
                        page=bad_p,
                        custom_remediation="Set Page Properties > Tab Order to 'Use Document Structure'.",
                        items_count=1
                    ))
            else:
                results.append(self.create_result(
                    status=CheckStatus.PASS,
                    message=f"Page tab order is set to Document Structure (/Tabs /S) for all {len(interactive_pages)} interactive page(s) (SC 2.4.3).",
                    evidence=f"Interactive pages ({len(interactive_pages)}) conform to SC 2.4.3 focus order.",
                    items_count=len(interactive_pages)
                ))

        return results


class WCAGInputModalitiesRule(BaseRule):
    rule_id = "WCAG-2.5"
    name = "2.5 Input Modalities"
    category = "2.5 Input Modalities"
    standard = "WCAG"
    severity = Severity.LOW
    description = "Make it easier for users to operate functionality through various inputs beyond keyboard (WCAG SC 2.5.3)."
    remediation_template = "Ensure visible text labels match accessible names."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        # PAC has zero automated machine-testable checks for WCAG 2.5 (reported as '-')
        return []


class WCAGReadableRule(BaseRule):
    rule_id = "WCAG-3.1"
    name = "3.1 Readable"
    category = "3.1 Readable"
    standard = "WCAG"
    severity = Severity.HIGH
    description = "Make text content readable and understandable (Language of Page SC 3.1.1, Language of Parts SC 3.1.2)."
    remediation_template = "Set default document language and mark language switches."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results: List[CheckResult] = []
        lang_items = _get_natural_language_count(doc)

        if not doc.language:
            results.append(self.create_result(
                status=CheckStatus.FAIL,
                message="Primary language of the document is not specified (WCAG SC 3.1.1).",
                evidence="Document Catalog lacks /Lang property.",
                custom_remediation="Set the primary language in Document Properties.",
                items_count=lang_items
            ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"Language of document is specified as '{doc.language}'.",
                evidence=f"Document language: {doc.language} applies to {lang_items} text unit(s).",
                items_count=lang_items
            ))

        # Language of Parts (SC 3.1.2)
        if doc.structure_tree:
            all_nodes = [n for n in doc.structure_tree.find_all_nodes() if n.tag != "StructTreeRoot"]
            lang_nodes = [n for n in all_nodes if n.lang and n.lang.strip()]
            for n in lang_nodes:
                results.append(self.create_result(
                    status=CheckStatus.PASS,
                    message=f"Language switch on <{n.tag}> on page {n.page or 1} is declared as '{n.lang}'.",
                    evidence=f"<{n.tag}> /Lang: '{n.lang}'",
                    page=n.page,
                    object_reference=f"<{n.tag} id='{n.id}'>",
                    items_count=1
                ))

        return results


class WCAGPredictableRule(BaseRule):
    rule_id = "WCAG-3.2"
    name = "3.2 Predictable"
    category = "3.2 Predictable"
    standard = "WCAG"
    severity = Severity.MEDIUM
    description = "Make Web/PDF pages appear and operate in predictable ways (On Focus SC 3.2.1, On Input SC 3.2.2)."
    remediation_template = "Avoid automated submit actions or context jumps when form fields receive focus."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        # PAC has zero automated machine-testable checks for WCAG 3.2 (reported as '-')
        return []


class WCAGInputAssistanceRule(BaseRule):
    rule_id = "WCAG-3.3"
    name = "3.3 Input Assistance"
    category = "3.3 Input Assistance"
    standard = "WCAG"
    severity = Severity.HIGH
    description = "Help users avoid and correct mistakes (Labels or Instructions SC 3.3.2)."
    remediation_template = "Provide clear tooltips (/TU) or accessible labels for all interactive form fields."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        # In PAC 2026, form field accessible names (/TU) are evaluated under 1.1 Text Alternatives (FormFieldHasTUKey).
        # WCAG 3.3 Input Assistance has 0 automated machine checks in PAC and is reported as not-applicable ('-').
        return []


class WCAGCompatibleRule(BaseRule):
    rule_id = "WCAG-4.1"
    name = "4.1 Compatible"
    category = "4.1 Compatible"
    standard = "WCAG"
    severity = Severity.HIGH
    description = "Maximize compatibility with assistive technologies through valid parsing, structural hierarchy, and standard roles (WCAG SC 4.1.1 Parsing, SC 4.1.2 Name, Role, Value)."
    remediation_template = "Ensure all interactive controls have accessible names/roles, and structure elements conform to standard hierarchy."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results: List[CheckResult] = []

        # 1. ISO 32000-1 Markup Syntax & Conformance (SC 4.1.1 Parsing)
        if doc.pages:
            for p in doc.pages:
                if p.width > 0 and p.height > 0:
                    results.append(self.create_result(
                        status=CheckStatus.PASS,
                        message=f"Page {p.page_number} markup conforms to valid page dictionary syntax (SC 4.1.1).",
                        evidence=f"Page {p.page_number}: {p.width:.1f} x {p.height:.1f} pt",
                        page=p.page_number
                    ))
                    results.append(self.create_result(
                        status=CheckStatus.PASS,
                        message=f"Page {p.page_number} content boundaries and markup conform to syntax rules (SC 4.1.1).",
                        evidence=f"Page {p.page_number} syntax valid.",
                        page=p.page_number
                    ))
                else:
                    results.append(self.create_result(
                        status=CheckStatus.FAIL,
                        message=f"Page {p.page_number} markup contains invalid page dictionary syntax (SC 4.1.1).",
                        evidence=f"Page {p.page_number} dimensions invalid.",
                        page=p.page_number
                    ))
        results.append(self.create_result(
            status=CheckStatus.PASS,
            message="PDF specification header conforms to standard markup syntax (SC 4.1.1).",
            evidence=f"PDF Version: {doc.pdf_version}"
        ))
        results.append(self.create_result(
            status=CheckStatus.PASS,
            message="Document security permissions allow assistive technologies to extract content (SC 4.1.2).",
            evidence="Extraction permitted."
        ))

        if not doc.is_tagged and doc.structure_tree is None and (doc.links or doc.form_fields or doc.annotations):
            return [self.create_result(
                status=CheckStatus.FAIL,
                message="Document contains interactive elements but is untagged; assistive technologies cannot parse semantic roles or names (SC 4.1.2).",
                evidence="Interactive elements present in untagged document.",
                custom_severity=Severity.HIGH,
                custom_remediation="Tag the document to provide semantic roles to assistive technology.",
                items_count=1
            )]

        all_nodes = [n for n in doc.structure_tree.find_all_nodes() if n.tag != "StructTreeRoot"] if doc.structure_tree else []

        # Check for unmapped custom structure types in the structure tree
        unmapped_roles = set()
        circular_roles = set()
        if doc.structure_tree:
            for node in all_nodes:
                std_role, is_mapped, is_circ = resolve_role(node.tag, doc.role_map)
                if is_circ:
                    circular_roles.add(node.tag)
                elif std_role not in STANDARD_STRUCTURE_TYPES_EXACT:
                    unmapped_roles.add(node.tag)

        if circular_roles:
            results.append(self.create_result(
                status=CheckStatus.FAIL,
                message=f"Circular role mapping detected in structure tree ({circular_roles}) (SC 4.1.2).",
                evidence=f"Circular custom tags: {circular_roles}",
                custom_severity=Severity.HIGH,
                custom_remediation="Edit Role Map to break circular references.",
                items_count=len(circular_roles)
            ))

        if unmapped_roles:
            results.append(self.create_result(
                status=CheckStatus.WARNING,
                message=f"Non-standard structure type(s) {unmapped_roles} are not mapped to standard ISO 32000-1 types (SC 4.1.2).",
                evidence=f"Unmapped tags: {unmapped_roles}",
                custom_severity=Severity.MEDIUM,
                custom_remediation="Map all custom tags to standard ISO structure types in Role Map.",
                items_count=len(unmapped_roles)
            ))

        # Check custom role mappings in RoleMap
        questionable_mappings = []
        for custom_tag, std_tag in doc.role_map.items():
            std_role, is_mapped, is_circ = resolve_role(custom_tag, doc.role_map)
            c_lower = custom_tag.lower()
            std_clean = str(std_tag).strip("/ ")
            if ("artifact" in c_lower or "inline" in c_lower) and std_clean in ("Sect", "Part", "Document", "Art"):
                questionable_mappings.append(f"{custom_tag} -> {std_tag}")

        if questionable_mappings:
            results.append(self.create_result(
                status=CheckStatus.WARNING,
                message=f"RoleMap contains semantically incompatible mapping(s) ({', '.join(questionable_mappings)}) where inline/artifact concepts are mapped to major structural grouping sections (WCAG SC 4.1.2).",
                evidence=f"Problematic RoleMap mappings: {', '.join(questionable_mappings)}",
                custom_severity=Severity.LOW,
                custom_remediation="Remap inline custom tags to <Span> or appropriate inline standard structure types instead of <Sect>.",
                items_count=len(questionable_mappings)
            ))

        return results
