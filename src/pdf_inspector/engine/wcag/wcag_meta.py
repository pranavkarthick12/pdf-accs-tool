"""
WCAG 2.1 and 2.2 Standards Metadata and Guidance
Provides authoritative mapping for WCAG Principles (POUR), Success Criteria,
conformance levels (Level A / AA), technical summaries, and remediation advice.
"""

from typing import Dict, Any

WCAG_GUIDELINE_META: Dict[str, Dict[str, Any]] = {
    "1.1 Text Alternatives": {
        "principle": "1. Perceivable",
        "criteria": "SC 1.1.1 Non-text Content (Level A)",
        "level": "Level A",
        "summary": "All non-text content (images, charts, diagrams, formulas, form fields) presented to users must have a text alternative serving equivalent purpose.",
        "remediation": "Provide concise alternative text (/Alt or /ActualText) on all <Figure> and <Formula> tags, tooltip (/TU) on form fields, and mark decorative graphics as /Artifact.",
        "not_applicable_guidance": "No figures, formulas, raster images, or interactive form fields are present in this document."
    },
    "1.2 Time-based Media": {
        "principle": "1. Perceivable",
        "criteria": "SC 1.2.1 Audio/Video-only (A), SC 1.2.2 Captions (A), SC 1.2.3 Audio Description (A), SC 1.2.5 Audio Description (AA)",
        "level": "Level A / AA",
        "summary": "Provide synchronized captions, text transcripts, or audio descriptions for time-based media embedded in the document.",
        "remediation": "If multimedia is embedded, provide synchronized closed captions (CC), full text transcripts, and audio descriptions during pauses in dialogue.",
        "not_applicable_guidance": "No embedded audio or video streams are present in this document. Automated PDF tools (PAC) report '-' (⊘); human review applies if multimedia is added."
    },
    "1.3 Adaptable": {
        "principle": "1. Perceivable",
        "criteria": "SC 1.3.1 Info and Relationships (Level A), SC 1.3.2 Meaningful Sequence (Level A)",
        "level": "Level A",
        "summary": "Information, structure, and relationships conveyed visually must be programmatically determined through semantic tags (<H1>-<H6>, <L>/<LI>, <Table>/<TH>, BBox, embedded fonts).",
        "remediation": "Tag heading hierarchy sequentially without skipping levels, assign table headers (<TH>) with Scope, ensure list items contain <Lbl> and <LBody>, embed all fonts, and ensure all figures have valid BBox attributes.",
        "not_applicable_guidance": "Document contains no applicable structural content elements."
    },
    "1.4 Distinguishable": {
        "principle": "1. Perceivable",
        "criteria": "SC 1.4.1 Use of Color (Level A), SC 1.4.2 Audio Control (Level A), SC 1.4.3 Contrast (Minimum) (Level AA), SC 1.4.4 Resize Text (Level AA), SC 1.4.5 Images of Text (Level AA), SC 1.4.10 Reflow (Level AA), SC 1.4.11 Non-text Contrast (Level AA), SC 1.4.12 Text Spacing (Level AA), SC 1.4.13 Content on Hover or Focus (Level AA)",
        "level": "Level A / AA",
        "summary": "Make it easier for users to see and hear content by separating foreground from background. Evaluates text visual contrast (SC 1.4.3), non-text control boundaries (SC 1.4.11), color-only dependency for links and controls (SC 1.4.1), and avoiding images of text (SC 1.4.5).",
        "remediation": "Ensure standard text meets at least 4.5:1 contrast (3:1 for large text ≥18pt or ≥14pt bold), interactive form field boundaries achieve at least 3:1 contrast against adjacent background, links within body text provide visual cues (underline or distinct font styling) in addition to color, and raster images of text are replaced with real text.",
        "not_applicable_guidance": "No text, link, form control, or image elements requiring visual distinction or contrast evaluation are present in this document. Non-machine-testable criteria (audio control, text resize, reflow) report '-' as they require manual assistive inspection."
    },
    "2.1 Keyboard Accessible": {
        "principle": "2. Operable",
        "criteria": "SC 2.1.1 Keyboard (Level A), SC 2.1.2 No Keyboard Trap (Level A)",
        "level": "Level A",
        "summary": "All functionality must be operable through a keyboard interface without requiring specific timings and without trapping keyboard focus.",
        "remediation": "Ensure all interactive form fields, links, and annotations can receive and relinquish keyboard focus seamlessly, matching the logical tag reading order.",
        "not_applicable_guidance": "Keyboard navigation in PDF documents relies on logical focus order (SC 2.4.3 /Tabs /S). Pure interactive keyboard operability is validated through assistive technology and human inspection."
    },
    "2.2 Enough Time": {
        "principle": "2. Operable",
        "criteria": "SC 2.2.1 Timing Adjustable (Level A), SC 2.2.2 Pause, Stop, Hide (Level A)",
        "level": "Level A",
        "summary": "Provide users enough time to read and use content, allowing adjustments or extensions on timed interactions or moving/auto-updating content.",
        "remediation": "Avoid automatic timeouts, self-advancing carousels, or timed scripts in document workflows.",
        "not_applicable_guidance": "PDF documents do not feature auto-expiring sessions or timed presentations. PAC reports '-' (⊘) as no timed interactions apply."
    },
    "2.3 Seizures and Physical Reactions": {
        "principle": "2. Operable",
        "criteria": "SC 2.3.1 Three Flashes or Below Threshold (Level A)",
        "level": "Level A",
        "summary": "Do not design content in a way that is known to cause seizures (no elements flashing more than 3 times per second).",
        "remediation": "Ensure no embedded animated content, media, or scripts flash more than three times per second.",
        "not_applicable_guidance": "No animated or flashing multimedia elements are embedded in this PDF."
    },
    "2.4 Navigable": {
        "principle": "2. Operable",
        "criteria": "SC 2.4.1 Bypass Blocks (Level A), SC 2.4.2 Page Titled (Level A), SC 2.4.3 Focus Order (Level A), SC 2.4.4 Link Purpose (Level A)",
        "level": "Level A",
        "summary": "Provide ways to help users navigate, find content, and determine where they are (document title in XMP and window title, logical tab order, bookmarks).",
        "remediation": "Set Document Title in XMP metadata, enable 'Display Document Title' in Initial View properties, set Page Tab Order to Document Structure (/Tabs /S) for pages with annotations, and provide descriptive link names.",
        "not_applicable_guidance": "No navigational elements or document catalog properties require evaluation."
    },
    "2.5 Input Modalities": {
        "principle": "2. Operable",
        "criteria": "SC 2.5.3 Label in Name (Level A - 2.1), SC 2.5.8 Target Size (Minimum) (Level AA - WCAG 2.2)",
        "level": "Level A / AA",
        "summary": "Make it easier for users to operate functionality through various inputs beyond keyboard (minimum 24x24px target size, visible text included in accessible name).",
        "remediation": "Ensure visible labels match accessible names (/TU), and interactive buttons/form fields have target sizes of at least 24x24 CSS pixels.",
        "not_applicable_guidance": "PAC 2026 reports '-' (⊘) as target sizing and pointer modalities in PDFs are verified during layout authoring and visual inspection."
    },
    "3.1 Readable": {
        "principle": "3. Understandable",
        "criteria": "SC 3.1.1 Language of Page (Level A), SC 3.1.2 Language of Parts (Level AA)",
        "level": "Level A / AA",
        "summary": "Make text content readable and understandable by declaring the default document natural language and marking language switches on foreign words.",
        "remediation": "Define default document language (e.g. 'en-US') in Document Properties, and specify /Lang on structure tags containing secondary languages.",
        "not_applicable_guidance": "No readable text content elements are present in this document."
    },
    "3.2 Predictable": {
        "principle": "3. Understandable",
        "criteria": "SC 3.2.1 On Focus (Level A), SC 3.2.2 On Input (Level A), SC 3.2.6 Consistent Help (Level A - WCAG 2.2)",
        "level": "Level A",
        "summary": "Make pages appear and operate in predictable ways without unexpected context shifts when controls receive focus or input.",
        "remediation": "Avoid automatic submit actions or window navigation on focus/change events in interactive form scripts.",
        "not_applicable_guidance": "Evaluating that form focus or input does not cause an unexpected change of context requires human functional testing; automated check reports '-' (⊘)."
    },
    "3.3 Input Assistance": {
        "principle": "3. Understandable",
        "criteria": "SC 3.3.1 Error Identification (Level A), SC 3.3.2 Labels or Instructions (Level A), SC 3.3.3 Error Suggestion (Level AA)",
        "level": "Level A / AA",
        "summary": "Help users avoid and correct mistakes by providing clear labels, instructions, error identification, and error suggestions.",
        "remediation": "Provide clear visible instructions and labels for required inputs, and ensure validation scripts identify and describe errors in text.",
        "not_applicable_guidance": "In PAC 2026, form field accessible names (/TU) are verified under 1.1 Text Alternatives (FormFieldHasTUKey). Dynamic error handling requires human functional testing."
    },
    "4.1 Compatible": {
        "principle": "4. Robust",
        "criteria": "SC 4.1.1 Parsing (Level A), SC 4.1.2 Name, Role, Value (Level A)",
        "level": "Level A",
        "summary": "Maximize compatibility with assistive technologies through valid structural hierarchy, standard roles, and circular-free role mapping.",
        "remediation": "Map all custom structure types to standard ISO 32000-1 types in the Role Map, resolve circular mappings, and ensure interactive annotations have parent structure tags.",
        "not_applicable_guidance": "No structure elements or interactive controls are present in this document."
    },
}
