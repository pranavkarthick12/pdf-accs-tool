"""
List Structure Rules (ISO 14289-1:2014, Clause 7.4 & Matterhorn Protocol 1.1 Checkpoints 28-001, 28-002)
Validates strict list structure hierarchy: <L> contains <LI> (or <Caption>), which contains at most
one direct <Lbl> and at most one direct <LBody>, with nested lists permitted inside <LBody>.
"""

from typing import List, Optional, Tuple, Dict, Any, Set
from ..rule_base import BaseRule
from ...core.models import (
    PDFDocumentModel, CheckResult, CheckStatus, Severity, StructureNode, ListModel
)


class ListStructureHierarchyRule(BaseRule):
    rule_id = "PDFUA-LIST-001"
    name = "List Structure Hierarchy"
    category = "Structure elements"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = (
        "A list (<L>) must contain only list items (<LI>) or captions (<Caption>), "
        "and each <LI> must contain at most one direct list label (<Lbl>) and at most one "
        "direct list body (<LBody>) element (ISO 14289-1 Clause 7.4 / Matterhorn 28-001, 28-002)."
    )
    remediation_template = (
        "In Acrobat Pro Tags panel, re-nest list elements so that L contains LI, "
        "and each LI contains at most one direct Lbl and at most one direct LBody. "
        "Place any nested lists inside LBody."
    )

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        # 1. Determine whether structure tree contains list structures (<L> or <LI>)
        has_struct_lists = False
        l_nodes: List[StructureNode] = []
        li_nodes: List[StructureNode] = []

        if doc.structure_tree:
            all_nodes = doc.structure_tree.find_all_nodes()
            l_nodes = [
                n for n in all_nodes
                if n is not None and (n.standard_tag or n.tag or "").upper() == "L"
            ]
            li_nodes = [
                n for n in all_nodes
                if n is not None and (n.standard_tag or n.tag or "").upper() == "LI"
            ]
            has_struct_lists = bool(l_nodes or li_nodes)

        # Case A: No lists detected in tree and no lists in doc.lists
        if not has_struct_lists and not doc.lists:
            return [self.create_result(
                status=CheckStatus.PASS,
                message="No lists detected in document (or document contains no list structures).",
                evidence="List count: 0",
                items_count=0
            )]

        # Case B: Structure tree has no list nodes, but doc.lists is populated (e.g. synthetic test fixtures)
        if not has_struct_lists and doc.lists:
            return self._evaluate_from_list_models(doc)

        # Case C: Structure tree contains <L> or <LI> nodes -> Perform deep structure tree validation
        return self._evaluate_from_structure_tree(doc, l_nodes, li_nodes)

    def _evaluate_from_structure_tree(
        self,
        doc: PDFDocumentModel,
        l_nodes: List[StructureNode],
        li_nodes: List[StructureNode]
    ) -> List[CheckResult]:
        results: List[CheckResult] = []
        defects: List[Dict[str, Any]] = []
        valid_li_count = 0
        total_li_count = len(li_nodes)

        # 1. Inspect all List containers (<L>) for Matterhorn 28-001
        for l_node in l_nodes:
            page_val = l_node.page
            if page_val is None and l_node.pages_spanned:
                page_val = l_node.pages_spanned[0]
            if page_val is None:
                page_val = 1

            direct_children = [
                c for c in l_node.children
                if c is not None and isinstance(c, StructureNode)
            ]
            invalid_l_children = [
                c for c in direct_children
                if (c.standard_tag or c.tag or "").upper() not in ("LI", "CAPTION")
            ]

            l_path = l_node.get_structure_path() if hasattr(l_node, "get_structure_path") else f"L id='{l_node.id}'"

            if invalid_l_children:
                invalid_tags = [c.tag or c.standard_tag for c in invalid_l_children]
                defects.append({
                    "message": (
                        f"List container <L> on page {page_val} has an invalid structural hierarchy: "
                        f"contains invalid direct child element(s) {invalid_tags} "
                        f"(direct children of <L> must only be <LI> or <Caption> per ISO 14289-1 Clause 7.4 / Matterhorn 28-001)."
                    ),
                    "evidence": (
                        f"Path: {l_path} | Direct children: {[c.tag or c.standard_tag for c in direct_children]} | Page: {page_val}"
                    ),
                    "page": page_val,
                    "object_reference": f"<L id='{l_node.id}'>",
                    "remediation": "Wrap list content inside <LI> elements directly under <L> (optional <Caption> allowed)."
                })
            elif len(direct_children) == 0 and not l_node.mcids:
                defects.append({
                    "message": (
                        f"List container <L> on page {page_val} has an invalid structural hierarchy: "
                        f"contains no list items (<LI>) or child elements (Matterhorn 28-001)."
                    ),
                    "evidence": f"Path: {l_path} | Direct children count: 0 | Page: {page_val}",
                    "page": page_val,
                    "object_reference": f"<L id='{l_node.id}'>",
                    "remediation": "Populate the <L> list container with <LI> list item elements or remove empty <L> tag."
                })

        # 2. Inspect every List Item (<LI>) for direct child structure & cardinality (Matterhorn 28-002, ISO 32000-1 14.8.4.3.3)
        for li in li_nodes:
            page_val = li.page
            if page_val is None and li.parent:
                page_val = li.parent.page
            if page_val is None and li.pages_spanned:
                page_val = li.pages_spanned[0]
            if page_val is None:
                page_val = 1

            immediate_children = [
                c for c in li.children
                if c is not None and isinstance(c, StructureNode)
            ]
            direct_lbl = [
                c for c in immediate_children
                if (c.standard_tag or c.tag or "").upper() == "LBL"
            ]
            direct_lbody = [
                c for c in immediate_children
                if (c.standard_tag or c.tag or "").upper() == "LBODY"
            ]
            other_direct = [
                c for c in immediate_children
                if (c.standard_tag or c.tag or "").upper() not in ("LBL", "LBODY")
            ]
            has_direct_content = bool(li.mcids)

            li_defects = []
            lbl_count = len(direct_lbl)
            lbody_count = len(direct_lbody)

            # Check cardinality: At most one direct <Lbl>
            if lbl_count > 1:
                li_defects.append(
                    f"contains {lbl_count} direct <Lbl> elements (at most 1 direct <Lbl> allowed by ISO 32000-1 Clause 14.8.4.3.3)"
                )

            # Check cardinality: At most one direct <LBody>
            if lbody_count > 1:
                li_defects.append(
                    f"contains {lbody_count} direct <LBody> elements (at most 1 direct <LBody> allowed by ISO 32000-1 Clause 14.8.4.3.3)"
                )

            # Check direct child types (Matterhorn 28-002)
            if other_direct:
                invalid_tags = [c.tag or c.standard_tag for c in other_direct]
                li_defects.append(
                    f"contains invalid direct child element(s) {invalid_tags} (must contain only <Lbl> and/or <LBody> per Matterhorn 28-002)"
                )

            # Check empty LI element
            if len(immediate_children) == 0 and not has_direct_content:
                li_defects.append("is empty (contains neither <Lbl> nor <LBody>)")
            elif has_direct_content and lbody_count == 0 and lbl_count == 0:
                li_defects.append("contains direct content operations outside of an <LBody> element")

            if li_defects:
                li_path = li.get_structure_path() if hasattr(li, "get_structure_path") else f"LI id='{li.id}'"
                other_info = f", other: {[c.tag or c.standard_tag for c in other_direct]}" if other_direct else ""
                defects.append({
                    "message": (
                        f"List item <LI> on page {page_val} has an invalid structural hierarchy: "
                        f"{'; '.join(li_defects)}."
                    ),
                    "evidence": (
                        f"Path: {li_path} | Direct children: {lbl_count} <Lbl>, {lbody_count} <LBody>{other_info} | Page: {page_val}"
                    ),
                    "page": page_val,
                    "object_reference": f"<LI id='{li.id}'>",
                    "remediation": (
                        "Restructure the list item so each <LI> contains at most one direct <Lbl> and at most "
                        "one direct <LBody>. Enclose list content in <LBody> and place any nested lists inside <LBody>."
                    )
                })
            else:
                valid_li_count += 1

        if defects:
            for d in defects[:5]:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=d["message"],
                    evidence=d["evidence"],
                    page=d["page"],
                    object_reference=d["object_reference"],
                    custom_severity=Severity.HIGH,
                    custom_remediation=d["remediation"],
                    items_count=1
                ))
            if len(defects) > 5:
                rem = len(defects) - 5
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"{rem} additional list structure element(s) have invalid structural hierarchies.",
                    evidence=f"Total invalid list elements: {len(defects)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Restructure lists according to ISO 14289-1 Clause 7.4 / Matterhorn Checkpoint 28.",
                    items_count=rem
                ))
            if valid_li_count > 0:
                results.append(self.create_result(
                    status=CheckStatus.PASS,
                    message=f"{valid_li_count} of {total_li_count} list item(s) conform to ISO standard structural list hierarchies.",
                    evidence=f"Valid list items: {valid_li_count}/{total_li_count}",
                    items_count=0
                ))
        else:
            list_count = len(l_nodes) if l_nodes else len(doc.lists) or 1
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"All {list_count} list(s) ({total_li_count} list item(s)) conform to ISO standard structural list hierarchies.",
                evidence=f"Total valid list items: {total_li_count}",
                items_count=total_li_count
            ))

        return results

    def _evaluate_from_list_models(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results: List[CheckResult] = []
        invalid_lists = [l for l in doc.lists if not l.is_valid_structure]
        passed_lists = [l for l in doc.lists if l.is_valid_structure]
        fail_items_count = 1

        if invalid_lists:
            for l in invalid_lists[:5]:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"List on page {l.page} has an invalid structural hierarchy (violates L -> LI -> Lbl/LBody nesting).",
                    evidence=f"List {l.id} with {l.items_count} item(s) on page {l.page}",
                    page=l.page,
                    object_reference=f"List {l.id}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Restructure the list so each item is enclosed in an <LI> containing <Lbl> (bullet/number) and <LBody> (text).",
                    items_count=fail_items_count
                ))
            if len(invalid_lists) > 5:
                rem = len(invalid_lists) - 5
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"{rem} additional list(s) have invalid structural hierarchies.",
                    evidence=f"Invalid list count: {len(invalid_lists)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Restructure lists according to ISO 14289-1 clause 7.4.",
                    items_count=rem * fail_items_count
                ))
            if passed_lists:
                results.append(self.create_result(
                    status=CheckStatus.PASS,
                    message=f"{len(passed_lists)} of {len(doc.lists)} list(s) conform to ISO standard structural list hierarchies.",
                    evidence=f"Valid lists: {len(passed_lists)}/{len(doc.lists)}",
                    items_count=0
                ))
        else:
            total_li = sum(l.items_count for l in doc.lists) if doc.lists else len(doc.lists)
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"All {len(doc.lists)} list(s) ({total_li} list item(s)) conform to ISO standard structural list hierarchies.",
                evidence=f"Total valid list items: {total_li}",
                items_count=total_li
            ))

        return results
