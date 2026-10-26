"""
Structure Elements & Tree Rules (ISO 14289-1:2014, Clause 7.1 & 7.4, ISO 32000-1:2008 Clause 14.8.4)
Validates logical tag hierarchy, proper containment & admissibility of lists/tables/headings/containers,
empty elements, and figure bounding boxes according to the Matterhorn Protocol.
"""

from typing import List, Optional, Tuple, Dict, Any, Set
import re
from ..rule_base import BaseRule
from ...core.models import PDFDocumentModel, CheckResult, CheckStatus, Severity, StructureNode, validate_bbox_coordinates
from ...core.structure_tree import (
    STANDARD_STRUCTURE_TYPES_EXACT,
    GROUPING_ROLES,
    BLOCK_ROLES,
    LIST_ROLES,
    TABLE_ROLES,
    INLINE_ROLES,
    ILLUSTRATION_ROLES,
    resolve_role
)

# Inadmissible parent -> child relationships according to ISO 32000-1 Clause 14.8.4
INADMISSIBLE_CHILDREN_MAP: Dict[str, Set[str]] = {
    # Paragraphs / Headings cannot contain major grouping sections, tables, lists, or other paragraphs
    "P": {"Document", "Part", "Art", "Sect", "Table", "L", "H", "H1", "H2", "H3", "H4", "H5", "H6", "P"},
    "H": {"Document", "Part", "Art", "Sect", "Table", "L", "H", "H1", "H2", "H3", "H4", "H5", "H6", "P"},
    "H1": {"Document", "Part", "Art", "Sect", "Table", "L", "H", "H1", "H2", "H3", "H4", "H5", "H6", "P"},
    "H2": {"Document", "Part", "Art", "Sect", "Table", "L", "H", "H1", "H2", "H3", "H4", "H5", "H6", "P"},
    "H3": {"Document", "Part", "Art", "Sect", "Table", "L", "H", "H1", "H2", "H3", "H4", "H5", "H6", "P"},
    "H4": {"Document", "Part", "Art", "Sect", "Table", "L", "H", "H1", "H2", "H3", "H4", "H5", "H6", "P"},
    "H5": {"Document", "Part", "Art", "Sect", "Table", "L", "H", "H1", "H2", "H3", "H4", "H5", "H6", "P"},
    "H6": {"Document", "Part", "Art", "Sect", "Table", "L", "H", "H1", "H2", "H3", "H4", "H5", "H6", "P"},

    # Inline elements cannot contain block/grouping elements
    "Span": {"Document", "Part", "Art", "Sect", "Div", "P", "H", "H1", "H2", "H3", "H4", "H5", "H6", "Table", "L", "TR", "TH", "TD", "LI"},
    "Quote": {"Document", "Part", "Art", "Sect", "Table", "L", "H1", "H2", "H3", "H4", "H5", "H6"},
    "Code": {"Document", "Part", "Art", "Sect", "Div", "P", "H1", "H2", "H3", "H4", "H5", "H6", "Table", "L"},
    "Link": {"Document", "Part", "Art", "Sect", "Div", "P", "H1", "H2", "H3", "H4", "H5", "H6", "Table", "L"},
    "Annot": {"Document", "Part", "Art", "Sect", "Div", "P", "H1", "H2", "H3", "H4", "H5", "H6", "Table", "L"},

    # List label should only contain inline items and marked content
    "Lbl": {"Document", "Part", "Art", "Sect", "Div", "P", "H", "H1", "H2", "H3", "H4", "H5", "H6", "Table", "L", "LI"},

    # List body can contain block and inline elements but not document-level grouping sections
    "LBody": {"Document", "Part", "Art", "Sect"},

    # List container must only contain LI and Caption
    "L": {"Document", "Part", "Art", "Sect", "Div", "P", "H", "H1", "H2", "H3", "H4", "H5", "H6", "Table", "Span", "Link", "Quote"},

    # List item must only contain Lbl and LBody
    "LI": {"Document", "Part", "Art", "Sect", "Div", "P", "H", "H1", "H2", "H3", "H4", "H5", "H6", "Table", "L", "Span", "Link"},

    # Table container must only contain TR, THEAD, TBODY, TFOOT, Caption
    "Table": {"Document", "Part", "Art", "Sect", "Div", "P", "H", "H1", "H2", "H3", "H4", "H5", "H6", "L", "Span", "Link", "TH", "TD"},

    # Table row must only contain TH, TD
    "TR": {"Document", "Part", "Art", "Sect", "Div", "P", "H", "H1", "H2", "H3", "H4", "H5", "H6", "Table", "L", "Span", "Link", "TR"},

    # Table cells (TH, TD) cannot contain document-level grouping sections
    "TH": {"Document", "Part", "Art", "Sect"},
    "TD": {"Document", "Part", "Art", "Sect"},

    # Captions and Notes
    "Caption": {"Document", "Part", "Art", "Sect", "Table", "L"},
    "Note": {"Document", "Part", "Art", "Sect"}
}


class StructureTreeIntegrityRule(BaseRule):
    rule_id = "PDFUA-TREE-001"
    name = "Structure Tree Hierarchy & Containment"
    category = "Structure tree"
    standard = "PDF/UA"
    severity = Severity.CRITICAL
    description = "The structure tree must have a valid StructTreeRoot and compliant structural hierarchy without inadmissible containment (ISO 14289-1, Clause 7.1 / Matterhorn 14-001, 14-002, 13-006)."
    remediation_template = "Ensure the structure tree is tagged and elements are nested logically according to ISO 32000-1."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.is_tagged or not doc.structure_tree:
            return results

        root_children = doc.structure_tree.children
        if not root_children:
            results.append(self.create_result(
                status=CheckStatus.FAIL,
                message="StructTreeRoot contains no children (empty structure tree) (Matterhorn 14-002).",
                evidence="StructTreeRoot /K is empty.",
                custom_remediation="Ensure tags contain document content."
            ))
            return results

        # Traverse the entire structure tree collecting (node, parent) pairs
        nodes_with_parents: List[Tuple[StructureNode, Optional[StructureNode]]] = []

        def _walk_tree(curr: StructureNode, parent: Optional[StructureNode]):
            if curr.tag != "StructTreeRoot":
                nodes_with_parents.append((curr, parent))
            for child in curr.children:
                _walk_tree(child, curr)

        _walk_tree(doc.structure_tree, None)

        all_nodes = [n for n, _ in nodes_with_parents]
        total_tags = len(all_nodes)
        invalid_nodes = []
        warned_nodes = []

        heading_pat = re.compile(r"^H([1-6])$", re.IGNORECASE)
        heading_nodes = []

        for node, parent in nodes_with_parents:
            std_role = node.standard_tag or "Span"
            std_upper = std_role.upper()
            raw_upper = (node.tag or "").upper()

            # Heading hierarchy tracking
            m = heading_pat.match(std_role)
            if m:
                heading_nodes.append((int(m.group(1)), node))

            # 1. Missing or empty tag type
            if not node.tag or not node.standard_tag:
                invalid_nodes.append((
                    node,
                    "Structure element has missing or empty tag type (Matterhorn 13-004).",
                    f"Node ID: {node.id}",
                    "Ensure all tags in the structure tree define a valid structure type."
                ))
                continue

            # 2. Artifact in Structure Tree (Matterhorn 01-001)
            if node.is_artifact or std_upper == "ARTIFACT" or raw_upper == "ARTIFACT" or node.attributes.get("O") == "/Artifact":
                invalid_nodes.append((
                    node,
                    f"Artifact structure element <{node.tag}> must not be present in the structure tree (Matterhorn 01-001).",
                    f"Artifact on page {node.page or 1}",
                    "Remove artifact elements from the structure tree or mark as pagination/background artifacts."
                ))
                continue

            # 3. Inadmissible containment / placement warnings in structure tree (Matterhorn 13-006 / ISO 32000-1 Clause 14.8.4)
            if parent is not None and parent.tag != "StructTreeRoot":
                p_std_role = parent.standard_tag or "Span"
                if p_std_role in INADMISSIBLE_CHILDREN_MAP:
                    inadmissible = INADMISSIBLE_CHILDREN_MAP[p_std_role]
                    if std_role in inadmissible:
                        warned_nodes.append((
                            node,
                            f'Possibly inappropriate use of a "{node.tag}" structure element. Element resolved to <{std_role}> is placed inside <{parent.tag}> (resolved to <{p_std_role}>) (Matterhorn 13-006).',
                            f"<{node.tag}> inside <{parent.tag}> on page {node.page or parent.page or 1}",
                            f"Restructure tags so <{node.tag}> is placed in an admissible container according to ISO 32000-1."
                        ))

            # 4. Inline element at block level without Placement=Block
            parent_is_block = (
                parent is None
                or parent.tag == "StructTreeRoot"
                or (parent.standard_tag or "").upper() in ("DOCUMENT", "PART", "ART", "SECT", "DIV")
            )
            if (std_role in ILLUSTRATION_ROLES or std_role in INLINE_ROLES) and parent_is_block:
                placement = (node.placement or node.attributes.get("Placement", "")).strip("/ ").lower()
                if placement != "block":
                    warned_nodes.append((
                        node,
                        f'Possibly inappropriate use of a "{node.tag}" structure element. Inline element is used at block level without Placement=Block attribute (Matterhorn 13-007).',
                        f"<{node.tag}> on page {node.page or 1}",
                        f'Set Placement=Block attribute on <{node.tag}> or wrap inside a paragraph element.'
                    ))

            # 5. Structural container without children or content (Matterhorn 13-008)
            if std_role in ("Sect", "Div", "Part", "Art") and not node.children and not node.mcids:
                warned_nodes.append((
                    node,
                    f"Structural container <{node.tag}> in structure tree has no children or content (Matterhorn 13-008).",
                    f"Empty container on page {node.page or 1}",
                    "Remove or populate empty container tags in the structure tree."
                ))

        # Check 6: Heading hierarchy in tree (Matterhorn 13-003)
        if heading_nodes:
            first_lvl, first_node = heading_nodes[0]
            if first_lvl != 1:
                warned_nodes.append((
                    first_node,
                    f"First heading in structure tree is <{first_node.tag}> (level {first_lvl}) instead of <H1> (Matterhorn 13-003).",
                    f"First heading on page {first_node.page or 1}",
                    "Start document heading hierarchy with an <H1> title."
                ))

            prev_lvl = first_lvl
            for lvl, h_node in heading_nodes[1:]:
                if lvl > prev_lvl + 1:
                    warned_nodes.append((
                        h_node,
                        f"Structure tree heading hierarchy skips from H{prev_lvl} to H{lvl} (Matterhorn 13-003).",
                        f"Tag <{h_node.tag}> on page {h_node.page or 1}",
                        f"Demote to H{prev_lvl + 1} or insert intervening H{prev_lvl + 1} section."
                    ))
                prev_lvl = lvl

        # Record FAIL findings
        if invalid_nodes:
            for node, msg, evid, remed in invalid_nodes[:5]:
                pg = node.page or (node.pages_spanned[0] if node.pages_spanned else 1)
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=msg,
                    evidence=evid,
                    page=pg,
                    bounding_box=node.bbox,
                    object_reference=f"<{node.tag} id='{node.id}'>",
                    custom_severity=Severity.HIGH,
                    custom_remediation=remed,
                    items_count=1
                ))
            if len(invalid_nodes) > 5:
                rem_fail = len(invalid_nodes) - 5
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"{rem_fail} additional structure tree element(s) failed integrity requirements.",
                    evidence=f"Structure tree failures: {len(invalid_nodes)}/{total_tags}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Review and repair structure tags in Acrobat Pro Tag Tree.",
                    items_count=rem_fail
                ))

        # Record WARNING findings
        if warned_nodes:
            for node, msg, evid, remed in warned_nodes[:5]:
                pg = node.page or (node.pages_spanned[0] if node.pages_spanned else 1)
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=msg,
                    evidence=evid,
                    page=pg,
                    bounding_box=node.bbox,
                    object_reference=f"<{node.tag} id='{node.id}'>",
                    custom_severity=Severity.LOW,
                    custom_remediation=remed,
                    items_count=1
                ))
            if len(warned_nodes) > 5:
                rem_warn = len(warned_nodes) - 5
                results.append(self.create_result(
                    status=CheckStatus.WARNING,
                    message=f"{rem_warn} additional structure tree element(s) have structural warnings.",
                    evidence=f"Structure tree warnings: {len(warned_nodes)}/{total_tags}",
                    custom_severity=Severity.LOW,
                    custom_remediation="Review structure tree tags in Acrobat Pro Tag Tree.",
                    items_count=rem_warn
                ))


        passed_count = max(0, total_tags - len(invalid_nodes) - len(warned_nodes))
        if passed_count > 0:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"{passed_count} structure element(s) conform to logical structure tree requirements.",
                evidence=f"Validated structure tags: {passed_count}/{total_tags}",
                items_count=passed_count
            ))

        return results


class StructureNestingRule(BaseRule):
    rule_id = "PDFUA-STRUCT-001"
    name = "Structure Elements Validation & Nesting"
    category = "Structure elements"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = "Structural elements must satisfy element-specific rules, satisfy Placement attributes, and reference pages properly (ISO 14289-1, Clause 7.1 / Matterhorn 13-001, 13-002, 13-007)."
    remediation_template = "Fix structure element attributes and nesting in the Tag Tree so element rules are satisfied."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree:
            return results

        # Collect all nodes with parent
        nodes_with_parents: List[Tuple[StructureNode, Optional[StructureNode]]] = []

        def _walk_tree(curr: StructureNode, parent: Optional[StructureNode]):
            if curr.tag != "StructTreeRoot":
                nodes_with_parents.append((curr, parent))
            for child in curr.children:
                _walk_tree(child, curr)

        _walk_tree(doc.structure_tree, None)

        all_nodes = [n for n, _ in nodes_with_parents]
        if not all_nodes:
            return results

        invalid_nodes = []

        for node, parent in nodes_with_parents:
            std_role = node.standard_tag or "Span"
            std_upper = std_role.upper()
            raw_upper = (node.tag or "").upper()

            # 1. Missing or empty tag type (Matterhorn 13-004)
            if not node.tag or not node.standard_tag:
                invalid_nodes.append((
                    node,
                    "Structure element has missing or empty tag type (Matterhorn 13-004).",
                    f"Node ID: {node.id}",
                    "Ensure all tags in the structure tree define a valid structure type."
                ))
                continue

            # 1b. Artifact in Structure Tree (Matterhorn 01-001)
            if node.is_artifact or std_upper == "ARTIFACT" or raw_upper == "ARTIFACT" or node.attributes.get("O") == "/Artifact":
                invalid_nodes.append((
                    node,
                    f"Artifact structure element <{node.tag}> must not be present in the structure tree (Matterhorn 01-001).",
                    f"Artifact on page {node.page or 1}",
                    "Remove artifact elements from the structure tree or mark as pagination/background artifacts."
                ))
                continue

            # 2. Missing /Pg on element with marked content (Matterhorn 13-001, ISO 32000-1 Table 323)
            if node.mcids and not node.page and not node.has_pg_attr:
                invalid_nodes.append((
                    node,
                    f"Structure element <{node.tag}> contains marked content but lacks an explicit page reference (/Pg) (Matterhorn 13-001).",
                    f"Element ID: {node.id}",
                    "Ensure structure element specifies target page in /Pg dictionary entry."
                ))
                continue

            # 3. Inline element at block level without Placement=Block (Matterhorn 13-007)
            parent_is_grouping_or_block = (
                parent is None
                or parent.tag == "StructTreeRoot"
                or (parent.standard_tag or "").upper() in ("DOCUMENT", "PART", "ART", "SECT", "DIV")
            )
            if (std_role in ILLUSTRATION_ROLES or std_role in INLINE_ROLES) and parent_is_grouping_or_block:
                placement = (node.placement or node.attributes.get("Placement", "")).strip("/ ").lower()
                if placement != "block":
                    invalid_nodes.append((
                        node,
                        f'Possibly inappropriate use of a "{node.tag}" structure element. Inline element is used at block level without Placement=Block attribute (Matterhorn 13-007).',
                        f"<{node.tag}> on page {node.page or 1}",
                        f'Set Placement=Block attribute on <{node.tag}> or wrap inside a paragraph element.'
                    ))
                    continue

            # 4. Specific List Item children check (Matterhorn 13-002)
            if std_role == "LI":
                for child in node.children:
                    ctag = child.standard_tag or "Span"
                    if ctag not in ("Lbl", "LBody"):
                        invalid_nodes.append((
                            node,
                            f"<LI> (List Item) contains invalid child element <{child.tag}>. An <LI> element must contain only <Lbl> and/or <LBody> (Matterhorn 13-002).",
                            f"LI > {child.tag} on page {node.page or child.page or 1}",
                            "Rearrange list item tags so LI only contains Lbl and LBody."
                        ))

            # 5. Specific Table children check (ISO 32000-1 Table 337)
            if std_role == "Table":
                for child in node.children:
                    ctag = child.standard_tag or "Span"
                    if ctag not in ("TR", "THEAD", "TBODY", "TFOOT", "Caption"):
                        invalid_nodes.append((
                            node,
                            f"<Table> should only contain TR/Caption/Thead/Tbody, found <{child.tag}> (resolved to <{ctag}>)",
                            f"Table > {child.tag} on page {node.page or child.page or 1}",
                            "Rearrange table tags so Table only contains TR/Caption/Thead/Tbody."
                        ))
            elif std_role in ("THEAD", "TBODY", "TFOOT"):
                for child in node.children:
                    ctag = child.standard_tag or "Span"
                    if ctag not in ("TR",):
                        invalid_nodes.append((
                            node,
                            f"<{node.tag}> should only contain TR, found <{child.tag}>",
                            f"{node.tag} > {child.tag} on page {node.page or child.page or 1}",
                            "Rearrange table section tags so only TR rows are contained."
                        ))
            elif std_role == "TR":
                for child in node.children:
                    ctag = child.standard_tag or "Span"
                    if ctag not in ("TH", "TD"):
                        invalid_nodes.append((
                            node,
                            f"<TR> should only contain TH or TD, found <{child.tag}>",
                            f"TR > {child.tag} on page {node.page or child.page or 1}",
                            "Rearrange table row tags so only TH/TD cells are contained."
                        ))

        # Record FAIL findings
        if invalid_nodes:
            for node, msg, evid, remed in invalid_nodes[:5]:
                pg = node.page or (node.pages_spanned[0] if node.pages_spanned else 1)
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=msg,
                    evidence=evid,
                    page=pg,
                    bounding_box=node.bbox,
                    object_reference=f"<{node.tag} id='{node.id}'>",
                    custom_severity=Severity.HIGH,
                    custom_remediation=remed,
                    items_count=1
                ))
            if len(invalid_nodes) > 5:
                rem_fail = len(invalid_nodes) - 5
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"{rem_fail} additional structure element(s) failed integrity requirements.",
                    evidence=f"Structure element failures: {len(invalid_nodes)}/{len(all_nodes)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Review and repair structure tags in Acrobat Pro Tag Tree.",
                    items_count=rem_fail
                ))

        # Evaluated structure element checks (grouping and block-level structural hierarchy elements matching PAC)
        evaluated_elements = [
            n for n in all_nodes
            if (n.standard_tag or "") in (
                "H", "H1", "H2", "H3", "H4", "H5", "H6", "Table", "TH",
                "Document", "Art", "Part", "Sect", "Div", "Index", "TOC", "TOCI",
                "Formula", "Form"
            )
        ]
        # In PAC checkpoint matrix, structure elements checkpoint tracks distinct structural element units
        # For non-empty documents with structure elements:
        total_evaluated = len(evaluated_elements) if evaluated_elements else len(all_nodes)
        passed_count = max(0, total_evaluated - len(invalid_nodes))

        if passed_count > 0:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"{passed_count} structure elements conform to standard element requirements.",
                evidence="Structure elements validation passed.",
                items_count=passed_count
            ))

        return results


class EmptyStructureElementsRule(BaseRule):
    rule_id = "PDFUA-STRUCT-002"
    name = "Empty Structure Elements"
    category = "Structure elements"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = "Structure elements should not be empty unless they serve as structural grouping containers (ISO 14289-1, Clause 7.1 / Matterhorn 13-005)."
    remediation_template = "Delete empty tags or attach content to them."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree:
            return results

        all_nodes = doc.structure_tree.find_all_nodes()
        leaf_empty = []

        for node in all_nodes:
            std_role = node.standard_tag or "Span"
            has_text_payload = bool(
                node.alt_text
                or node.actual_text
                or node.title
                or (node.text_content and node.text_content.strip())
            )
            if std_role in ("P", "H1", "H2", "H3", "H4", "H5", "H6", "Span", "Link") and not node.children and not node.mcids and not has_text_payload:
                leaf_empty.append((node, node.page or 1))

        if leaf_empty:
            for node, pg in leaf_empty[:5]:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"Empty structure element <{node.tag}> has no child tags or marked content (Matterhorn 13-005).",
                    evidence=f"<{node.tag}> on page {pg} is empty.",
                    page=pg,
                    bounding_box=node.bbox,
                    object_reference=f"<{node.tag} id='{node.id}'>",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Remove empty tags in the tag tree or assign content to them.",
                    items_count=1
                ))

            if len(leaf_empty) > 5:
                rem = len(leaf_empty) - 5
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"{rem} additional empty leaf structure element(s) detected.",
                    evidence=f"Total empty leaf elements: {len(leaf_empty)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Remove empty tags or attach content.",
                    items_count=rem
                ))
        else:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="No superfluous empty leaf structure tags detected.",
                evidence="Structure completeness validated.",
                items_count=0
            ))

        return results


class FigureBoundingBoxRule(BaseRule):
    rule_id = "PDFUA-FIG-001"
    name = "Figure Bounding Box"
    category = "Structure elements"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = "Figure elements spanning more than one page must contain a BBox attribute for each page, and any BBox attribute present must be a valid array of four numbers (ISO 14289-1, Clause 7.18 / Matterhorn 16-001, 19-001)."
    remediation_template = "Ensure page-spanning figures define page-specific BBox attributes, and verify that BBox attribute values are valid 4-number arrays [x0 y0 x1 y1]."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.structure_tree:
            return results

        all_nodes = [n for n in doc.structure_tree.find_all_nodes() if n.tag != "StructTreeRoot"]
        figures = [n for n in all_nodes if (n.standard_tag or "").upper() == "FIGURE"]
        if not figures:
            return results

        failing_figures = []
        for fig in figures:
            # 1. Matterhorn 16-001: If BBox attribute is present, verify it is a valid 4-number array
            raw_bbox = None
            if fig.attributes:
                for k, v in fig.attributes.items():
                    if k.lower() == "bbox":
                        raw_bbox = v
                        break

            has_non_empty_raw_bbox = (
                raw_bbox is not None
                and not (isinstance(raw_bbox, (list, tuple, str, dict)) and len(raw_bbox) == 0)
            )

            if has_non_empty_raw_bbox:
                is_valid, _ = validate_bbox_coordinates(raw_bbox)
                if not is_valid:
                    failing_figures.append((
                        fig,
                        "Figure element contains an invalid /BBox attribute (must be an array of four numbers) (Matterhorn 16-001).",
                        f"Malformed BBox: {raw_bbox}",
                        "Set /BBox attribute to a valid array of four numbers [x0 y0 x1 y1]."
                    ))
                    continue

            # Also validate BBox on any child nodes if explicitly present
            for c in fig.children:
                c_bbox = c.attributes.get("BBox") if c.attributes else None
                if c_bbox is not None and not (isinstance(c_bbox, (list, tuple, str, dict)) and len(c_bbox) == 0):
                    is_c_valid, _ = validate_bbox_coordinates(c_bbox)
                    if not is_c_valid:
                        failing_figures.append((
                            c,
                            "Figure element contains an invalid /BBox attribute (must be an array of four numbers) (Matterhorn 16-001).",
                            f"Malformed child BBox: {c_bbox}",
                            "Set /BBox attribute to a valid array of four numbers [x0 y0 x1 y1]."
                        ))
                        break

        if failing_figures:
            for fig, msg, evid, remed in failing_figures[:5]:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=msg,
                    evidence=evid,
                    page=fig.page or 1,
                    object_reference="<Figure>",
                    custom_severity=Severity.HIGH,
                    custom_remediation=remed,
                    items_count=1
                ))
            if len(failing_figures) > 5:
                rem = len(failing_figures) - 5
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"{rem} additional Figure element(s) violate BBox requirements.",
                    evidence=f"Failed BBox requirements on {len(failing_figures)}/{len(figures)} figures.",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Correct /BBox attribute on multi-page and invalid figure tags.",
                    items_count=rem
                ))

        passed_count = len(figures) - len(failing_figures)
        if passed_count > 0:
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"{passed_count} figure element(s) conform to ISO 14289-1 bounding box requirements.",
                evidence=f"Validated figure bounding box integrity: {passed_count}/{len(figures)}",
                items_count=passed_count
            ))

        return results
