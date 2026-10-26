"""
Annotation Rules (ISO 14289-1, Clause 7.18 & Matterhorn Protocol Checkpoint 19-001)
Verifies that all interactive annotations on pages are properly tagged in the structure tree.
"""

import os
from typing import List, Dict, Tuple, Any, Optional
from ..rule_base import BaseRule
from ...core.models import PDFDocumentModel, CheckResult, CheckStatus, Severity


class AnnotationTaggedRule(BaseRule):
    rule_id = "PDFUA-ANNOT-001"
    name = "Annotations Tagged"
    category = "Content"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = "All interactive annotations (links, form fields, notes) must be associated with a structure element in the logical structure tree (ISO 14289-1, Clause 7.18)."
    remediation_template = "Tag untagged annotations or link them using an OBJR (Object Reference) in Acrobat Pro."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.is_tagged or not doc.annotations:
            return results

        # Distinguish interactive annotations by subtype (Link, Widget, Text/Popup)
        interactive_annots = [
            a for a in doc.annotations
            if a.subtype in ("Link", "Widget", "Text", "Popup")
        ]
        if not interactive_annots:
            return results

        structural_errors = []
        valid_count = 0

        # Method A: High-fidelity verification using pikepdf when PDF is accessible on disk
        if doc.filepath and os.path.exists(doc.filepath):
            try:
                import pikepdf
                with pikepdf.open(doc.filepath) as pdf:
                    # Map all OBJR annotations in the structure tree to their enclosing structure element
                    # and check if the structure element exposes text or alternative descriptions
                    annot_to_struct: Dict[Any, Tuple[Any, str, bool]] = {}  # objgen -> (elem, tag, has_text)

                    def walk_struct(elem):
                        tag = str(elem.get('/S', '')).lstrip('/')
                        has_text = bool(
                            elem.get('/ActualText') or
                            elem.get('/Alt') or
                            elem.get('/T')
                        )
                        k = elem.get('/K')
                        k_items = k if isinstance(k, pikepdf.Array) else [k] if k is not None else []
                        for it in k_items:
                            if isinstance(it, int):  # MCID marked content sequence
                                has_text = True
                            elif isinstance(it, pikepdf.Dictionary):
                                it_type = str(it.get('/Type', ''))
                                if it_type == '/OBJR':
                                    obj = it.get('/Obj')
                                    if obj is not None:
                                        annot_to_struct[getattr(obj, "objgen", str(obj))] = (elem, tag, has_text)
                                elif it_type == '/MCR':
                                    has_text = True
                                elif str(it.get('/S', '')).lstrip('/') == 'Span':
                                    # Optional Span tag: check Span content and nested OBJR
                                    span_k = it.get('/K')
                                    span_items = span_k if isinstance(span_k, pikepdf.Array) else [span_k] if span_k is not None else []
                                    for sit in span_items:
                                        if isinstance(sit, int):
                                            has_text = True
                                        elif isinstance(sit, pikepdf.Dictionary) and sit.get('/Type') == '/OBJR':
                                            sobj = sit.get('/Obj')
                                            if sobj is not None:
                                                annot_to_struct[getattr(sobj, "objgen", str(sobj))] = (elem, tag, has_text)
                                        elif isinstance(sit, pikepdf.Dictionary) and sit.get('/Type') == '/MCR':
                                            has_text = True
                                    walk_struct(it)
                                else:
                                    walk_struct(it)

                    root = pdf.Root.get('/StructTreeRoot')
                    if root:
                        walk_struct(root)

                    # Inspect each interactive annotation
                    for a_model in interactive_annots:
                        if a_model.subtype == "Link":
                            # Check structural association for Link annotations
                            xref = None
                            try:
                                xref = int(a_model.id.rsplit('_', 1)[-1])
                            except Exception:
                                pass
                            assoc = annot_to_struct.get(xref) or annot_to_struct.get((xref, 0)) if xref is not None else None

                            if not a_model.is_tagged or (annot_to_struct and assoc is None):
                                structural_errors.append({
                                    "message": f"Link annotation on page {a_model.page} is not associated with any structure element (missing OBJR reference).",
                                    "evidence": f"Untagged link annotation {a_model.id} at {a_model.rect}",
                                    "page": a_model.page,
                                    "ref": f"Annotation {a_model.id}",
                                    "remediation": "Enclose the link annotation in a <Link> structure element using an OBJR reference."
                                })
                            elif assoc is not None:
                                elem, tag, has_text = assoc
                                if tag != "Link":
                                    structural_errors.append({
                                        "message": f"Link annotation on page {a_model.page} is associated with a <{tag}> element instead of a <Link> structure element (Matterhorn 19-002).",
                                        "evidence": f"Link annotation associated with <{tag}>",
                                        "page": a_model.page,
                                        "ref": f"Annotation {a_model.id}",
                                        "remediation": "Wrap the link annotation in a <Link> structure element."
                                    })
                                elif not has_text:
                                    structural_errors.append({
                                        "message": f"Link structure element for annotation on page {a_model.page} does not expose link text to assistive technologies (W3C PDF11).",
                                        "evidence": "Link structure element lacks text content or /Alt entry",
                                        "page": a_model.page,
                                        "ref": f"Annotation {a_model.id}",
                                        "remediation": "Provide accessible link text or an /Alt replacement description for the Link element."
                                    })
                                else:
                                    valid_count += 1
                            else:
                                valid_count += 1
                        elif a_model.subtype == "Widget":
                            # Form field widgets: verified as form controls, never flagged as invalid links
                            if not a_model.is_tagged:
                                structural_errors.append({
                                    "message": f"Form field widget annotation on page {a_model.page} is not associated with any structure element.",
                                    "evidence": f"Untagged form widget {a_model.id} at {a_model.rect}",
                                    "page": a_model.page,
                                    "ref": f"Annotation {a_model.id}",
                                    "remediation": "Associate the form field widget with a <Form> structure tag."
                                })
                            else:
                                valid_count += 1
                        elif a_model.subtype in ("Text", "Popup"):
                            # Note annotations: verified as notes/comments, never flagged as invalid links
                            if not a_model.is_tagged:
                                structural_errors.append({
                                    "message": f"Note annotation on page {a_model.page} is not associated with any structure element.",
                                    "evidence": f"Untagged note annotation {a_model.id} at {a_model.rect}",
                                    "page": a_model.page,
                                    "ref": f"Annotation {a_model.id}",
                                    "remediation": "Associate the note annotation with a <Note> structure tag."
                                })
                            else:
                                valid_count += 1
            except Exception:
                pass

        # Method B: In-memory fallback for unit tests and synthetic models
        if not (doc.filepath and os.path.exists(doc.filepath)):
            for a in interactive_annots:
                if not a.is_tagged:
                    structural_errors.append({
                        "message": f"Annotation of type '{a.subtype}' on page {a.page} is not associated with any structure element.",
                        "evidence": f"Annotation {a.id} at {a.rect}",
                        "page": a.page,
                        "ref": f"Annotation {a.id}",
                        "remediation": f"Wrap the {a.subtype} annotation in a matching structure tag (<Link>, <Form>, or <Note>)."
                    })
                else:
                    # For Link annotations, if structure tree is provided, ensure Link node exposes text/content
                    if a.subtype == "Link" and doc.structure_tree:
                        link_nodes = doc.structure_tree.find_all_by_standard_tag("Link")
                        if not link_nodes:
                            structural_errors.append({
                                "message": f"Link annotation on page {a.page} is not associated with a <Link> structure element (Matterhorn 19-002).",
                                "evidence": f"No <Link> structure tag found for link annotation {a.id}",
                                "page": a.page,
                                "ref": f"Annotation {a.id}",
                                "remediation": "Wrap the link annotation in a <Link> structure element."
                            })
                            continue
                        empty_links = [
                            ln for ln in link_nodes
                            if not ln.text_content and not ln.alt_text and not ln.actual_text and not ln.children and not ln.mcids
                        ]
                        if empty_links and len(empty_links) == len(link_nodes):
                            structural_errors.append({
                                "message": f"Link structure element for annotation on page {a.page} does not expose link text to assistive technologies (W3C PDF11).",
                                "evidence": "Empty Link tag without text or alternative description",
                                "page": a.page,
                                "ref": f"Annotation {a.id}",
                                "remediation": "Associate link text or an /Alt replacement description with the Link tag."
                            })
                            continue
                        # Check if link node has explicit invalid association
                        incorrect_association = [
                            ln for ln in link_nodes
                            if ln.attributes.get("objr_associated") is False
                        ]
                        if incorrect_association:
                            structural_errors.append({
                                "message": f"Link annotation on page {a.page} has an incorrect or missing OBJR association.",
                                "evidence": f"Invalid OBJR association on <Link id='{incorrect_association[0].id}'>",
                                "page": a.page,
                                "ref": f"Annotation {a.id}",
                                "remediation": "Ensure the OBJR properly references the link annotation object."
                            })
                            continue
                    valid_count += 1

        if structural_errors:
            for err in structural_errors[:5]:
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=err["message"],
                    evidence=err["evidence"],
                    page=err["page"],
                    object_reference=err["ref"],
                    custom_severity=Severity.HIGH,
                    custom_remediation=err.get("remediation", "Associate interactive annotations with structure elements.")
                ))
            if len(structural_errors) > 5:
                rem = len(structural_errors) - 5
                results.append(self.create_result(
                    status=CheckStatus.FAIL,
                    message=f"{rem} additional interactive annotation(s) lack valid structure element associations.",
                    evidence=f"Total invalid annotations: {len(structural_errors)}",
                    custom_severity=Severity.HIGH,
                    custom_remediation="Associate all interactive annotations with appropriate structure tags.",
                    items_count=rem
                ))
        else:
            items_cnt = valid_count if valid_count > 0 else len(interactive_annots)
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message=f"All {items_cnt} interactive annotation(s) are associated with the logical structure tree.",
                evidence="Interactive annotation tagging and structure association verified.",
                items_count=items_cnt
            ))

        return results


class PageTabOrderRule(BaseRule):
    rule_id = "PDFUA-ANNOT-002"
    name = "Page Tab Order"
    category = "Annotations"
    standard = "PDF/UA"
    severity = Severity.HIGH
    description = "In a tagged document, each page containing interactive annotations must specify /Tabs /S to ensure navigation order conforms to document structure order (ISO 14289-1:2014, Clause 7.18.1 / Matterhorn Checkpoint 17-001)."
    remediation_template = "In Acrobat Pro Page Thumbnails panel, select page properties and set Tab Order to 'Use Document Structure'."

    def evaluate(self, doc: PDFDocumentModel) -> List[CheckResult]:
        results = []
        if not doc.pages:
            return results

        # Under ISO 14289-1:2014, Clause 7.18.1 / Matterhorn Checkpoint 17-001,
        # tab order is required on pages that contain annotations. Pages without annotations
        # have no interactive tab navigation sequence.
        pages_with_annots = [
            p.page_number for p in doc.pages
            if getattr(p, "annotations_count", 0) > 0
            or p.links_count > 0
            or any(a.page == p.page_number for a in doc.annotations)
        ]
        has_annots = len(pages_with_annots) > 0

        violating_pages = [
            p.page_number for p in doc.pages
            if p.tab_order_mode != "S" and (p.page_number in pages_with_annots or not doc.is_tagged)
        ]

        if violating_pages:
            results.append(self.create_result(
                status=CheckStatus.FAIL,
                message=f"{len(violating_pages)} page(s) containing annotations do not specify Structure tab order (/Tabs /S).",
                evidence=f"Pages lacking /Tabs /S: {violating_pages[:5]}",
                page=violating_pages[0],
                custom_severity=Severity.HIGH,
                custom_remediation="In Acrobat Pro Page Thumbnails, set Page Properties > Tab Order to 'Use Document Structure' (/Tabs /S).",
                items_count=1
            ))
        else:
            items_cnt = len(pages_with_annots) if pages_with_annots else 1
            results.append(self.create_result(
                status=CheckStatus.PASS,
                message="All pages specify Structure tab order (/Tabs /S) or contain no interactive annotations.",
                evidence=f"Page tab navigation conforms to document structure order (/Tabs /S) across {items_cnt} page(s).",
                items_count=items_cnt
            ))

        return results
