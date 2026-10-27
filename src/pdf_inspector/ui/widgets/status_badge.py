"""
Status Badge Widget
Draws pill badges for CheckStatus (PASS, FAIL, WARN, MANUAL) and Severity levels.
"""

from typing import Dict, Any, Union
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from ...core.models import CheckStatus, Severity


class StatusColors:
    """Centralized visual styling system for CheckStatus, Severity, and inspection states."""

    STATUS_MAP: Dict[Any, Dict[str, str]] = {
        CheckStatus.PASS: {
            "bg": "#dcfce7",
            "fg": "#15803d",
            "border": "#86efac",
            "icon": "✅",
            "label": "PASS",
        },
        CheckStatus.FAIL: {
            "bg": "#fee2e2",
            "fg": "#b91c1c",
            "border": "#fca5a5",
            "icon": "❌",
            "label": "FAIL",
        },
        CheckStatus.WARNING: {
            "bg": "#fef3c7",
            "fg": "#b45309",
            "border": "#fcd34d",
            "icon": "⚠️",
            "label": "WARNING",
        },
        CheckStatus.MANUAL_REVIEW: {
            "bg": "#e0f2fe",
            "fg": "#0369a1",
            "border": "#7dd3fc",
            "icon": "🔍",
            "label": "MANUAL",
        },
        CheckStatus.ERROR: {
            "bg": "#f3e8ff",
            "fg": "#7e22ce",
            "border": "#d8b4fe",
            "icon": "⛔",
            "label": "ERROR",
        },
        CheckStatus.NOT_APPLICABLE: {
            "bg": "#f1f5f9",
            "fg": "#64748b",
            "border": "#cbd5e1",
            "icon": "⊘",
            "label": "N/A",
        },
    }

    SEVERITY_MAP: Dict[Any, Dict[str, str]] = {
        Severity.CRITICAL: {
            "bg": "#ffe4e6",
            "fg": "#9f1239",
            "border": "#fda4af",
            "label": "CRITICAL",
        },
        Severity.HIGH: {
            "bg": "#fee2e2",
            "fg": "#b91c1c",
            "border": "#fca5a5",
            "label": "HIGH",
        },
        Severity.MEDIUM: {
            "bg": "#ffedd5",
            "fg": "#c2410c",
            "border": "#fdba74",
            "label": "MEDIUM",
        },
        Severity.LOW: {
            "bg": "#fef9c3",
            "fg": "#a16207",
            "border": "#fde047",
            "label": "LOW",
        },
        Severity.INFO: {
            "bg": "#f0fdf4",
            "fg": "#15803d",
            "border": "#bbf7d0",
            "label": "INFO",
        },
    }

    _DEFAULT_STATUS = {
        "bg": "#f1f5f9",
        "fg": "#64748b",
        "border": "#cbd5e1",
        "icon": "•",
        "label": "UNKNOWN",
    }

    _DEFAULT_SEVERITY = {
        "bg": "#f1f5f9",
        "fg": "#64748b",
        "border": "#cbd5e1",
        "label": "INFO",
    }

    @classmethod
    def get_status_style(cls, status: Any) -> Dict[str, str]:
        """Resolves style dictionary for any CheckStatus instance, value, or string."""
        if status in cls.STATUS_MAP:
            return cls.STATUS_MAP[status]
        # Resolve by value string if passed as string or enum
        val = getattr(status, "value", str(status)).upper().strip()
        for s_enum, s_style in cls.STATUS_MAP.items():
            if s_enum.value.upper() == val or s_enum.name.upper() == val:
                return s_style
        if val in ("WARN", "WARNING"):
            return cls.STATUS_MAP[CheckStatus.WARNING]
        if val in ("MANUAL", "MANUAL_REVIEW"):
            return cls.STATUS_MAP[CheckStatus.MANUAL_REVIEW]
        if val in ("N/A", "NA", "NOT_APPLICABLE"):
            return cls.STATUS_MAP[CheckStatus.NOT_APPLICABLE]
        return cls._DEFAULT_STATUS

    @classmethod
    def get_severity_style(cls, severity: Any) -> Dict[str, str]:
        """Resolves style dictionary for any Severity instance, value, or string."""
        if severity in cls.SEVERITY_MAP:
            return cls.SEVERITY_MAP[severity]
        val = getattr(severity, "value", str(severity)).upper().strip()
        for s_enum, s_style in cls.SEVERITY_MAP.items():
            if s_enum.value.upper() == val or s_enum.name.upper() == val:
                return s_style
        if val in ("INFORMATIONAL", "INFO"):
            return cls.SEVERITY_MAP[Severity.INFO]
        return cls._DEFAULT_SEVERITY

    @classmethod
    def get_status_color(cls, status: Any) -> QColor:
        """Returns the high-contrast foreground QColor for a status."""
        return QColor(cls.get_status_style(status)["fg"])

    @classmethod
    def get_severity_color(cls, severity: Any) -> QColor:
        """Returns the high-contrast foreground QColor for a severity."""
        return QColor(cls.get_severity_style(severity)["fg"])

    @classmethod
    def get_status_css(
        cls,
        status: Any,
        border_radius: int = 6,
        padding: str = "3px 8px",
        font_size: int = 11,
        font_weight: int = 700,
    ) -> str:
        """Returns complete stylesheet block for a status pill badge."""
        st = cls.get_status_style(status)
        return (
            f"background-color: {st['bg']}; "
            f"color: {st['fg']}; "
            f"border: 1px solid {st['border']}; "
            f"border-radius: {border_radius}px; "
            f"padding: {padding}; "
            f"font-weight: {font_weight}; "
            f"font-size: {font_size}px;"
        )

    @classmethod
    def get_severity_css(
        cls,
        severity: Any,
        border_radius: int = 6,
        padding: str = "3px 8px",
        font_size: int = 10,
        font_weight: int = 600,
    ) -> str:
        """Returns complete stylesheet block for a severity pill badge."""
        st = cls.get_severity_style(severity)
        return (
            f"background-color: {st['bg']}; "
            f"color: {st['fg']}; "
            f"border: 1px solid {st['border']}; "
            f"border-radius: {border_radius}px; "
            f"padding: {padding}; "
            f"font-weight: {font_weight}; "
            f"font-size: {font_size}px;"
        )


class StatusBadge(QLabel):
    """Pill badge showing standardized colored status."""

    def __init__(self, status: CheckStatus, parent=None):
        super().__init__(parent)
        self.setStatus(status)

    def setStatus(self, status: CheckStatus):
        display_val = getattr(status, "value", str(status))
        self.setText(f" {display_val} ")
        self.setAlignment(Qt.AlignCenter)
        css = StatusColors.get_status_css(status, border_radius=6, padding="3px 8px", font_size=11, font_weight=700)
        self.setStyleSheet(f"QLabel {{ {css} }}")


class SeverityBadge(QLabel):
    """Pill badge showing standardized severity level."""

    def __init__(self, severity: Severity, parent=None):
        super().__init__(parent)
        self.setSeverity(severity)

    def setSeverity(self, severity: Severity):
        display_val = getattr(severity, "value", str(severity))
        self.setText(f" {display_val} ")
        self.setAlignment(Qt.AlignCenter)
        css = StatusColors.get_severity_css(severity, border_radius=6, padding="3px 8px", font_size=10, font_weight=600)
        self.setStyleSheet(f"QLabel {{ {css} }}")

