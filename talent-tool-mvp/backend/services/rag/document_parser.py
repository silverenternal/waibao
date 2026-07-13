"""Document parser — vendor-in LlamaIndex readers.

We support PDF, Word, Markdown, HTML, and plain text.  The heavy lifting is
done by `llama_index` readers, but we keep the surface small and provide a
hand-rolled fallback so that the parser remains functional in environments
where the optional readers are not installed.
"""
from __future__ import annotations

import mimetypes
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParsedDocument:
    """Result of parsing one uploaded file."""

    document_id: uuid.UUID = field(default_factory=uuid.uuid4)
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    pages: int = 0
    language: str | None = None
    parser_used: str = "unknown"

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def char_count(self) -> int:
        return len(self.text)


# ----------------------------------------------------------------------
# LlamaIndex bridge
# ----------------------------------------------------------------------

def _try_llama_index_reader(path: str, mime_type: str | None) -> tuple[str, str] | None:
    """Return (text, parser_used) using LlamaIndex readers, or None if unsupported.

    Importing LlamaIndex readers lazily so that the test suite does not require
    the optional dependencies (pypdf, docx2txt, bs4) to be installed.
    """
    ext = Path(path).suffix.lower()
    name = os.path.basename(path)

    # PDF
    if ext == ".pdf" or (mime_type or "").endswith("pdf"):
        try:
            from llama_index.readers.file import PDFReader  # type: ignore
        except Exception:  # noqa: BLE001
            return None
        reader = PDFReader()
        docs = reader.load_data(file=Path(path))
        text = "\n\n".join(d.get_content() for d in docs)
        return text, "llama_index.PDFReader"

    # Word
    if ext in {".docx", ".doc"} or "wordprocessing" in (mime_type or ""):
        try:
            from llama_index.readers.file import DocxReader  # type: ignore
        except Exception:  # noqa: BLE001
            return None
        reader = DocxReader()
        docs = reader.load_data(file=Path(path))
        text = "\n\n".join(d.get_content() for d in docs)
        return text, "llama_index.DocxReader"

    # Markdown
    if ext in {".md", ".markdown"}:
        try:
            from llama_index.readers.file import MarkdownReader  # type: ignore
        except Exception:  # noqa: BLE001
            return None
        reader = MarkdownReader()
        docs = reader.load_data(file=Path(path))
        text = "\n\n".join(d.get_content() for d in docs)
        return text, "llama_index.MarkdownReader"

    # HTML
    if ext in {".html", ".htm"}:
        try:
            from llama_index.readers.file import HTMLReader  # type: ignore
        except Exception:  # noqa: BLE001
            return None
        reader = HTMLReader()
        docs = reader.load_data(file=Path(path))
        text = "\n\n".join(d.get_content() for d in docs)
        return text, "llama_index.HTMLReader"

    # Plain text — fall through to fallback
    return None


# ----------------------------------------------------------------------
# Hand-rolled fallbacks
# ----------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def _read_pdf_fallback(path: str) -> str:
    """Very small PDF fallback that handles the most trivial single-page case.

    Production deployments should rely on the LlamaIndex PDFReader (which uses
    pypdf under the hood).  This is here so the parser returns *something*
    when pypdf is missing rather than raising an opaque error.
    """
    raw = Path(path).read_bytes()
    chunks: list[str] = []
    for match in re.finditer(rb"\((.*?)\)\s*Tj", raw, flags=re.DOTALL):
        try:
            text = match.group(1).decode("latin-1", errors="ignore")
            text = text.replace("\\(", "(").replace("\\)", ")")
            if text.strip():
                chunks.append(text)
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(chunks) if chunks else ""


def _read_docx_fallback(path: str) -> str:
    """Minimal docx fallback — strips XML, returns text."""
    raw = Path(path).read_bytes()
    # very rough: extract <w:t>...</w:t> bodies
    parts = re.findall(rb"<w:t[^>]*>(.*?)</w:t>", raw, flags=re.DOTALL)
    return "\n".join(p.decode("utf-8", errors="ignore") for p in parts)


def _strip_html(html: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", html)).strip()


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

class DocumentParser:
    """Parse a file into a `ParsedDocument`.

    Examples:
        parser = DocumentParser()
        doc = parser.parse("/tmp/handbook.pdf", "application/pdf")
        chunks = Chunker().split([doc])
    """

    SUPPORTED_MIME_PREFIXES = (
        "application/pdf",
        "application/vnd.openxmlformats-officedocument",
        "application/msword",
        "text/",
    )

    def __init__(self, *, default_language: str = "en") -> None:
        self.default_language = default_language

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------
    def detect_mime(self, path: str) -> str:
        mime, _ = mimetypes.guess_type(path)
        return mime or "application/octet-stream"

    def supports(self, path: str, mime_type: str | None = None) -> bool:
        mime = mime_type or self.detect_mime(path)
        return any(mime.startswith(prefix) for prefix in self.SUPPORTED_MIME_PREFIXES)

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------
    def parse(self, path: str, mime_type: str | None = None) -> ParsedDocument:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Document not found: {path}")
        mime = mime_type or self.detect_mime(path)
        ext = Path(path).suffix.lower()

        parser_used = "unknown"
        text = ""

        # 1) LlamaIndex (preferred)
        result = _try_llama_index_reader(path, mime)
        if result is not None:
            text, parser_used = result

        # 2) Fallback
        if not text:
            if ext == ".pdf":
                text = _read_pdf_fallback(path)
                parser_used = "fallback.pdf"
            elif ext in {".docx", ".doc"}:
                text = _read_docx_fallback(path)
                parser_used = "fallback.docx"
            elif ext in {".html", ".htm"}:
                text = _strip_html(_read_text(path))
                parser_used = "fallback.html"
            else:
                text = _read_text(path)
                parser_used = "fallback.text"

        if not text.strip():
            raise ValueError(f"Parser produced empty content for {path}")

        # Crude page detection: 1 page per ~3k chars, minimum 1
        pages = max(1, len(text) // 3000)

        # Heuristic language detection — fine for tests
        language = self.default_language
        if re.search(r"[一-鿿]", text):
            language = "zh"
        elif re.search(r"[぀-ヿ]", text):
            language = "ja"

        return ParsedDocument(
            text=text,
            metadata={
                "path": path,
                "mime_type": mime,
                "extension": ext,
                "filename": os.path.basename(path),
            },
            pages=pages,
            language=language,
            parser_used=parser_used,
        )

    def parse_text(self, text: str, *, source: str = "raw") -> ParsedDocument:
        """Parse an in-memory string — useful for tests and URL ingestion."""
        if not text or not text.strip():
            raise ValueError("Cannot parse empty text")
        language = self.default_language
        if re.search(r"[一-鿿]", text):
            language = "zh"
        return ParsedDocument(
            text=text,
            metadata={"source": source, "mime_type": "text/plain"},
            pages=max(1, len(text) // 3000),
            language=language,
            parser_used="raw",
        )
