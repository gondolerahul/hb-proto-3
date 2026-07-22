"""Inc 2 / RETR — structure-aware chunking (T2).

The old ingest cut every 500 characters, mid-word. What these pin is that the
new boundaries are *meaningful*: chunks end at paragraph edges, carry the
heading trail they were found under, and stay inside their profile's cap. The
heading trail has to be inside `content` — both retrievers read that field, so a
heading kept only in a metadata column would be invisible to them.
"""
from __future__ import annotations

import pytest

from src.ai.memory.chunking import (
    CURRENT_CHUNK_VERSION,
    PROFILES,
    ChunkProfile,
    chunk_document,
    profile_for,
)

CONTRACT = """# Master Services Agreement

This agreement governs the supply of services between the parties.

## 1. Payment Terms

Net-30 applies to all enterprise invoices.

## 2. Delivery

Delivery is made to the address on the purchase order.
"""


class TestHeadingContext:
    def test_chunks_carry_their_heading_trail(self):
        chunks = chunk_document(CONTRACT, source_type="md")
        payment = [c for c in chunks if "Net-30" in c.body]
        assert payment
        assert payment[0].heading_path == ("Master Services Agreement", "Payment Terms")

    def test_heading_is_inside_content_not_just_metadata(self):
        """Both retrievers read `content` — a heading elsewhere is invisible."""
        chunks = chunk_document(CONTRACT, source_type="md")
        payment = [c for c in chunks if "Net-30" in c.body][0]
        assert "Payment Terms" in payment.content
        assert payment.content.endswith(payment.body)

    def test_a_deeper_heading_extends_the_trail(self):
        text = "# A\n\nintro\n\n## B\n\nbody\n"
        trails = {c.heading_path for c in chunk_document(text, source_type="md")}
        assert ("A",) in trails and ("A", "B") in trails

    def test_a_sibling_heading_replaces_not_extends(self):
        """1 → 1.1 → 2 must not leave 1.1 dangling in section 2's trail."""
        text = "# One\n\na\n\n## Sub\n\nb\n\n# Two\n\nc\n"
        trails = [c.heading_path for c in chunk_document(text, source_type="md")]
        assert ("Two",) in trails
        assert not any(t[:1] == ("Two",) and len(t) > 1 for t in trails)

    def test_numbered_sections_are_headings(self):
        text = "1. Scope\n\nThe scope is broad.\n\n1.1 Exclusions\n\nNone apply.\n"
        trails = {c.heading_path for c in chunk_document(text, source_type="txt")}
        assert ("Scope",) in trails
        assert ("Scope", "Exclusions") in trails

    def test_setext_underline_is_a_heading(self):
        text = "Overview\n========\n\nSome prose here.\n"
        chunks = chunk_document(text, source_type="txt")
        assert chunks[0].heading_path == ("Overview",)
        assert "=====" not in chunks[0].content

    def test_content_without_headings_still_chunks(self):
        chunks = chunk_document("Just prose.\n\nMore prose.\n", source_type="txt")
        assert chunks and chunks[0].heading_path == ()
        assert chunks[0].content == chunks[0].body


class TestBoundaries:
    def test_no_chunk_exceeds_the_profile_maximum(self):
        text = "\n\n".join(f"Paragraph {i}. " + "word " * 120 for i in range(40))
        for source in ("txt", "pdf", "md", "docx"):
            prof = profile_for(source)
            for c in chunk_document(text, source_type=source):
                assert len(c.body) <= prof.maximum, source

    def test_paragraphs_are_not_split_when_they_fit(self):
        para_a = "Alpha. " * 30
        para_b = "Beta. " * 30
        chunks = chunk_document(f"{para_a}\n\n{para_b}", source_type="txt")
        # Both fit inside one 1200-char target chunk, kept whole and together.
        assert len(chunks) == 1
        assert "Alpha." in chunks[0].body and "Beta." in chunks[0].body

    def test_an_oversized_paragraph_splits_on_sentences(self):
        text = " ".join(f"Sentence number {i} here." for i in range(400))
        chunks = chunk_document(text, source_type="txt")
        assert len(chunks) > 1
        # Every boundary lands after a sentence terminator, never mid-word.
        for c in chunks[:-1]:
            assert c.body.rstrip().endswith(".")

    def test_a_single_unbreakable_run_is_hard_split_as_a_last_resort(self):
        text = "x" * 9000  # no sentence or paragraph boundary anywhere
        chunks = chunk_document(text, source_type="txt")
        prof = profile_for("txt")
        assert len(chunks) > 1
        assert all(len(c.body) <= prof.maximum for c in chunks)

    def test_runt_tail_is_folded_back(self):
        """A 20-char trailing stub is a useless embedding on its own."""
        body = "Sentence text here. " * 70   # comfortably over target
        chunks = chunk_document(body + "\n\nTiny.", source_type="txt")
        assert all(
            len(c.body) >= profile_for("txt").minimum or len(chunks) == 1
            for c in chunks
        )

    def test_indices_are_contiguous_from_zero(self):
        chunks = chunk_document(CONTRACT, source_type="md")
        assert [c.index for c in chunks] == list(range(len(chunks)))


class TestProfiles:
    def test_each_source_type_has_its_own_sizing(self):
        assert profile_for("pdf").target < profile_for("md").target

    def test_unknown_and_absent_types_fall_back_to_the_default(self):
        assert profile_for("xlsx") == profile_for(None) == ChunkProfile()

    def test_extension_dot_and_case_are_tolerated(self):
        assert profile_for(".PDF") == PROFILES["pdf"]

    def test_an_explicit_profile_overrides_the_source_type(self):
        tiny = ChunkProfile(target=100, maximum=150, minimum=10)
        chunks = chunk_document("word " * 300, source_type="md", profile=tiny)
        assert all(len(c.body) <= 150 for c in chunks)


class TestBareTitles:
    def test_pdf_extraction_treats_an_isolated_short_line_as_a_heading(self):
        """PDF/DOCX arrive with no markup — the only signal is layout."""
        text = "Refund Policy\n\nRefunds are issued within 14 days.\n"
        chunks = chunk_document(text, source_type="pdf")
        assert chunks[0].heading_path == ("Refund Policy",)

    def test_txt_does_not_guess(self):
        """Without the profile flag, a short line stays prose."""
        text = "Refund Policy\n\nRefunds are issued within 14 days.\n"
        assert chunk_document(text, source_type="txt")[0].heading_path == ()

    def test_a_sentence_is_not_mistaken_for_a_title(self):
        text = "This is an ordinary sentence of prose.\n\nAnd another one here.\n"
        assert all(c.heading_path == () for c in chunk_document(text, source_type="pdf"))

    def test_a_long_line_is_not_a_title(self):
        long_line = "Alpha " * 20
        text = f"{long_line}\n\nBody text follows here.\n"
        assert all(c.heading_path == () for c in chunk_document(text, source_type="pdf"))


class TestEmptyInput:
    @pytest.mark.parametrize("text", ["", "   ", "\n\n\n"])
    def test_nothing_in_nothing_out(self, text):
        """An empty extraction must not produce one empty embedding."""
        assert chunk_document(text, source_type="txt") == []

    def test_headings_with_no_body_produce_no_chunks(self):
        assert chunk_document("# Title\n\n## Sub\n", source_type="md") == []


def test_chunk_version_is_set():
    """The lazy re-chunk sweep keys off this — it must be a real integer."""
    assert isinstance(CURRENT_CHUNK_VERSION, int) and CURRENT_CHUNK_VERSION >= 2
