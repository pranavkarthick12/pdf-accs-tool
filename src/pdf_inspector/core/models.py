"""
PDF Accessibility Inspector - Core Data Models
Provides immutable and structured definitions for document analysis, structural tags,
check results, and accessibility audit reports.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Tuple, Any
import datetime


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    MANUAL_REVIEW = "MANUAL REVIEW"
    NOT_APPLICABLE = "NOT APPLICABLE"
    ERROR = "ERROR"

    @property
    def is_problem(self) -> bool:
        return self in (CheckStatus.FAIL, CheckStatus.WARNING, CheckStatus.ERROR)


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


def validate_bbox_coordinates(val: Any) -> Tuple[bool, Optional[Tuple[float, float, float, float]]]:
    """
    Validates and converts a bounding box attribute.
    Returns (is_valid, parsed_bbox_tuple).
    - Accepts integers, floats, decimal.Decimal, and pikepdf numeric types.
    - Requires exactly four numeric coordinates.
    - Rejects non-numeric strings/objects, NaN, and positive/negative infinity.
    - Preserves legitimate zero and negative coordinates.
    - Returns (False, None) for malformed, non-4-length, non-numeric, or non-finite coordinates.
    """
    if val is None or isinstance(val, (str, bytes, dict)):
        return False, None
    if not isinstance(val, (list, tuple)) and not hasattr(val, "__iter__"):
        return False, None
    try:
        if len(val) != 4:
            return False, None
        import math
        coords = []
        for x in val:
            if isinstance(x, (bool, bytes, str, dict, list)):
                return False, None
            f_val = float(x)
            if not math.isfinite(f_val):
                return False, None
            coords.append(f_val)
        return True, (coords[0], coords[1], coords[2], coords[3])
    except Exception:
        return False, None



@dataclass
class CheckResult:
    """Standardized finding result for any automated or manual rule."""
    check_id: str
    name: str
    category: str
    standard: str  # "PDF/UA", "WCAG", "Quality", "AI"
    status: CheckStatus
    severity: Severity
    message: str
    description: str = ""
    evidence: str = ""
    page: Optional[int] = None
    bounding_box: Optional[Tuple[float, float, float, float]] = None  # (x0, y0, x1, y1)
    object_reference: str = ""
    remediation: str = ""
    confidence: float = 1.0
    machine_testable: bool = True
    manual_review_required: bool = False
    items_count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "name": self.name,
            "category": self.category,
            "standard": self.standard,
            "status": self.status.value,
            "severity": self.severity.value,
            "message": self.message,
            "description": self.description,
            "evidence": self.evidence,
            "page": self.page,
            "bounding_box": list(self.bounding_box) if self.bounding_box else None,
            "object_reference": self.object_reference,
            "remediation": self.remediation,
            "confidence": self.confidence,
            "machine_testable": self.machine_testable,
            "manual_review_required": self.manual_review_required,
            "items_count": self.items_count,
        }


@dataclass
class StructureNode:
    """Represents a structural element within the PDF Logical Structure Tree."""
    id: str
    tag: str
    standard_tag: str
    title: Optional[str] = None
    alt_text: Optional[str] = None
    actual_text: Optional[str] = None
    lang: Optional[str] = None
    page: Optional[int] = None
    mcids: List[int] = field(default_factory=list)
    mcid_entries: List[Tuple[int, Optional[int]]] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    children: List['StructureNode'] = field(default_factory=list)
    text_content: str = ""
    bbox: Optional[Tuple[float, float, float, float]] = None
    struct_bbox: Optional[Tuple[float, float, float, float]] = None
    has_explicit_bbox: bool = False
    placement: Optional[str] = None
    obj_num: Optional[int] = None
    has_pg_attr: bool = False
    pg_attr_val: Optional[int] = None
    pages_spanned: List[int] = field(default_factory=list)
    is_artifact: bool = False
    extracted_graphic_text: Optional[str] = None
    ai_description: Optional[str] = None
    expanded_text: Optional[str] = None
    has_decoding_error: bool = False
    decoding_error_msg: str = ""
    parent: Optional['StructureNode'] = field(default=None, repr=False)

    def is_in_formula(self) -> bool:
        """Returns True if this node or any ancestor is a Formula or Math element."""
        curr = self
        while curr:
            if (curr.standard_tag or curr.tag or "").upper() in ("FORMULA", "MATH"):
                return True
            curr = curr.parent
        return False

    def has_actual_text_ancestor(self) -> bool:
        """Returns True if this node or any ancestor has non-empty /ActualText or /Alt."""
        curr = self
        while curr:
            if (curr.actual_text and curr.actual_text.strip()) or (curr.alt_text and curr.alt_text.strip()):
                return True
            curr = curr.parent
        return False

    def is_artifact_ancestor(self) -> bool:
        """Returns True if this node or any ancestor is marked decorative/artifact."""
        curr = self
        while curr:
            if curr.is_decorative():
                return True
            curr = curr.parent
        return False

    def get_readable_text(self, recursive: bool = True) -> str:
        """
        Returns human-readable text for this node.
        Prefers author-specified /ActualText, then direct text_content,
        then recursively aggregates text from child elements while preserving
        meaningful Unicode characters.
        """
        if self.actual_text and self.actual_text.strip().replace("\x00", ""):
            return self.actual_text.strip().replace("\x00", "")

        parts: List[str] = []
        if self.text_content and self.text_content.strip().replace("\x00", ""):
            parts.append(self.text_content.strip().replace("\x00", ""))

        if recursive and self.children:
            for child in self.children:
                # Do not aggregate text from independent major structures into a parent block
                if child.standard_tag.upper() not in ("FIGURE", "FORMULA", "TABLE", "NOTE"):
                    c_txt = child.get_readable_text(recursive=True)
                    if c_txt and c_txt not in parts:
                        parts.append(c_txt)

        return " ".join(parts).strip()

    def is_decorative(self) -> bool:
        """Returns True if this node represents a decorative/artifact element."""
        return (
            self.is_artifact
            or self.standard_tag.upper() == "ARTIFACT"
            or self.tag.lower() == "artifact"
            or self.attributes.get("O") == "/Artifact"
            or self.attributes.get("Type") == "/Pagination"
            or self.attributes.get("Placement") == "/Background"
        )

    def find_all_by_standard_tag(self, target_tag: str) -> List['StructureNode']:
        results = []
        if self.standard_tag.upper() == target_tag.upper():
            results.append(self)
        for child in self.children:
            results.extend(child.find_all_by_standard_tag(target_tag))
        return results

    def find_all_nodes(self) -> List['StructureNode']:
        all_nodes = [self]
        for child in self.children:
            all_nodes.extend(child.find_all_nodes())
        return all_nodes


@dataclass
class FontModel:
    """Represents a font dictionary in the PDF document."""
    name: str
    subtype: str
    is_embedded: bool
    is_subset: bool
    has_tounicode: bool
    encoding: str
    pages: List[int] = field(default_factory=list)
    is_used: bool = True
    xref: int = 0
    has_standard_encoding: bool = False


@dataclass
class ImageModel:
    """Represents an image or figure on a specific PDF page."""
    id: str
    page: int
    bbox: Tuple[float, float, float, float]
    width: int
    height: int
    colorspace: str
    has_alt: bool
    alt_text: str = ""
    is_artifact: bool = False
    structure_element_id: Optional[str] = None


@dataclass
class TableModel:
    """Represents a data or layout table extracted from the structure tree."""
    id: str
    page: int
    rows_count: int
    cols_count: int
    has_headers: bool
    header_cells_count: int
    data_cells_count: int
    summary: Optional[str] = None
    is_regular: bool = True
    bbox: Optional[Tuple[float, float, float, float]] = None


@dataclass
class LinkModel:
    """Represents a hyperlink annotation and its structure association."""
    id: str
    page: int
    text: str
    uri: str
    is_internal: bool = False
    destination_page: Optional[int] = None
    alt_text: Optional[str] = None
    has_structure_link: bool = False
    bbox: Optional[Tuple[float, float, float, float]] = None


@dataclass
class FormFieldModel:
    """Represents an interactive AcroForm form field."""
    name: str
    field_type: str
    tooltip: Optional[str] = None
    label: Optional[str] = None
    page: int = 1
    is_required: bool = False
    tab_order: Optional[str] = None
    bbox: Optional[Tuple[float, float, float, float]] = None


@dataclass
class BookmarkModel:
    """Represents a document outline (bookmark) item."""
    title: str
    level: int
    page: int
    children: List['BookmarkModel'] = field(default_factory=list)


@dataclass
class AnnotationModel:
    """Represents a PDF page annotation and its association to the logical structure tree."""
    id: str
    page: int
    subtype: str
    rect: Tuple[float, float, float, float]
    struct_parent: Optional[int] = None
    is_tagged: bool = False
    contents: Optional[str] = None


@dataclass
class ListModel:
    """Represents an ordered or unordered structural list element (<L>)."""
    id: str
    page: int
    items_count: int
    is_valid_structure: bool  # L -> LI -> (Lbl, LBody)
    has_labels: bool
    bbox: Optional[Tuple[float, float, float, float]] = None


@dataclass
class ContentOccurrenceModel:
    """Represents a content or artifact sequence encountered in a page or XObject content stream."""
    page_number: int
    operator_type: str  # "text", "path", "xobject", "marked_content"
    operator_name: str  # "Tj", "TJ", "re", "Do", "BDC", "BMC", etc.
    mcid: Optional[int] = None
    tag: Optional[str] = None
    is_artifact: bool = False
    is_inside_tagged: bool = False
    is_inside_artifact: bool = False
    is_unmarked_real_content: bool = False
    xobject_name: Optional[str] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    snippet: str = ""


@dataclass
class ArtifactOccurrenceModel:
    """Represents a marked-content /Artifact sequence found in page streams or XObjects."""
    page_number: int
    is_inside_tagged: bool
    parent_tag: Optional[str] = None
    parent_mcid: Optional[int] = None
    xobject_name: Optional[str] = None
    xobject_xref: Optional[int] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    text_snippet: str = ""


@dataclass
class FormXObjectModel:
    """Represents a Form XObject (ISO 32000-1 Clause 8.10) stream dictionary."""
    id: str
    obj_num: int
    has_valid_bbox: bool = True
    bbox: Optional[Tuple[float, float, float, float]] = None
    has_matrix: bool = False
    matrix_valid: bool = True
    struct_parents: Optional[int] = None
    is_valid: bool = True
    error_message: str = ""


@dataclass
class PageModel:
    """Represents metadata and geometry for a single PDF page."""
    page_number: int  # 1-indexed
    width: float
    height: float
    rotation: int = 0
    text: str = ""
    images_count: int = 0
    links_count: int = 0
    has_structure: bool = False
    has_tab_order: bool = False
    tab_order_mode: str = "Unspecified"
    struct_parents_id: Optional[int] = None
    mcids: List[int] = field(default_factory=list)
    mcid_bboxes: Dict[int, Tuple[float, float, float, float]] = field(default_factory=dict)
    mcid_texts: Dict[int, str] = field(default_factory=dict)
    artifacts: List[ArtifactOccurrenceModel] = field(default_factory=list)
    content_occurrences: List[ContentOccurrenceModel] = field(default_factory=list)
    unmarked_real_content_count: int = 0
    tagged_operations_count: int = 0
    artifact_operations_count: int = 0
    tagged_in_artifact_count: int = 0
    artifact_in_tagged_count: int = 0
    annotations_count: int = 0
    text_spans: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PDFDocumentModel:
    """Unified in-memory model of the parsed PDF document."""
    filepath: str
    filename: str
    filesize: int
    pdf_version: str
    page_count: int
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    keywords: Optional[str] = None
    creator: Optional[str] = None
    producer: Optional[str] = None
    creation_date: Optional[str] = None
    modification_date: Optional[str] = None
    language: Optional[str] = None
    is_tagged: bool = False
    is_encrypted: bool = False
    allows_extraction: bool = True
    display_doc_title: bool = False
    has_suspects: bool = False
    doc_info_title: Optional[str] = None
    doc_info_author: Optional[str] = None
    doc_info_subject: Optional[str] = None
    doc_info_keywords: Optional[str] = None
    xmp_metadata_present: bool = False
    xmp_dc_title: Optional[str] = None
    xmp_dc_creator: Optional[str] = None
    xmp_dc_description: Optional[str] = None
    pdfua_identifier_present: bool = False
    pdfua_part: Optional[int] = None
    has_parent_tree: bool = False
    parent_tree_valid: bool = False
    parent_tree_entries_count: int = 0
    parent_tree_map: Dict[int, Any] = field(default_factory=dict)
    role_map: Dict[str, str] = field(default_factory=dict)
    pages: List[PageModel] = field(default_factory=list)
    structure_tree: Optional[StructureNode] = None
    fonts: List[FontModel] = field(default_factory=list)
    images: List[ImageModel] = field(default_factory=list)
    tables: List[TableModel] = field(default_factory=list)
    lists: List[ListModel] = field(default_factory=list)
    links: List[LinkModel] = field(default_factory=list)
    form_fields: List[FormFieldModel] = field(default_factory=list)
    annotations: List[AnnotationModel] = field(default_factory=list)
    bookmarks: List[BookmarkModel] = field(default_factory=list)
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
    embedded_files_count: int = 0
    form_xobjects: List[FormXObjectModel] = field(default_factory=list)

    @property
    def all_artifacts(self) -> List[ArtifactOccurrenceModel]:
        """Returns all artifact occurrences across all pages."""
        arts: List[ArtifactOccurrenceModel] = []
        for p in self.pages:
            arts.extend(p.artifacts)
        return arts

    @property
    def all_content_occurrences(self) -> List[ContentOccurrenceModel]:
        """Returns all content occurrences across all pages."""
        occs: List[ContentOccurrenceModel] = []
        for p in self.pages:
            occs.extend(p.content_occurrences)
        return occs


@dataclass
class AuditReport:
    """Complete summary and detailed collection of audit results."""
    document_info: Dict[str, Any]
    results: List[CheckResult]
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def get_results_by_standard(self, standard: str) -> List[CheckResult]:
        return [r for r in self.results if r.standard.upper() == standard.upper()]

    def get_category_counts(self, standard: str) -> Dict[str, Dict[str, int]]:
        """Returns {category_name: {'passed': X, 'warned': Y, 'failed': Z, 'manual': W}}"""
        counts: Dict[str, Dict[str, int]] = {}
        if standard.upper() == "PDF/UA":
            for cat in [
                "PDF Syntax (ISO 32000-1)", "Fonts", "Content", "Embedded Files",
                "Natural language", "Structure elements", "Structure tree",
                "Role mapping", "Alternative Descriptions", "Metadata", "Document settings"
            ]:
                counts[cat] = {"passed": 0, "warned": 0, "failed": 0, "manual": 0}

        for r in self.get_results_by_standard(standard):
            if r.category not in counts:
                counts[r.category] = {"passed": 0, "warned": 0, "failed": 0, "manual": 0}
            cnt = r.items_count if (hasattr(r, "items_count") and r.items_count is not None) else 1
            if r.status == CheckStatus.PASS:
                counts[r.category]["passed"] += cnt
            elif r.status == CheckStatus.WARNING:
                counts[r.category]["warned"] += cnt
            elif r.status in (CheckStatus.FAIL, CheckStatus.ERROR):
                counts[r.category]["failed"] += cnt
            elif r.status == CheckStatus.MANUAL_REVIEW:
                counts[r.category]["manual"] += cnt
        return counts
    PAC_PDFUA_CATEGORIES = [
        "PDF Syntax (ISO 32000-1)",
        "Fonts",
        "Content",
        "Embedded Files",
        "Natural language",
        "Structure elements",
        "Structure tree",
        "Role mapping",
        "Alternative Descriptions",
        "Metadata",
        "Document settings",
    ]

    PAC_WCAG_CATEGORIES = [
        "1.1 Text Alternatives",
        "1.2 Time-based Media",
        "1.3 Adaptable",
        "1.4 Distinguishable",
        "2.1 Keyboard Accessible",
        "2.2 Enough Time",
        "2.3 Seizures and Physical Reactions",
        "2.4 Navigable",
        "2.5 Input Modalities",
        "3.1 Readable",
        "3.2 Predictable",
        "3.3 Input Assistance",
        "4.1 Compatible",
    ]

    PAC_QUALITY_CATEGORIES = [
        "Validity of document title",
        "Artifacted content on page body",
        "Tagged text consists of only whitespace",
        "Tagged content exists outside of the page boundaries",
        "Presence of headings",
        "Presence of bookmarks (document outline) if there are headings",
        '"TOCI" elements contain "Link" elements',
        '"TOCI" elements correctly linked to headings',
        "Alternative text on text elements",
        "Validity of alternate text",
        'Completeness of "Link" elements',
        'Formal correctness of "LI" elements',
        'Completeness of "Table" elements',
        '"Note" elements are referenced',
        '"Note" elements contain "Lbl" elements',
        '"P" elements contain "Note" elements',
    ]

    PAC_AI_CATEGORIES = [
        "Classification of the elements",
        "Unrecognized structural elements",
        "Missing structural elements",
    ]

    AI_RULE_MAPPINGS = {
        "Classification of the elements": ["AI-ALT-001", "QUAL-TEXT-001", "PDFUA-FIGURE-001", "PDFUA-FIGURE-002"],
        "Unrecognized structural elements": ["AI-READ-001", "PDFUA-ROLE-001", "PDFUA-STRUCT-003"],
        "Missing structural elements": ["AI-OUTLINE-001", "PDFUA-CONTENT-002", "QUAL-HEAD-001"],
    }

    QUALITY_RULE_MAPPINGS = {
        "Validity of document title": ["QUAL-TITLE-001"],
        "Artifacted content on page body": ["QUAL-ART-001"],
        "Tagged text consists of only whitespace": ["QUAL-WHITE-001"],
        "Tagged content exists outside of the page boundaries": ["QUAL-BOUND-001"],
        "Presence of headings": ["QUAL-HEAD-001"],
        "Presence of bookmarks (document outline) if there are headings": ["QUAL-BOOKMARK-001"],
        '"TOCI" elements contain "Link" elements': ["QUAL-TOC-001"],
        '"TOCI" elements correctly linked to headings': ["QUAL-TOC-002"],
        "Alternative text on text elements": ["QUAL-TEXT-001"],
        "Validity of alternate text": ["QUAL-ALT-001"],
        'Completeness of "Link" elements': ["QUAL-LINK-002"],
        'Formal correctness of "LI" elements': ["QUAL-LIST-001"],
        'Completeness of "Table" elements': ["QUAL-TABLE-001"],
        '"Note" elements are referenced': ["QUAL-NOTE-001"],
        '"Note" elements contain "Lbl" elements': ["QUAL-NOTE-002"],
        '"P" elements contain "Note" elements': ["QUAL-NOTE-003"],
    }


    def get_category_counts(self, standard: str, pac_mapped: bool = True) -> Dict[str, Dict[str, int]]:
        """Returns {category_name: {'passed': X, 'warned': Y, 'failed': Z, 'manual': W}} mapped to PAC categories."""
        std_up = standard.upper()
        if not pac_mapped:
            counts: Dict[str, Dict[str, int]] = {}
            for r in self.get_results_by_standard(standard):
                if r.category not in counts:
                    counts[r.category] = {"passed": 0, "warned": 0, "failed": 0, "manual": 0}
                cnt = r.items_count if (hasattr(r, "items_count") and r.items_count is not None) else 1
                if r.status == CheckStatus.PASS:
                    counts[r.category]["passed"] += cnt
                elif r.status == CheckStatus.WARNING:
                    counts[r.category]["warned"] += cnt
                elif r.status in (CheckStatus.FAIL, CheckStatus.ERROR):
                    counts[r.category]["failed"] += cnt
                elif r.status == CheckStatus.MANUAL_REVIEW:
                    counts[r.category]["manual"] += cnt
            return counts

        if std_up in ("PDF/UA", "PDFUA"):
            counts = {c: {"passed": 0, "warned": 0, "failed": 0, "manual": 0} for c in self.PAC_PDFUA_CATEGORIES}
            pdfua_map = {
                "Tables": "Structure elements",
                "Forms": "Structure elements",
                "Artifacts": "Content",
                "Syntax": "PDF Syntax (ISO 32000-1)",
                "PDF Syntax": "PDF Syntax (ISO 32000-1)",
            }
            seen_unembedded_fonts = set()
            for r in self.get_results_by_standard("PDF/UA"):
                target = pdfua_map.get(r.category, r.category)
                if r.category == "Annotations":
                    target = "Document settings" if r.check_id == "PDFUA-ANNOT-002" else "Content"
                elif r.check_id.startswith("PDFUA-UNICODE-"):
                    target = "Natural language"
                if target not in counts:
                    target = "Content"

                if target == "Fonts" and r.check_id == "PDFUA-FONT-001" and r.status in (CheckStatus.FAIL, CheckStatus.ERROR):
                    font_key = r.object_reference or r.message
                    if font_key in seen_unembedded_fonts:
                        continue
                    seen_unembedded_fonts.add(font_key)

                cnt = r.items_count if (hasattr(r, "items_count") and r.items_count is not None) else 1
                if r.status == CheckStatus.PASS:
                    counts[target]["passed"] += cnt
                elif r.status == CheckStatus.WARNING:
                    counts[target]["warned"] += cnt
                elif r.status in (CheckStatus.FAIL, CheckStatus.ERROR):
                    counts[target]["failed"] += cnt
                elif r.status == CheckStatus.MANUAL_REVIEW:
                    counts[target]["manual"] += cnt
            return counts

        elif std_up == "QUALITY":
            counts = {c: {"passed": 0, "warned": 0, "failed": 0, "manual": 0} for c in self.PAC_QUALITY_CATEGORIES}
            for cat in self.PAC_QUALITY_CATEGORIES:
                rule_ids = self.QUALITY_RULE_MAPPINGS.get(cat, [])
                cat_results = [r for r in self.results if r.check_id in rule_ids]
                p = sum(r.items_count for r in cat_results if r.status == CheckStatus.PASS)
                w = sum(r.items_count for r in cat_results if r.status == CheckStatus.WARNING)
                f = sum(r.items_count for r in cat_results if r.status in (CheckStatus.FAIL, CheckStatus.ERROR))
                m = sum(r.items_count for r in cat_results if r.status == CheckStatus.MANUAL_REVIEW)
                counts[cat] = {"passed": p, "warned": w, "failed": f, "manual": m}
            return counts

        elif std_up == "WCAG":
            counts = {c: {"passed": 0, "warned": 0, "failed": 0, "manual": 0, "not_applicable": 0} for c in self.PAC_WCAG_CATEGORIES}
            for r in self.get_results_by_standard("WCAG"):
                cat = r.category
                if cat not in counts:
                    matched = False
                    for w_cat in self.PAC_WCAG_CATEGORIES:
                        if cat.startswith(w_cat[:3]) or w_cat.startswith(cat[:3]):
                            cat = w_cat
                            matched = True
                            break
                    if not matched:
                        counts[cat] = {"passed": 0, "warned": 0, "failed": 0, "manual": 0, "not_applicable": 0}
                cnt = r.items_count if (hasattr(r, "items_count") and r.items_count is not None) else 1
                if r.status == CheckStatus.PASS:
                    counts[cat]["passed"] += cnt
                elif r.status == CheckStatus.WARNING:
                    counts[cat]["warned"] += cnt
                elif r.status in (CheckStatus.FAIL, CheckStatus.ERROR):
                    counts[cat]["failed"] += cnt
                elif r.status == CheckStatus.MANUAL_REVIEW:
                    counts[cat]["manual"] += cnt
                elif r.status == CheckStatus.NOT_APPLICABLE:
                    counts[cat]["not_applicable"] += (cnt if cnt > 0 else 1)
            return counts

        elif std_up == "AI":
            counts = {c: {"passed": 0, "warned": 0, "failed": 0, "manual": 0} for c in self.PAC_AI_CATEGORIES}
            ai_results = self.get_results_by_standard("AI")
            cat_ai_map = {
                "AI Alt-Text Evaluation": "Classification of the elements",
                "Cognitive Accessibility": "Unrecognized structural elements",
                "Structural AI": "Missing structural elements",
                "Classification of the elements": "Classification of the elements",
                "Unrecognized structural elements": "Unrecognized structural elements",
                "Missing structural elements": "Missing structural elements",
            }
            if ai_results:
                for r in ai_results:
                    target_cat = cat_ai_map.get(r.category, "Classification of the elements")
                    if target_cat not in counts:
                        target_cat = "Classification of the elements"
                    cnt = r.items_count if (hasattr(r, "items_count") and r.items_count is not None) else 1
                    if r.status == CheckStatus.PASS:
                        counts[target_cat]["passed"] += cnt
                    elif r.status == CheckStatus.WARNING:
                        counts[target_cat]["warned"] += cnt
                    elif r.status in (CheckStatus.FAIL, CheckStatus.ERROR):
                        counts[target_cat]["failed"] += cnt
                    elif r.status == CheckStatus.MANUAL_REVIEW:
                        counts[target_cat]["manual"] += cnt
            else:
                for cat, rule_ids in self.AI_RULE_MAPPINGS.items():
                    cat_results = [r for r in self.results if r.check_id in rule_ids]
                    p = sum(r.items_count for r in cat_results if r.status == CheckStatus.PASS)
                    w = sum(r.items_count for r in cat_results if r.status == CheckStatus.WARNING)
                    f = sum(r.items_count for r in cat_results if r.status in (CheckStatus.FAIL, CheckStatus.ERROR))
                    m = sum(r.items_count for r in cat_results if r.status == CheckStatus.MANUAL_REVIEW)
                    counts[cat] = {"passed": p, "warned": w, "failed": f, "manual": m}
            return counts

        else:
            return self.get_category_counts(standard, pac_mapped=False)

    @property
    def total_passed(self) -> int:
        return sum(r.items_count for r in self.results if r.status == CheckStatus.PASS)

    @property
    def total_warned(self) -> int:
        return sum(r.items_count for r in self.results if r.status == CheckStatus.WARNING)

    @property
    def total_failed(self) -> int:
        return sum(r.items_count for r in self.results if r.status in (CheckStatus.FAIL, CheckStatus.ERROR))

    @property
    def total_manual(self) -> int:
        return sum(r.items_count for r in self.results if r.status == CheckStatus.MANUAL_REVIEW)

    @property
    def total_not_applicable(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.NOT_APPLICABLE)

    @property
    def total_checks(self) -> int:
        """Total number of individual item-level checks evaluated across all rules."""
        return self.total_passed + self.total_warned + self.total_failed + self.total_manual

    @property
    def total_findings_count(self) -> int:
        """Total count of individual CheckResult finding objects."""
        return len(self.results)

    @property
    def compliance_score(self) -> float:
        total = self.total_passed + self.total_warned + self.total_failed
        if total == 0:
            return 100.0
        return round((self.total_passed / total) * 100.0, 1)

    @property
    def summary(self) -> Dict[str, Any]:
        """Consolidated, mathematically consistent summary dictionary."""
        return {
            "total_checks": self.total_checks,
            "passed": self.total_passed,
            "warned": self.total_warned,
            "failed": self.total_failed,
            "manual": self.total_manual,
            "not_applicable": self.total_not_applicable,
            "compliance_score": self.compliance_score,
            "findings_count": self.total_findings_count
        }
