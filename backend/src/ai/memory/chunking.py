"""memory/chunking.py — structure-aware chunking (RETR T2).

The shipped ingest split documents every 500 characters with `text[i:i+500]`.
That is the worst possible boundary: it cuts mid-sentence and often mid-word, so
a chunk routinely begins with half a clause whose subject is in the previous
chunk. Two things follow, and both hurt retrieval more than the chunk size does:

* **An embedding of a fragment is an embedding of nothing in particular.** The
  vector for "…and the payment terms are net-30 unless the" points nowhere
  useful.
* **Context evaporates at the boundary.** A chunk reading "Net-30 applies." is
  useless without knowing it sat under *"§4 Payment Terms — Enterprise"*.

Technical §24.4 asks for 1–2k chunks split on document structure, carrying
heading context, tunable per source type. This module is that chunker, and it is
pure: text in, chunks out, no I/O — so the boundary rules are directly testable
rather than only observable through retrieval quality.

**Heading context is prepended to the chunk body**, not merely stored beside it.
Both the embedding and the lexical index read `content`, so a heading that lives
only in a metadata column would be invisible to exactly the two retrievers it
needs to inform.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence

__all__ = [
    "CURRENT_CHUNK_VERSION",
    "ChunkProfile",
    "PROFILES",
    "Chunk",
    "profile_for",
    "chunk_document",
]

# Bumped whenever the chunking rules change materially. Documents carry the
# version they were ingested under, so the lazy background re-chunk (decision 1)
# can find stale ones without a big-bang migration.
CURRENT_CHUNK_VERSION = 2

# Markdown ATX headings: "## Payment Terms"
_ATX = re.compile(r"^(#{1,6})\s+(.{1,200})$")
# Numbered section headings: "4. Payment Terms", "4.1.2 Late Fees"
_NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(\S.{0,150})$")
# Setext underlines: a line of === or --- beneath its title
_SETEXT = re.compile(r"^(=|-){3,}\s*$")
# A short, title-cased or upper-case line standing alone reads as a heading in
# PDF/DOCX extractions, which carry no markup at all.
_BARE_TITLE = re.compile(r"^[A-Z][^.!?]{2,80}$")

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
# Leading section numbering on a title — "## 4.1 Late Fees" and "4.1 Late Fees"
# should yield the same label, since the label is what gets embedded.
_LEADING_NUMBER = re.compile(r"^\d+(?:\.\d+)*\.?\s+")


def _clean_title(text: str) -> str:
    return _LEADING_NUMBER.sub("", text.strip()).strip()


@dataclass(frozen=True)
class ChunkProfile:
    """Per-source-type sizing. Extraction quality differs, so boundaries should.

    ``target`` is where a chunk prefers to end; ``maximum`` is the hard cap that
    forces a split even mid-paragraph; ``minimum`` is the size below which a
    trailing chunk is merged back rather than left as a stub.
    """

    target: int = 1200
    maximum: int = 2000
    minimum: int = 200
    detect_bare_titles: bool = False


PROFILES: dict[str, ChunkProfile] = {
    # Markdown's structure is explicit and trustworthy — lean on it, chunk large.
    "md": ChunkProfile(target=1500, maximum=2000, minimum=250),
    # PDF extraction interleaves headers, footers and column artefacts. Smaller
    # chunks limit how much noise any one embedding has to carry, and bare-title
    # detection is on because a PDF heading arrives as an unmarked short line.
    "pdf": ChunkProfile(target=1000, maximum=1800, minimum=200, detect_bare_titles=True),
    # DOCX paragraphs survive extraction cleanly, but styling does not.
    "docx": ChunkProfile(target=1200, maximum=2000, minimum=200, detect_bare_titles=True),
    "txt": ChunkProfile(),
}
_DEFAULT_PROFILE = ChunkProfile()


@dataclass(frozen=True)
class Chunk:
    """One chunk, with the heading trail it was found under."""

    index: int
    body: str
    heading_path: tuple[str, ...] = ()

    @property
    def heading_label(self) -> str:
        return " > ".join(self.heading_path)

    @property
    def content(self) -> str:
        """What gets embedded and full-text indexed — heading trail included.

        Both retrievers read this field, so the heading has to be *in* it.
        """
        if not self.heading_path:
            return self.body
        return f"{self.heading_label}\n\n{self.body}"


def profile_for(source_type: Optional[str]) -> ChunkProfile:
    return PROFILES.get((source_type or "").lower().lstrip("."), _DEFAULT_PROFILE)


@dataclass
class _Section:
    heading_path: tuple[str, ...]
    lines: list[str]


def _split_sections(text: str, profile: ChunkProfile) -> list[_Section]:
    """Walk the document, tracking the current heading trail.

    A heading at depth *n* replaces everything from depth *n* down, so
    "1 Terms" → "1.2 Late Fees" → "2 Delivery" yields the trails you would
    expect rather than an ever-growing list.
    """
    sections: list[_Section] = [_Section((), [])]
    trail: list[str] = []
    lines = text.splitlines()

    for i, raw in enumerate(lines):
        line = raw.rstrip()
        # A setext underline belongs to the title above, which was already
        # consumed as a heading — drop it rather than emitting "=====" as prose.
        if _SETEXT.match(line.strip()) and i > 0 and lines[i - 1].strip():
            continue
        heading, depth = _as_heading(line, lines, i, profile)
        if heading is None or depth is None:
            sections[-1].lines.append(raw)
            continue
        del trail[depth - 1:]
        trail.append(heading)
        sections.append(_Section(tuple(trail), []))

    return [s for s in sections if any(ln.strip() for ln in s.lines)]


def _as_heading(
    line: str, lines: Sequence[str], i: int, profile: ChunkProfile,
) -> tuple[Optional[str], Optional[int]]:
    """Classify a line as a heading and its nesting depth, or (None, None)."""
    if not line.strip():
        return None, None

    atx = _ATX.match(line)
    if atx:
        # The `#` count is explicit depth and wins over any numbering in the text.
        return _clean_title(atx.group(2)), len(atx.group(1))

    numbered = _NUMBERED.match(line)
    if numbered:
        return _clean_title(numbered.group(2)), numbered.group(1).count(".") + 1

    # A title underlined by === or --- on the following line.
    if i + 1 < len(lines) and _SETEXT.match(lines[i + 1].strip()):
        if line.strip() and len(line.strip()) <= 200:
            return _clean_title(line), 1 if lines[i + 1].strip()[0] == "=" else 2

    if profile.detect_bare_titles and _is_bare_title(line, lines, i):
        return _clean_title(line), 1

    return None, None


def _is_bare_title(line: str, lines: Sequence[str], i: int) -> bool:
    """A short, unpunctuated line surrounded by blanks — a heading without markup.

    Deliberately conservative: PDF and DOCX extractions have no markup to go on,
    but a false positive here fragments a paragraph, so it demands the blank-line
    isolation a real heading has.
    """
    stripped = line.strip()
    if not _BARE_TITLE.match(stripped):
        return False
    if len(stripped.split()) > 12:
        return False
    before_blank = i == 0 or not lines[i - 1].strip()
    after_blank = i + 1 >= len(lines) or not lines[i + 1].strip()
    return before_blank and after_blank


def _paragraphs(lines: Sequence[str]) -> list[str]:
    """Group lines into paragraphs on blank-line boundaries."""
    paras: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line.strip())
        elif current:
            paras.append(" ".join(current))
            current = []
    if current:
        paras.append(" ".join(current))
    return paras


def _split_oversized(text: str, profile: ChunkProfile) -> list[str]:
    """Break a paragraph longer than the cap, preferring sentence boundaries."""
    if len(text) <= profile.maximum:
        return [text]

    out: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(text):
        if current and len(current) + len(sentence) + 1 > profile.target:
            out.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        out.append(current.strip())

    # A single sentence longer than the cap (tables, minified text) still has to
    # be cut somewhere; a hard slice is the honest last resort.
    final: list[str] = []
    for piece in out:
        while len(piece) > profile.maximum:
            final.append(piece[:profile.maximum])
            piece = piece[profile.maximum:]
        if piece:
            final.append(piece)
    return final


def _pack(paragraphs: Sequence[str], profile: ChunkProfile) -> list[str]:
    """Fill chunks up to the target, never breaking a paragraph unnecessarily."""
    bodies: list[str] = []
    current = ""
    for para in paragraphs:
        for piece in _split_oversized(para, profile):
            if not current:
                current = piece
            elif len(current) + len(piece) + 2 <= profile.target:
                current = f"{current}\n\n{piece}"
            else:
                bodies.append(current)
                current = piece
    if current:
        bodies.append(current)

    # Fold a runt tail into its predecessor rather than embedding a stub.
    if len(bodies) > 1 and len(bodies[-1]) < profile.minimum:
        tail = bodies.pop()
        if len(bodies[-1]) + len(tail) + 2 <= profile.maximum:
            bodies[-1] = f"{bodies[-1]}\n\n{tail}"
        else:
            bodies.append(tail)
    return bodies


def chunk_document(
    text: str, *, source_type: Optional[str] = None,
    profile: Optional[ChunkProfile] = None,
) -> list[Chunk]:
    """Split ``text`` into structure-aware chunks carrying heading context.

    Returns an empty list for empty input — a document that extracted to nothing
    should produce no chunks rather than one empty embedding.
    """
    if not text or not text.strip():
        return []

    prof = profile or profile_for(source_type)
    chunks: list[Chunk] = []
    for section in _split_sections(text, prof):
        for body in _pack(_paragraphs(section.lines), prof):
            chunks.append(Chunk(
                index=len(chunks), body=body, heading_path=section.heading_path,
            ))
    return chunks
