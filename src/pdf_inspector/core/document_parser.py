"""
PDF Document Parser
Combines pikepdf (deep PDF structural dictionary inspection, StructTreeRoot, ParentTree)
and pymupdf (high-speed rendering, text extraction, visual bounding boxes, annotations)
into a unified, exhaustive PDFDocumentModel.
"""

from typing import Dict, List, Optional, Tuple, Any, Set
import os
import re
import logging
import pikepdf
import pymupdf

from .models import (
    PDFDocumentModel, PageModel, StructureNode, FontModel,
    ImageModel, TableModel, ListModel, LinkModel, FormFieldModel,
    AnnotationModel, BookmarkModel, ArtifactOccurrenceModel, ContentOccurrenceModel,
    FormXObjectModel
)
from .structure_tree import StructureTreeParser, resolve_role, parse_number_tree

logger = logging.getLogger(__name__)

# Regex for parsing marked content sequences in PDF content streams
MCID_PATTERN = re.compile(r"/(\w+)\s*<<\s*[^>]*?/MCID\s+(\d+)[^>]*?>>\s*BDC", re.DOTALL)
ARTIFACT_PATTERN = re.compile(r"/Artifact(?:\s*<<[^>]*?>>)?\s*B[DM]C", re.DOTALL)
ART_XOBJECT_PATTERN = re.compile(r'(/(\w+)\s*(?:<<.*?>>)?\s*B[DM]C)|(\bEMC\b)|(/(\w+)\s+Do\b)', re.DOTALL)
CONTENT_TOKEN_PATTERN = re.compile(r'(/(\w+)\s+(<<.*?>>|/\w+)\s*BDC|/(\w+)\s+BMC|(\bEMC\b)|(/(\w+)\s+Do\b))', re.DOTALL)


class DocumentParser:
    """Parses a PDF file into a complete, in-memory PDFDocumentModel."""

    def __init__(self, filepath: str, password: Optional[str] = None):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.filesize = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        self.password = password

    def parse(self) -> PDFDocumentModel:
        """Executes full document extraction."""
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"PDF file does not exist: {self.filepath}")

        try:
            pike_doc = pikepdf.open(self.filepath, password=self.password or "")
        except pikepdf.PasswordError:
            raise PermissionError("Password required — analysis cannot continue until the document is unlocked.")
        except pikepdf.PdfError as pe:
            raise ValueError(f"PDF '{self.filename}' is corrupt or malformed: {pe}")
        except Exception as e:
            raise RuntimeError(f"Failed to open PDF '{self.filename}': {e}")

        try:
            fitz_doc = pymupdf.open(self.filepath)
            if fitz_doc.needs_pass:
                if self.password:
                    auth_success = fitz_doc.authenticate(self.password)
                    if not auth_success:
                        pike_doc.close()
                        fitz_doc.close()
                        raise PermissionError("Password required — analysis cannot continue until the document is unlocked.")
                else:
                    pike_doc.close()
                    fitz_doc.close()
                    raise PermissionError("Password required — analysis cannot continue until the document is unlocked.")
        except PermissionError:
            raise
        except Exception as e:
            pike_doc.close()
            raise ValueError(f"Failed to render PDF '{self.filename}': {e}")

        try:
            # 1. Basic Document Information
            pdf_version = str(getattr(pike_doc, "pdf_version", "1.7"))
            page_count = len(fitz_doc)

            # Metadata from Info dictionary
            doc_info = {}
            if "/Info" in pike_doc.trailer:
                info_dict = pike_doc.trailer["/Info"]
                for k, v in info_dict.items():
                    key = str(k).strip("/")
                    try:
                        doc_info[key] = str(v)
                    except Exception:
                        doc_info[key] = ""

            doc_info_title = doc_info.get("Title")
            doc_info_author = doc_info.get("Author")
            doc_info_subject = doc_info.get("Subject")
            doc_info_keywords = doc_info.get("Keywords")
            creator = doc_info.get("Creator")
            producer = doc_info.get("Producer")
            creation_date = doc_info.get("CreationDate")
            mod_date = doc_info.get("ModDate")

            # Document language
            language = None
            if "/Lang" in pike_doc.Root:
                language = str(pike_doc.Root["/Lang"]).strip()

            # Tagged PDF check
            is_tagged = False
            if "/MarkInfo" in pike_doc.Root:
                mark_info = pike_doc.Root["/MarkInfo"]
                if isinstance(mark_info, pikepdf.Dictionary) and "/Marked" in mark_info:
                    is_tagged = bool(mark_info["/Marked"])

            # Encryption / Extraction permissions
            is_encrypted = pike_doc.is_encrypted
            allows_extraction = True
            if is_encrypted:
                try:
                    allows_extraction = fitz_doc.permissions & pymupdf.PDF_PERM_ACCESSIBILITY != 0
                except Exception:
                    allows_extraction = True

            # ViewerPreferences -> DisplayDocTitle
            display_doc_title = False
            if "/ViewerPreferences" in pike_doc.Root:
                vp = pike_doc.Root["/ViewerPreferences"]
                if isinstance(vp, pikepdf.Dictionary) and "/DisplayDocTitle" in vp:
                    display_doc_title = bool(vp["/DisplayDocTitle"])

            # MarkInfo -> Suspects (ISO 14289-1 Clause 7.18, Matterhorn Checkpoint 31-003)
            has_suspects = False
            if "/MarkInfo" in pike_doc.Root:
                mi = pike_doc.Root["/MarkInfo"]
                if isinstance(mi, pikepdf.Dictionary) and "/Suspects" in mi:
                    has_suspects = bool(mi["/Suspects"])

            # XMP Metadata & PDF/UA Identification
            xmp_metadata_present = "/Metadata" in pike_doc.Root
            xmp_dc_title = None
            xmp_dc_creator = None
            xmp_dc_description = None
            pdfua_identifier_present = False
            pdfua_part = None

            if xmp_metadata_present:
                try:
                    meta_bytes = bytes(pike_doc.Root.Metadata.read_bytes())
                    meta_str = meta_bytes.decode("utf-8", errors="ignore")

                    # Dublin Core Title (<dc:title>)
                    m_title_block = re.search(r"<dc:title\b[^>]*>(.*?)</dc:title>", meta_str, re.DOTALL | re.IGNORECASE)
                    if m_title_block:
                        block = m_title_block.group(1)
                        m_li = re.search(r"<rdf:li\b[^>]*>(.*?)</rdf:li>", block, re.DOTALL | re.IGNORECASE)
                        if m_li and m_li.group(1).strip():
                            xmp_dc_title = m_li.group(1).strip()
                        elif "<rdf:" not in block and block.strip():
                            xmp_dc_title = block.strip()

                    # Dublin Core Creator (<dc:creator>)
                    m_creator_block = re.search(r"<dc:creator\b[^>]*>(.*?)</dc:creator>", meta_str, re.DOTALL | re.IGNORECASE)
                    if m_creator_block:
                        block = m_creator_block.group(1)
                        m_li = re.search(r"<rdf:li\b[^>]*>(.*?)</rdf:li>", block, re.DOTALL | re.IGNORECASE)
                        if m_li and m_li.group(1).strip():
                            xmp_dc_creator = m_li.group(1).strip()
                        elif "<rdf:" not in block and block.strip():
                            xmp_dc_creator = block.strip()

                    # Dublin Core Description (<dc:description>)
                    m_desc_block = re.search(r"<dc:description\b[^>]*>(.*?)</dc:description>", meta_str, re.DOTALL | re.IGNORECASE)
                    if m_desc_block:
                        block = m_desc_block.group(1)
                        m_li = re.search(r"<rdf:li\b[^>]*>(.*?)</rdf:li>", block, re.DOTALL | re.IGNORECASE)
                        if m_li and m_li.group(1).strip():
                            xmp_dc_description = m_li.group(1).strip()
                        elif "<rdf:" not in block and block.strip():
                            xmp_dc_description = block.strip()

                    # PDF/UA Identification (pdfuaid:part)
                    m_part = re.search(r"<pdfuaid:part>(\d+)</pdfuaid:part>", meta_str, re.IGNORECASE)
                    if m_part:
                        pdfua_identifier_present = True
                        pdfua_part = int(m_part.group(1))
                    elif "pdfuaid" in meta_str.lower() or "iso 14289" in meta_str.lower():
                        pdfua_identifier_present = True
                        pdfua_part = 1
                except Exception as e:
                    logger.debug(f"Failed parsing XMP stream: {e}")

            # Display title preference: prefer XMP dc:title, fallback to Info title for UI display
            title = xmp_dc_title or doc_info_title

            # ParentTree & RoleMap
            has_parent_tree = False
            parent_tree_valid = False
            parent_tree_entries_count = 0
            role_map: Dict[str, str] = {}

            if "/StructTreeRoot" in pike_doc.Root:
                struct_root = pike_doc.Root["/StructTreeRoot"]
                if "/RoleMap" in struct_root and isinstance(struct_root["/RoleMap"], pikepdf.Dictionary):
                    for custom_tag, mapped_tag in struct_root["/RoleMap"].items():
                        role_map[str(custom_tag).strip("/")] = str(mapped_tag).strip("/")

                if "/ParentTree" in struct_root:
                    has_parent_tree = True
                    try:
                        pt_entries = parse_number_tree(struct_root["/ParentTree"])
                        parent_tree_entries_count = len(pt_entries)
                        parent_tree_valid = parent_tree_entries_count > 0
                    except Exception as e:
                        logger.debug(f"Error parsing ParentTree: {e}")

            # Page mapping for Structure Tree
            page_map = {}
            for idx, p in enumerate(pike_doc.pages, start=1):
                if hasattr(p, "objgen"):
                    page_map[p.objgen] = idx
                    page_map[p.objgen[0]] = idx
                page_map[id(p)] = idx

            # 2. Extract Pages with MCIDs, content occurrences, artifacts, and geometry
            pages: List[PageModel] = []
            page_mcid_data: Dict[int, Dict[int, Tuple[str, Tuple[float, float, float, float]]]] = {}
            page_artifact_xobjs: Dict[int, Set[str]] = {}
            doc_artifact_xobjs: Set[str] = set()
            xobject_artifact_cache: Dict[int, Tuple[int, List[str]]] = {}

            parent_tree_map: Dict[int, Any] = {}
            if "/StructTreeRoot" in pike_doc.Root and "/ParentTree" in pike_doc.Root["/StructTreeRoot"]:
                try:
                    raw_pt = parse_number_tree(pike_doc.Root["/StructTreeRoot"]["/ParentTree"])
                    for sp_id, val in raw_pt.items():
                        if isinstance(val, (pikepdf.Array, list)):
                            arr = []
                            for item in val:
                                if item is None or (isinstance(item, pikepdf.Object) and str(item) == "null"):
                                    arr.append(None)
                                elif isinstance(item, (pikepdf.Dictionary, dict)):
                                    og = getattr(item, "objgen", (None, None))[0] if hasattr(item, "objgen") else None
                                    s_tag = str(item.get("/S", "")).strip("/")
                                    t_val = str(item.get("/Type", "")).strip("/")
                                    has_p = bool(item.get("/P"))
                                    p_obj = item.get("/P") if hasattr(item, "get") else None
                                    p_og = getattr(p_obj, "objgen", (None, None))[0] if hasattr(p_obj, "objgen") else None
                                    arr.append({
                                        "obj_num": og,
                                        "tag": s_tag,
                                        "type": t_val,
                                        "has_parent": has_p,
                                        "parent_obj_num": p_og
                                    })
                                else:
                                    arr.append({"obj_num": None, "tag": str(item), "type": "", "has_parent": False, "parent_obj_num": None})
                            parent_tree_map[sp_id] = arr
                        elif isinstance(val, (pikepdf.Dictionary, dict)):
                            og = getattr(val, "objgen", (None, None))[0] if hasattr(val, "objgen") else None
                            p_obj = val.get("/P") if hasattr(val, "get") else None
                            p_og = getattr(p_obj, "objgen", (None, None))[0] if hasattr(p_obj, "objgen") else None
                            parent_tree_map[sp_id] = {
                                "obj_num": og,
                                "tag": str(val.get("/S", "")).strip("/"),
                                "type": str(val.get("/Type", "")).strip("/"),
                                "has_parent": bool(val.get("/P")),
                                "parent_obj_num": p_og
                            }
                except Exception as e:
                    logger.debug(f"Error parsing parent tree: {e}")

            font_cmap_cache: Dict[Any, Dict[int, str]] = {}

            STREAM_TOKEN_RE = re.compile(
                r'(?P<bdc>/(\w+)\s*(<<.*?>>|/\w+)\s*BDC)'
                r'|(?P<bmc>/(\w+)\s*BMC)'
                r'|(?P<emc>\bEMC\b)'
                r'|(?P<do>/(\w+)\s+Do\b)'
                r'|(?P<text_tj>(?:\((?:\\.|[^()\\])*\)|\[(?:\\.|[^\]\\])*\])\s*(?:TJ|Tj|\'|"))'
                r'|(?P<paint>\b(?:sh|f\*|b\*|B\*|f|F|S|s|B|b)\b)',
                re.DOTALL
            )

            for page_idx, pike_page in enumerate(pike_doc.pages, start=1):
                fitz_page = fitz_doc[page_idx - 1]
                rect = fitz_page.rect
                rotation = fitz_page.rotation
                text = fitz_page.get_text("text")

                # Check Tab order and StructParents on page dictionary
                tab_mode = "Unspecified"
                has_tab = False
                annots_count = 0
                struct_parents_id = None
                mcids_found: List[int] = []
                mcid_bboxes: Dict[int, Tuple[float, float, float, float]] = {}
                mcid_texts: Dict[int, str] = {}
                art_xobjs: Set[str] = set()
                page_artifacts: List[ArtifactOccurrenceModel] = []
                page_content_occs: List[ContentOccurrenceModel] = []
                unmarked_count = 0
                tagged_ops_count = 0
                art_ops_count = 0
                tagged_in_art_count = 0
                art_in_tagged_count = 0

                # Collect direct XObjects defined on this page
                xobj_info: Dict[str, Dict[str, Any]] = {}
                try:
                    for xo in fitz_page.get_xobjects():
                        # xo is (xref, name, invoker, rect)
                        is_direct = (xo[2] == 0)
                        if is_direct or xo[1] not in xobj_info:
                            xobj_info[xo[1]] = {"xref": xo[0], "rect": xo[3]}
                except Exception as e:
                    logger.debug(f"Error checking page xobjects: {e}")

                try:
                    if "/Annots" in pike_page:
                        try:
                            annots_count = len(pike_page["/Annots"])
                        except Exception:
                            annots_count = 0

                    if "/Tabs" in pike_page:
                        has_tab = True
                        tab_mode = str(pike_page["/Tabs"]).strip("/")

                    if "/StructParents" in pike_page:
                        try:
                            struct_parents_id = int(pike_page["/StructParents"])
                        except Exception:
                            struct_parents_id = None

                    # Also collect MCIDs from Form XObjects on this page
                    if "/Resources" in pike_page and "/XObject" in pike_page["/Resources"]:
                        try:
                            xo_dict = pike_page["/Resources"]["/XObject"]
                            for _, xo in xo_dict.items():
                                if hasattr(xo, "read_bytes"):
                                    xo_stream = xo.read_bytes().decode("latin1", errors="ignore")
                                    for xo_m in MCID_PATTERN.finditer(xo_stream):
                                        x_mcid = int(xo_m.group(2))
                                        if x_mcid not in mcids_found:
                                            mcids_found.append(x_mcid)
                        except Exception:
                            pass

                    # Parse MCIDs, Artifacts, and marked content tokens from page contents stream
                    if "/Contents" in pike_page:
                        contents_obj = pike_page["/Contents"]
                        raw_stream = b""
                        if isinstance(contents_obj, pikepdf.Array):
                            for stream_part in contents_obj:
                                if hasattr(stream_part, "read_bytes"):
                                    raw_stream += stream_part.read_bytes() + b"\n"
                        elif hasattr(contents_obj, "read_bytes"):
                            raw_stream = contents_obj.read_bytes()

                        stream_text = raw_stream.decode("latin1", errors="ignore")
                        for match in MCID_PATTERN.finditer(stream_text):
                            mcid_num = int(match.group(2))
                            if mcid_num not in mcids_found:
                                mcids_found.append(mcid_num)

                        # Marked content stack tracking
                        stack: List[Dict[str, Any]] = []

                        for m in STREAM_TOKEN_RE.finditer(stream_text):
                            if m.group("bdc"):
                                bdc_m = re.match(r"/(\w+)\s*(<<.*?>>|/\w+)\s*BDC", m.group("bdc"), re.DOTALL)
                                tag = bdc_m.group(1) if bdc_m else "Span"
                                props = bdc_m.group(2) if bdc_m else ""
                                mcid = None
                                if props.startswith("<<") and "/MCID" in props:
                                    mc_match = re.search(r"/MCID\s+(\d+)", props)
                                    if mc_match:
                                        mcid = int(mc_match.group(1))

                                is_art = (tag.lower() == "artifact" or "/artifact" in props.lower())
                                in_tagged = any(s["mcid"] is not None for s in stack)
                                in_art = any(s["is_artifact"] for s in stack)

                                if is_art:
                                    if in_tagged:
                                        art_in_tagged_count += 1
                                        ancestor = next(s for s in reversed(stack) if s["mcid"] is not None)
                                        page_artifacts.append(ArtifactOccurrenceModel(
                                            page_number=page_idx,
                                            is_inside_tagged=True,
                                            parent_tag=ancestor["tag"],
                                            parent_mcid=ancestor["mcid"],
                                            bbox=None,
                                            text_snippet=""
                                        ))
                                    else:
                                        page_artifacts.append(ArtifactOccurrenceModel(
                                            page_number=page_idx,
                                            is_inside_tagged=False
                                        ))
                                else:
                                    if in_art and mcid is not None:
                                        tagged_in_art_count += 1
                                        page_content_occs.append(ContentOccurrenceModel(
                                            page_number=page_idx,
                                            operator_type="marked_content",
                                            operator_name="BDC",
                                            mcid=mcid,
                                            tag=tag,
                                            is_inside_artifact=True
                                        ))

                                stack.append({"tag": tag, "mcid": mcid, "is_artifact": is_art})

                            elif m.group("bmc"):
                                bmc_m = re.match(r"/(\w+)\s*BMC", m.group("bmc"))
                                tag = bmc_m.group(1) if bmc_m else "Span"
                                is_art = (tag.lower() == "artifact")
                                in_tagged = any(s["mcid"] is not None for s in stack)
                                in_art = any(s["is_artifact"] for s in stack)

                                if is_art:
                                    if in_tagged:
                                        art_in_tagged_count += 1
                                        ancestor = next(s for s in reversed(stack) if s["mcid"] is not None)
                                        page_artifacts.append(ArtifactOccurrenceModel(
                                            page_number=page_idx,
                                            is_inside_tagged=True,
                                            parent_tag=ancestor["tag"],
                                            parent_mcid=ancestor["mcid"],
                                            bbox=None,
                                            text_snippet=""
                                        ))
                                    else:
                                        page_artifacts.append(ArtifactOccurrenceModel(
                                            page_number=page_idx,
                                            is_inside_tagged=False
                                        ))

                                stack.append({"tag": tag, "mcid": None, "is_artifact": is_art})

                            elif m.group("emc"):
                                if stack:
                                    stack.pop()

                            elif m.group("text_tj"):
                                tj_txt = m.group("text_tj")
                                in_tagged = any(s["mcid"] is not None for s in stack)
                                in_art = any(s["is_artifact"] for s in stack)
                                if in_tagged and not in_art:
                                    tagged_ops_count += 1
                                elif in_art:
                                    art_ops_count += 1
                                else:
                                    # Text operator executed outside of any marked content sequence
                                    unmarked_count += 1
                                    page_content_occs.append(ContentOccurrenceModel(
                                        page_number=page_idx,
                                        operator_type="text",
                                        operator_name="Tj/TJ",
                                        is_unmarked_real_content=True,
                                        snippet=tj_txt[:60]
                                    ))

                            elif m.group("paint"):
                                paint_op = m.group("paint")
                                in_tagged = any(s["mcid"] is not None for s in stack)
                                in_art = any(s["is_artifact"] for s in stack)
                                if in_tagged and not in_art:
                                    tagged_ops_count += 1
                                elif in_art:
                                    art_ops_count += 1
                                else:
                                    # Path painting outside marked content
                                    unmarked_count += 1
                                    page_content_occs.append(ContentOccurrenceModel(
                                        page_number=page_idx,
                                        operator_type="path",
                                        operator_name=paint_op,
                                        is_unmarked_real_content=True
                                    ))

                            elif m.group("do"):
                                do_m = re.match(r"/(\w+)\s+Do", m.group("do"))
                                xname = do_m.group(1) if do_m else ""
                                in_tagged = any(s["mcid"] is not None for s in stack)
                                in_art = any(s["is_artifact"] for s in stack)
                                if in_tagged and not in_art:
                                    tagged_ops_count += 1
                                elif in_art:
                                    art_ops_count += 1

                                if any(s["tag"].lower() == "artifact" for s in stack):
                                    art_xobjs.add(xname)
                                    doc_artifact_xobjs.add(xname)

                                if xname in xobj_info:
                                    xo_entry = xobj_info[xname]
                                    xref = xo_entry["xref"]
                                    xo_rect = xo_entry["rect"]

                                    if xref not in xobject_artifact_cache:
                                        try:
                                            xo_stream = fitz_doc.xref_stream(xref).decode("latin1", errors="ignore")
                                            xo_art_matches = ARTIFACT_PATTERN.findall(xo_stream)
                                            snippets: List[str] = []
                                            for art_block in re.findall(r"/Artifact\s*(?:<<.*?>>)?\s*B[DM]C(.*?)EMC", xo_stream, re.DOTALL):
                                                tjs = re.findall(r"\(([^)]+)\)\s*Tj|\[(.*?)\]\s*TJ", art_block)
                                                for tj_str, tj_arr in tjs:
                                                    s_txt = tj_str or tj_arr
                                                    parts = re.findall(r"\((.*?)\)", s_txt) if tj_arr else [tj_str]
                                                    cleaned = re.sub(r"\\[0-7]{1,3}", "", " ".join(parts))
                                                    cleaned = re.sub(r"\\[nrtbf\\()]", "", cleaned).strip()
                                                    if sum(c.isalnum() for c in cleaned) >= 3:
                                                        snippets.append(cleaned)
                                            if not snippets and xo_rect:
                                                try:
                                                    cb = fitz_page.cropbox
                                                    r_fitz = pymupdf.Rect(xo_rect[0] - cb.x0, cb.y1 - xo_rect[3], xo_rect[2] - cb.x0 + 10, cb.y1 - xo_rect[1] + 10)
                                                    nearby_words = [w[4] for w in fitz_page.get_text("words") if pymupdf.Rect(w[:4]).intersects(r_fitz) or abs(w[0] - (xo_rect[0] - cb.x0)) < 15]
                                                    if nearby_words:
                                                        snippets.append(" ".join(nearby_words[:12]))
                                                except Exception:
                                                    pass
                                            xo_has_mcid = bool(re.search(r"/MCID", xo_stream))
                                            xo_has_paint = bool(re.search(r"\b(re|Do|Tj|TJ|'|\"|f\*?|F|s|S|b\*?|B\*?|m|l)\b", xo_stream))
                                            xobject_artifact_cache[xref] = (len(xo_art_matches), snippets, xo_has_mcid, xo_has_paint)
                                        except Exception:
                                            xobject_artifact_cache[xref] = (0, [], False, False)

                                    xo_arts_cnt, xo_snippets, xo_has_mcid, xo_has_paint = xobject_artifact_cache[xref]
                                    if xo_arts_cnt > 0:
                                        doc_artifact_xobjs.add(xname)
                                        snippet_text = xo_snippets[0] if xo_snippets else ""
                                        bbox_tuple = (float(xo_rect[0]), float(xo_rect[1]), float(xo_rect[2]), float(xo_rect[3])) if xo_rect else None

                                        if in_tagged:
                                            art_in_tagged_count += xo_arts_cnt
                                            ancestor = next(s for s in reversed(stack) if s["mcid"] is not None)
                                            for _ in range(xo_arts_cnt):
                                                page_artifacts.append(ArtifactOccurrenceModel(
                                                    page_number=page_idx,
                                                    is_inside_tagged=True,
                                                    parent_tag=ancestor["tag"],
                                                    parent_mcid=ancestor["mcid"],
                                                    xobject_name=xname,
                                                    xobject_xref=xref,
                                                    bbox=bbox_tuple,
                                                    text_snippet=snippet_text
                                                ))
                                        else:
                                            for _ in range(xo_arts_cnt):
                                                page_artifacts.append(ArtifactOccurrenceModel(
                                                    page_number=page_idx,
                                                    is_inside_tagged=False,
                                                    xobject_name=xname,
                                                    xobject_xref=xref,
                                                    bbox=bbox_tuple,
                                                    text_snippet=snippet_text
                                                ))
                                    elif not in_tagged and not in_art:
                                        # Form XObject containing real content executed outside marked content
                                        is_doc_art = (
                                            xname in doc_artifact_xobjs
                                            or any(xname in s for s in page_artifact_xobjs.values())
                                        )
                                        if xo_has_paint and not xo_has_mcid and not is_doc_art:
                                            unmarked_count += 1
                                            page_content_occs.append(ContentOccurrenceModel(
                                                page_number=page_idx,
                                                operator_type="xobject",
                                                operator_name="Do",
                                                is_unmarked_real_content=True,
                                                xobject_name=xname,
                                                snippet=f"XObject /{xname} Do"
                                            ))
                                elif not in_tagged and not in_art:
                                    # XObject Do outside marked content and not in xobj_info
                                    is_doc_art = (
                                        xname in doc_artifact_xobjs
                                        or any(xname in s for s in page_artifact_xobjs.values())
                                    )
                                    if not is_doc_art:
                                        unmarked_count += 1
                                        page_content_occs.append(ContentOccurrenceModel(
                                            page_number=page_idx,
                                            operator_type="xobject",
                                            operator_name="Do",
                                            is_unmarked_real_content=True,
                                            xobject_name=xname,
                                            snippet=f"XObject /{xname} Do"
                                        ))

                except Exception as e:
                    logger.debug(f"Error checking page dictionary: {e}")

                page_artifact_xobjs[page_idx] = art_xobjs

                # Image and link counts
                img_list = fitz_page.get_images()
                links_list = fitz_page.get_links()

                # Decode true MCID texts from page content stream using font ToUnicode CMaps
                if mcids_found:
                    mcid_texts = self._decode_page_mcid_texts(pike_page, font_cmap_cache)
                    blocks = fitz_page.get_text("blocks")
                    for idx, b in enumerate(blocks):
                        if idx < len(mcids_found):
                            target_mcid = mcids_found[idx]
                            mcid_bboxes[target_mcid] = (b[0], b[1], b[2], b[3])

                page_mcid_data[page_idx] = {
                    mcid: (mcid_texts.get(mcid, ""), mcid_bboxes.get(mcid, (0, 0, 0, 0)))
                    for mcid in mcids_found
                }

                pages.append(PageModel(
                    page_number=page_idx,
                    width=rect.width,
                    height=rect.height,
                    rotation=rotation,
                    text=text,
                    images_count=len(img_list),
                    links_count=len(links_list),
                    has_structure=is_tagged and (len(mcids_found) > 0 or len(page_artifacts) > 0),
                    has_tab_order=has_tab,
                    tab_order_mode=tab_mode,
                    struct_parents_id=struct_parents_id,
                    mcids=mcids_found,
                    mcid_bboxes=mcid_bboxes,
                    mcid_texts=mcid_texts,
                    artifacts=page_artifacts,
                    content_occurrences=page_content_occs,
                    unmarked_real_content_count=unmarked_count,
                    tagged_operations_count=tagged_ops_count,
                    artifact_operations_count=art_ops_count,
                    tagged_in_artifact_count=tagged_in_art_count,
                    artifact_in_tagged_count=art_in_tagged_count,
                    annotations_count=annots_count
                ))

            # 3. Structure Tree
            tree_parser = StructureTreeParser(pike_doc, role_map, page_map, page_mcid_data)
            structure_tree = tree_parser.parse()

            # Reconcile structure tree MCIDs into pages and reconcile tagged_in_artifact_count
            tree_mcids_by_page: Dict[int, Set[int]] = {}
            if structure_tree:
                for node in structure_tree.find_all_nodes():
                    if node.page:
                        if node.page not in tree_mcids_by_page:
                            tree_mcids_by_page[node.page] = set()
                        tree_mcids_by_page[node.page].update(node.mcids)

            for p in pages:
                page_tree_mcids = tree_mcids_by_page.get(p.page_number, set())
                # Reconcile tagged_in_artifact_count:
                # In PDF/UA (ISO 14289-1 7.1 / Matterhorn 01-004), content is only tagged if referenced in the structure tree.
                real_tagged_in_art = [
                    occ for occ in p.content_occurrences
                    if occ.is_inside_artifact and occ.mcid is not None and occ.mcid in page_tree_mcids
                ]
                p.tagged_in_artifact_count = len(real_tagged_in_art)

            # 4. Extract Fonts
            fonts = self._extract_fonts(fitz_doc, pike_doc)

            # 5. Extract Images & Figures
            images = self._extract_images(fitz_doc, structure_tree, page_artifact_xobjs)

            # 6. Extract Tables
            tables = self._extract_tables(structure_tree)

            # 7. Extract Lists (<L>)
            lists = self._extract_lists(structure_tree)

            # 8. Extract Links
            links = self._extract_links(fitz_doc, structure_tree)

            # 9. Extract Form Fields
            form_fields = self._extract_form_fields(fitz_doc, pike_doc)

            # 10. Extract Annotations
            annotations = self._extract_annotations(fitz_doc, pike_doc, structure_tree)

            # 11. Extract Bookmarks
            bookmarks = self._extract_bookmarks(fitz_doc)

            # 12. Check Embedded Files count
            try:
                embedded_files_count = fitz_doc.embfile_count()
            except Exception:
                embedded_files_count = 0

            if "/AF" in pike_doc.Root:
                try:
                    embedded_files_count += len(pike_doc.Root["/AF"])
                except Exception:
                    pass

            # 13. Extract and validate unique Form XObjects in document resources (ISO 32000-1 Clause 8.10)
            form_xobjects: List[FormXObjectModel] = []
            seen_form_xrefs = set()
            try:
                def process_form_xobject(xobj):
                    if not xobj:
                        return
                    og = getattr(xobj, "objgen", None)
                    ref_key = og if og is not None else id(xobj)
                    if ref_key in seen_form_xrefs:
                        return
                    seen_form_xrefs.add(ref_key)

                    if isinstance(xobj, pikepdf.Stream) and xobj.get("/Subtype") == "/Form":
                        bbox_obj = xobj.get("/BBox")
                        has_valid_bbox = False
                        parsed_bbox = None
                        if isinstance(bbox_obj, pikepdf.Array) and len(bbox_obj) == 4:
                            try:
                                coords = [float(c) for c in bbox_obj]
                                parsed_bbox = (coords[0], coords[1], coords[2], coords[3])
                                has_valid_bbox = True
                            except (ValueError, TypeError):
                                has_valid_bbox = False

                        matrix_valid = True
                        has_matrix = "/Matrix" in xobj
                        if has_matrix:
                            m_obj = xobj.get("/Matrix")
                            if not isinstance(m_obj, pikepdf.Array) or len(m_obj) != 6:
                                matrix_valid = False
                            else:
                                try:
                                    _ = [float(c) for c in m_obj]
                                except (ValueError, TypeError):
                                    matrix_valid = False

                        sp_val = int(xobj["/StructParents"]) if "/StructParents" in xobj else None
                        is_valid = has_valid_bbox and matrix_valid
                        err_msg = ""
                        if not has_valid_bbox:
                            err_msg = "Form XObject dictionary lacks valid /BBox 4-element array."
                        elif not matrix_valid:
                            err_msg = "Form XObject dictionary contains malformed /Matrix 6-element array."

                        obj_num = og[0] if og else 0
                        form_xobjects.append(FormXObjectModel(
                            id=f"Form_XObject_{og[0]}_{og[1]}" if og else f"Form_XObject_{id(xobj)}",
                            obj_num=obj_num,
                            has_valid_bbox=has_valid_bbox,
                            bbox=parsed_bbox,
                            has_matrix=has_matrix,
                            matrix_valid=matrix_valid,
                            struct_parents=sp_val,
                            is_valid=is_valid,
                            error_message=err_msg
                        ))

                        res = getattr(xobj, "resources", None) or xobj.get("/Resources")
                        if res and "/XObject" in res:
                            try:
                                for _, child_xo in res.XObject.items():
                                    process_form_xobject(child_xo)
                            except Exception:
                                pass

                for p in pike_doc.pages:
                    res = getattr(p, "resources", None) or p.get("/Resources")
                    if res and "/XObject" in res:
                        try:
                            for _, xo in res.XObject.items():
                                process_form_xobject(xo)
                        except Exception:
                            pass
                    if "/Annots" in p:
                        try:
                            for a in p.Annots:
                                if "/AP" in a:
                                    for ap_key in ["/N", "/R", "/D"]:
                                        if ap_key in a.AP:
                                            ap_val = a.AP[ap_key]
                                            if isinstance(ap_val, pikepdf.Dictionary) and not isinstance(ap_val, pikepdf.Stream):
                                                for _, sub_v in ap_val.items():
                                                    process_form_xobject(sub_v)
                                            else:
                                                process_form_xobject(ap_val)
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"Error extracting Form XObjects: {e}")

            return PDFDocumentModel(
                filepath=self.filepath,
                filename=self.filename,
                filesize=self.filesize,
                pdf_version=pdf_version,
                page_count=page_count,
                title=title,
                author=doc_info_author or xmp_dc_creator,
                subject=doc_info_subject or xmp_dc_description,
                keywords=doc_info_keywords,
                creator=creator,
                producer=producer,
                creation_date=creation_date,
                modification_date=mod_date,
                language=language,
                is_tagged=is_tagged,
                is_encrypted=is_encrypted,
                allows_extraction=allows_extraction,
                display_doc_title=display_doc_title,
                has_suspects=has_suspects,
                doc_info_title=doc_info_title,
                doc_info_author=doc_info_author,
                doc_info_subject=doc_info_subject,
                doc_info_keywords=doc_info_keywords,
                xmp_metadata_present=xmp_metadata_present,
                xmp_dc_title=xmp_dc_title,
                xmp_dc_creator=xmp_dc_creator,
                xmp_dc_description=xmp_dc_description,
                pdfua_identifier_present=pdfua_identifier_present,
                pdfua_part=pdfua_part,
                has_parent_tree=has_parent_tree,
                parent_tree_valid=parent_tree_valid,
                parent_tree_entries_count=parent_tree_entries_count,
                parent_tree_map=parent_tree_map,
                role_map=role_map,
                pages=pages,
                structure_tree=structure_tree,
                fonts=fonts,
                images=images,
                tables=tables,
                lists=lists,
                links=links,
                form_fields=form_fields,
                annotations=annotations,
                bookmarks=bookmarks,
                raw_metadata=doc_info,
                embedded_files_count=embedded_files_count,
                form_xobjects=form_xobjects
            )
        finally:
            fitz_doc.close()
            pike_doc.close()

    @staticmethod
    def _parse_tounicode_cmap(stream_bytes: bytes) -> Dict[int, str]:
        cmap: Dict[int, str] = {}
        text = stream_bytes.decode("latin1", errors="ignore")
        for section in re.findall(r'beginbfchar(.*?)endbfchar', text, re.DOTALL):
            for m in re.finditer(r'<([0-9a-fA-F]+)>\s+<([0-9a-fA-F]+)>', section):
                src = int(m.group(1), 16)
                dst_hex = m.group(2)
                try:
                    dst_chars = bytes.fromhex(dst_hex).decode("utf-16-be", errors="ignore")
                    cmap[src] = dst_chars
                except Exception:
                    pass
        for section in re.findall(r'beginbfrange(.*?)endbfrange', text, re.DOTALL):
            for m in re.finditer(r'<([0-9a-fA-F]+)>\s+<([0-9a-fA-F]+)>\s+<([0-9a-fA-F]+)>', section):
                start = int(m.group(1), 16)
                end = int(m.group(2), 16)
                base = int(m.group(3), 16)
                if 0 <= (end - start) <= 512:
                    for offset in range(end - start + 1):
                        curr_src = start + offset
                        curr_dst = base + offset
                        try:
                            dst_bytes = curr_dst.to_bytes((curr_dst.bit_length() + 7) // 8 or 2, 'big')
                            if len(dst_bytes) % 2 != 0:
                                dst_bytes = b'\x00' + dst_bytes
                            cmap[curr_src] = dst_bytes.decode("utf-16-be", errors="ignore")
                        except Exception:
                            pass
        return cmap

    @classmethod
    def _decode_page_mcid_texts(
        cls,
        pike_page: pikepdf.Page,
        font_cmap_cache: Dict[Any, Dict[int, str]]
    ) -> Dict[int, str]:
        page_cmaps: Dict[str, Dict[int, str]] = {}
        font_is_2byte: Dict[str, bool] = {}
        try:
            if "/Resources" in pike_page and "/Font" in pike_page.Resources:
                for f_name, f_obj in pike_page.Resources.Font.items():
                    fn_str = str(f_name).strip("/")
                    obj_id = getattr(f_obj, "objgen", None)
                    if obj_id and obj_id in font_cmap_cache:
                        page_cmaps[fn_str] = font_cmap_cache[obj_id]
                    elif "/ToUnicode" in f_obj:
                        try:
                            cmap = cls._parse_tounicode_cmap(f_obj.ToUnicode.read_bytes())
                            if obj_id:
                                font_cmap_cache[obj_id] = cmap
                            page_cmaps[fn_str] = cmap
                        except Exception:
                            pass

                    subtype = str(f_obj.get("/Subtype", "")).strip("/")
                    font_is_2byte[fn_str] = (subtype == "Type0")

            ops = pikepdf.parse_content_stream(pike_page)
            stack: List[Optional[int]] = []
            current_font = None
            mcid_chars: Dict[int, List[str]] = {}

            for operands, operator in ops:
                op = str(operator)
                if op == "Tf" and operands:
                    current_font = str(operands[0]).strip("/")
                elif op == "BDC":
                    props = operands[1] if len(operands) > 1 else None
                    mcid = None
                    if isinstance(props, pikepdf.Dictionary) and "/MCID" in props:
                        mcid = int(props["/MCID"])
                    stack.append(mcid)
                elif op == "BMC":
                    stack.append(None)
                elif op == "EMC":
                    if stack:
                        stack.pop()
                elif op in ("Tj", "'", "\"", "TJ"):
                    curr_mcid = next((m for m in reversed(stack) if m is not None), None)
                    if curr_mcid is not None:
                        if curr_mcid not in mcid_chars:
                            mcid_chars[curr_mcid] = []
                        cmap = page_cmaps.get(current_font, {})
                        is_2b = font_is_2byte.get(current_font, False)
                        raw_items: List[bytes] = []
                        if op in ("Tj", "'", "\"") and operands and isinstance(operands[0], (pikepdf.String, bytes)):
                            raw_items.append(bytes(operands[0]))
                        elif op == "TJ" and operands and isinstance(operands[0], pikepdf.Array):
                            for item in operands[0]:
                                if isinstance(item, (pikepdf.String, bytes)):
                                    raw_items.append(bytes(item))

                        for b in raw_items:
                            if cmap:
                                if is_2b or (len(b) % 2 == 0 and any(k > 255 for k in cmap.keys())):
                                    for i in range(0, len(b) - 1, 2):
                                        code = int.from_bytes(b[i:i+2], 'big')
                                        mcid_chars[curr_mcid].append(cmap.get(code, chr(code) if code < 256 else ""))
                                else:
                                    for byte_val in b:
                                        mcid_chars[curr_mcid].append(cmap.get(byte_val, chr(byte_val)))
                            else:
                                mcid_chars[curr_mcid].append(b.decode("latin1", errors="ignore"))

            return {mc: "".join(chars) for mc, chars in mcid_chars.items()}
        except Exception as e:
            logger.debug(f"Error decoding page MCID texts: {e}")
            return {}

    def _extract_fonts(self, fitz_doc: pymupdf.Document, pike_doc: pikepdf.Pdf) -> List[FontModel]:
        """Extracts all fonts and verifies embedding and ToUnicode maps."""
        font_dict: Dict[Any, FontModel] = {}

        for page_idx in range(len(fitz_doc)):
            page = fitz_doc[page_idx]
            font_list = page.get_fonts(full=True)
            for f in font_list:
                xref = f[0]
                ext = f[1] if len(f) > 1 else ""
                subtype = f[2] if len(f) > 2 else "Unknown"
                basefont = f[3] if len(f) > 3 else "Unknown"
                encoding = f[5] if len(f) > 5 else "Custom"

                font_key = xref if xref > 0 else basefont

                if font_key in font_dict:
                    if (page_idx + 1) not in font_dict[font_key].pages:
                        font_dict[font_key].pages.append(page_idx + 1)
                    continue

                is_subset = "+" in basefont and len(basefont.split("+")[0]) == 6
                # If PyMuPDF found an embedded font extension (cff, ttf, otf, cid, etc.), it is embedded
                is_embedded = bool(ext and ext.lower() not in ("", "n/a", "none")) or is_subset
                has_tounicode = False
                has_standard_encoding = str(encoding).strip("/") in (
                    "WinAnsiEncoding", "MacRomanEncoding", "StandardEncoding",
                    "PDFDocEncoding"
                )

                font_obj = None
                try:
                    font_obj = pike_doc.get_object((xref, 0))
                except Exception:
                    try:
                        if 0 < xref < len(pike_doc.objects):
                            font_obj = pike_doc.objects[xref]
                    except Exception:
                        pass

                if font_obj is not None:
                    if "/ToUnicode" in font_obj:
                        has_tounicode = True

                    if "/FontDescriptor" in font_obj:
                        fd = font_obj["/FontDescriptor"]
                        if any(k in fd for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                            is_embedded = True

                    if "/DescendantFonts" in font_obj:
                        try:
                            for df in font_obj["/DescendantFonts"]:
                                if "/FontDescriptor" in df:
                                    df_fd = df["/FontDescriptor"]
                                    if any(k in df_fd for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                                        is_embedded = True
                                if "/ToUnicode" in df:
                                    has_tounicode = True
                        except Exception:
                            pass

                    if "/Encoding" in font_obj:
                        try:
                            enc_val = font_obj["/Encoding"]
                            if isinstance(enc_val, pikepdf.Name):
                                enc_str = str(enc_val).strip("/")
                                if enc_str in ("WinAnsiEncoding", "MacRomanEncoding", "StandardEncoding"):
                                    has_standard_encoding = True
                            elif isinstance(enc_val, pikepdf.Dictionary) and "/BaseEncoding" in enc_val:
                                base_enc = str(enc_val["/BaseEncoding"]).strip("/")
                                if base_enc in ("WinAnsiEncoding", "MacRomanEncoding", "StandardEncoding"):
                                    has_standard_encoding = True
                        except Exception:
                            pass

                font_dict[font_key] = FontModel(
                    name=basefont,
                    subtype=subtype,
                    is_embedded=is_embedded,
                    is_subset=is_subset,
                    has_tounicode=has_tounicode,
                    encoding=str(encoding),
                    pages=[page_idx + 1],
                    is_used=True,
                    xref=xref,
                    has_standard_encoding=has_standard_encoding
                )

        # Check usage for non-embedded fonts to prevent false positives from unused resource entries
        page_spans_cache: Dict[int, Set[str]] = {}
        for font in font_dict.values():
            if not font.is_embedded:
                font_is_used = False
                base_clean = font.name.split("+")[-1].lower().replace(" ", "").replace("-", "")
                for p_num in font.pages:
                    p_idx = p_num - 1
                    if p_idx not in page_spans_cache:
                        p_spans: Set[str] = set()
                        try:
                            p_dict = fitz_doc[p_idx].get_text("dict", flags=0)
                            for b in p_dict.get("blocks", []):
                                for l in b.get("lines", []):
                                    for s in l.get("spans", []):
                                        f_name = s.get("font", "")
                                        if f_name:
                                            p_spans.add(f_name)
                                            p_spans.add(f_name.split("+")[-1].lower().replace(" ", "").replace("-", ""))
                        except Exception:
                            pass
                        page_spans_cache[p_idx] = p_spans

                    p_spans = page_spans_cache[p_idx]
                    if font.name in p_spans or base_clean in p_spans or any(base_clean in s for s in p_spans):
                        font_is_used = True
                        break
                font.is_used = font_is_used

        return list(font_dict.values())

    def _extract_images(
        self,
        fitz_doc: pymupdf.Document,
        struct_tree: Optional[StructureNode],
        page_artifact_xobjs: Optional[Dict[int, Set[str]]] = None
    ) -> List[ImageModel]:
        """Extracts images and maps them to Structure /Figure elements or Artifacts."""
        images: List[ImageModel] = []
        page_artifact_xobjs = page_artifact_xobjs or {}

        figures_by_page: Dict[int, List[StructureNode]] = {}
        if struct_tree:
            for fn in struct_tree.find_all_by_standard_tag("Figure"):
                p = fn.page or 0
                figures_by_page.setdefault(p, []).append(fn)

        for page_idx in range(len(fitz_doc)):
            page = fitz_doc[page_idx]
            page_num = page_idx + 1
            p_art_xobjs = page_artifact_xobjs.get(page_num, set())

            # Using page.get_images() is ~40x faster than get_image_info() on large files
            page_imgs = page.get_images()
            page_xref_counts: Dict[int, int] = {}
            for img in page_imgs:
                xref = img[0]
                occ_num = page_xref_counts.get(xref, 0) + 1
                page_xref_counts[xref] = occ_num

                width = img[2] if len(img) > 2 else 0
                height = img[3] if len(img) > 3 else 0
                cs = img[5] if len(img) > 5 else "RGB"
                name = img[7] if len(img) > 7 else ""

                # Check if this image was placed inside an /Artifact marked content sequence
                is_artifact = (name in p_art_xobjs) or str(name).startswith("Fm")

                # Match against Figure structure nodes on this page
                candidate_figs = figures_by_page.get(page_num) or figures_by_page.get(0, [])
                matched_node = candidate_figs[0] if candidate_figs else None

                # If matched to a figure that has alt text, it's not an untagged image
                has_alt = bool(matched_node and (matched_node.alt_text or matched_node.actual_text))
                alt_val = (matched_node.alt_text or matched_node.actual_text or "").strip() if matched_node else ""

                bbox_tuple = (0.0, 0.0, float(width), float(height))
                if matched_node and matched_node.bbox:
                    bbox_tuple = matched_node.bbox
                elif not is_artifact and not has_alt:
                    try:
                        rects = page.get_image_rects(xref)
                        if rects:
                            r_idx = occ_num - 1
                            r = rects[r_idx] if r_idx < len(rects) else rects[0]
                            bbox_tuple = (r.x0, r.y0, r.x1, r.y1)
                    except Exception:
                        pass

                img_id = f"img_p{page_num}_{xref}" if occ_num == 1 else f"img_p{page_num}_{xref}_{occ_num}"
                images.append(ImageModel(
                    id=img_id,
                    page=page_num,
                    bbox=bbox_tuple,
                    width=width,
                    height=height,
                    colorspace=cs,
                    has_alt=has_alt,
                    alt_text=alt_val,
                    is_artifact=is_artifact,
                    structure_element_id=matched_node.id if matched_node else None
                ))

        return images

    def _extract_tables(self, struct_tree: Optional[StructureNode]) -> List[TableModel]:
        """Extracts Table structural nodes and checks header cells."""
        tables: List[TableModel] = []
        if not struct_tree:
            return tables

        table_nodes = struct_tree.find_all_by_standard_tag("Table")
        for idx, t_node in enumerate(table_nodes):
            tr_nodes = t_node.find_all_by_standard_tag("TR")
            th_nodes = t_node.find_all_by_standard_tag("TH")
            td_nodes = t_node.find_all_by_standard_tag("TD")

            rows_count = len(tr_nodes)
            th_count = len(th_nodes)
            td_count = len(td_nodes)
            row_cols = []
            active_rowspans: List[int] = []
            for tr in tr_nodes:
                cells = [c for c in tr.children if (c.standard_tag or "").upper() in ("TH", "TD")]
                carried_over = sum(1 for span in active_rowspans if span > 1)
                active_rowspans = [span - 1 for span in active_rowspans if span > 1]
                total_row_span = carried_over
                for cell in cells:
                    try:
                        c_span = max(1, int(cell.attributes.get("ColSpan", 1)))
                    except Exception:
                        c_span = 1
                    try:
                        r_span = max(1, int(cell.attributes.get("RowSpan", 1)))
                    except Exception:
                        r_span = 1
                    total_row_span += c_span
                    if r_span > 1:
                        active_rowspans.extend([r_span] * c_span)
                row_cols.append(total_row_span)

            cols_count = max(row_cols) if row_cols else 0
            is_regular = (len(set(row_cols)) <= 1) if row_cols else True

            page_val = t_node.page
            if page_val is None and t_node.pages_spanned:
                page_val = t_node.pages_spanned[0]
            if page_val is None:
                page_val = 1

            tables.append(TableModel(
                id=f"table_{idx + 1}",
                page=page_val,
                rows_count=rows_count,
                cols_count=cols_count,
                has_headers=th_count > 0,
                header_cells_count=th_count,
                data_cells_count=td_count,
                summary=t_node.title,
                is_regular=is_regular,
                bbox=t_node.bbox
            ))

        return tables

    def _extract_lists(self, struct_tree: Optional[StructureNode]) -> List[ListModel]:
        """Extracts List (<L>) structural nodes and checks LI / Lbl / LBody nesting."""
        lists: List[ListModel] = []
        if not struct_tree:
            return lists

        list_nodes = struct_tree.find_all_by_standard_tag("L")
        for idx, l_node in enumerate(list_nodes):
            li_nodes = [c for c in l_node.children if c.standard_tag.upper() == "LI"]
            has_labels = False
            # Check Matterhorn Checkpoint 28-001: All direct children of L must be LI or Caption
            is_valid_l = len(l_node.children) > 0 and all(c.standard_tag.upper() in ("LI", "CAPTION") for c in l_node.children)

            # Check Matterhorn Checkpoint 28-002: All direct children of LI must be Lbl and/or LBody
            is_valid_li = True
            for li in li_nodes:
                child_tags = [c.standard_tag.upper() for c in li.children]
                if "LBL" in child_tags:
                    has_labels = True
                if not (len(li.children) > 0 and all(t in ("LBL", "LBODY", "CAPTION") for t in child_tags)):
                    is_valid_li = False

            is_valid = is_valid_l and is_valid_li

            page_val = l_node.page
            if page_val is None and l_node.pages_spanned:
                page_val = l_node.pages_spanned[0]
            if page_val is None:
                page_val = 1

            lists.append(ListModel(
                id=f"list_{idx + 1}",
                page=page_val,
                items_count=len(li_nodes),
                is_valid_structure=is_valid,
                has_labels=has_labels,
                bbox=l_node.bbox
            ))

        return lists

    def _extract_links(self, fitz_doc: pymupdf.Document, struct_tree: Optional[StructureNode]) -> List[LinkModel]:
        """Extracts links from page annotations and associates them with Link structure elements."""
        links: List[LinkModel] = []
        link_nodes: List[StructureNode] = []
        if struct_tree:
            link_nodes = struct_tree.find_all_by_standard_tag("Link")

        for page_idx in range(len(fitz_doc)):
            page = fitz_doc[page_idx]
            page_num = page_idx + 1
            for l in page.get_links():
                rect = l.get("from", (0, 0, 0, 0))
                uri = l.get("uri", "")
                page_dest = l.get("page", None)
                if page_dest is not None:
                    page_dest += 1

                link_text = page.get_text("text", clip=rect).strip()
                if not link_text and uri:
                    link_text = uri

                matched_node = next((ln for ln in link_nodes if ln.page == page_num), None)

                links.append(LinkModel(
                    id=f"link_p{page_num}_{len(links) + 1}",
                    page=page_num,
                    text=link_text,
                    uri=uri or (f"Page {page_dest}" if page_dest else "Internal"),
                    is_internal=bool(page_dest),
                    destination_page=page_dest,
                    alt_text=matched_node.alt_text if matched_node else None,
                    has_structure_link=matched_node is not None,
                    bbox=(rect.x0, rect.y0, rect.x1, rect.y1) if hasattr(rect, "x0") else tuple(rect)
                ))

        return links

    def _extract_form_fields(self, fitz_doc: pymupdf.Document, pike_doc: pikepdf.Pdf) -> List[FormFieldModel]:
        """Extracts interactive form fields and checks accessible tooltips /TU, including inherited attributes."""
        fields: List[FormFieldModel] = []
        for page_idx in range(len(fitz_doc)):
            page = fitz_doc[page_idx]
            page_num = page_idx + 1
            widgets = page.widgets()
            if widgets:
                for w in widgets:
                    name = w.field_name or "UnnamedField"
                    ftype = w.field_type_string or "Widget"
                    tooltip = None
                    rect = (w.rect.x0, w.rect.y0, w.rect.x1, w.rect.y1) if w.rect else None

                    try:
                        if w.xref and w.xref in pike_doc.objects:
                            annot_obj = pike_doc.objects[w.xref]
                            if "/TU" in annot_obj:
                                tooltip = str(annot_obj["/TU"]).strip()
                            elif "/Parent" in annot_obj:
                                curr = annot_obj["/Parent"]
                                while curr is not None:
                                    if "/TU" in curr:
                                        tooltip = str(curr["/TU"]).strip()
                                        break
                                    curr = curr.get("/Parent", None)
                    except Exception:
                        pass

                    fields.append(FormFieldModel(
                        name=name,
                        field_type=ftype,
                        tooltip=tooltip,
                        label=w.field_label or name,
                        page=page_num,
                        is_required=False,
                        bbox=rect
                    ))

        return fields

    def _extract_annotations(
        self,
        fitz_doc: pymupdf.Document,
        pike_doc: pikepdf.Pdf,
        struct_tree: Optional[StructureNode]
    ) -> List[AnnotationModel]:
        """Extracts all page annotations and checks if they are linked to the structure tree."""
        annots: List[AnnotationModel] = []
        has_link_nodes = bool(struct_tree.find_all_by_standard_tag("Link")) if struct_tree else False
        has_form_nodes = bool(struct_tree.find_all_by_standard_tag("Form")) if struct_tree else False

        for page_idx in range(len(fitz_doc)):
            page = fitz_doc[page_idx]
            page_num = page_idx + 1

            for a in page.annots():
                subtype = a.type[1] if isinstance(a.type, tuple) and len(a.type) > 1 else "Unknown"
                rect = (a.rect.x0, a.rect.y0, a.rect.x1, a.rect.y1)
                struct_parent = None
                is_tagged = False

                # Query pikepdf annotation object
                try:
                    if a.xref and a.xref in pike_doc.objects:
                        annot_obj = pike_doc.objects[a.xref]
                        if "/StructParent" in annot_obj:
                            struct_parent = int(annot_obj["/StructParent"])
                            is_tagged = True
                except Exception:
                    pass

                # If subtype is Link or Widget and struct_tree has link/form
                if not is_tagged:
                    if subtype == "Link" and has_link_nodes:
                        is_tagged = True
                    elif subtype == "Widget" and has_form_nodes:
                        is_tagged = True

                annots.append(AnnotationModel(
                    id=f"annot_p{page_num}_{a.xref}",
                    page=page_num,
                    subtype=subtype,
                    rect=rect,
                    struct_parent=struct_parent,
                    is_tagged=is_tagged,
                    contents=a.info.get("content", "")
                ))

        return annots

    def _extract_bookmarks(self, fitz_doc: pymupdf.Document) -> List[BookmarkModel]:
        """Extracts document table of contents / bookmarks hierarchy."""
        toc = fitz_doc.get_toc()
        bookmarks: List[BookmarkModel] = []
        stack: List[Tuple[int, BookmarkModel]] = []

        for item in toc:
            lvl = item[0]
            title = item[1]
            page = item[2]
            bm = BookmarkModel(title=title, level=lvl, page=page)

            while stack and stack[-1][0] >= lvl:
                stack.pop()

            if stack:
                stack[-1][1].children.append(bm)
            else:
                bookmarks.append(bm)

            stack.append((lvl, bm))

        return bookmarks
