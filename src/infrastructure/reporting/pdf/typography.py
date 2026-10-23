"""Share Unicode typography between actual PDF report renderers."""

from pathlib import Path

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

_FONT_NAME: str = "ASDReportSans"
_FONT_PATHS: tuple[Path, ...] = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/local/share/fonts/DejaVuSans.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
)
_PAGE_WIDTH: float = A4[0]


class UnicodeFontUnavailableError(FileNotFoundError):
    """No suitable local Unicode font is available for embedding."""


class UnicodeReportFont:
    """Resolve and register a local embeddable font without network access."""

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path | None = path

    def register(self) -> str:
        """Return a registered font name or a specific availability error."""
        candidates: tuple[Path, ...] = (
            (self._path,) if self._path is not None else _FONT_PATHS
        )
        font_path: Path | None = next(
            (path for path in candidates if path.is_file()), None
        )
        if font_path is None:
            message: str = "A local Unicode TrueType font is required for PDF output"
            raise UnicodeFontUnavailableError(message)
        if _FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(_FONT_NAME, str(font_path)))
        return _FONT_NAME


def build_report_styles(font: str) -> dict[str, ParagraphStyle]:
    """Define a small report-specific typographic scale."""
    base: ParagraphStyle = ParagraphStyle(
        "ASDBody",
        fontName=font,
        fontSize=9,
        leading=14,
        spaceAfter=6,
        splitLongWords=1,
        wordWrap="CJK",
    )
    return {
        "body": base,
        "title": ParagraphStyle(
            "ASDTitle",
            parent=base,
            fontSize=16,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=7,
        ),
        "heading": ParagraphStyle(
            "ASDHeading", parent=base, fontSize=12, leading=17, spaceBefore=8
        ),
        "finding": ParagraphStyle(
            "ASDFinding", parent=base, fontSize=10, leading=15, spaceBefore=7
        ),
        "note": ParagraphStyle("ASDNote", parent=base, fontSize=7, leading=10),
        "cell": ParagraphStyle(
            "ASDCell", parent=base, fontSize=7, leading=10, spaceAfter=0
        ),
        "table_header": ParagraphStyle(
            "ASDTableHead", parent=base, fontSize=7, leading=10, spaceAfter=0
        ),
        "path_node": ParagraphStyle(
            "ASDPathNode",
            parent=base,
            fontSize=8,
            leading=11,
            alignment=TA_CENTER,
            spaceAfter=1,
        ),
        "path_meta": ParagraphStyle(
            "ASDPathMeta",
            parent=base,
            fontSize=7,
            leading=9,
            alignment=TA_CENTER,
            spaceAfter=0,
        ),
    }


def draw_report_footer(canvas: Canvas, font: str) -> None:
    """Render deterministic page numbering below the document content."""
    canvas.saveState()
    canvas.setFont(font, 8)
    canvas.drawRightString(
        _PAGE_WIDTH - 18 * mm,
        12 * mm,
        f"AutoSystemDesign | страница {canvas.getPageNumber()}",
    )
    canvas.restoreState()
