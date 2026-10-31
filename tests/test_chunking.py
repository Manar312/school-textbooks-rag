from app.services.chunking import build_chunks, split_blocks


def test_headings_math_and_tables_stay_atomic():
    page = "# الدرس الأول\nنص عادي.\n\n$$\nx^2 + y^2 = z^2\n$$\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    kinds = [b.kind for b in split_blocks(page, 1)]
    assert kinds == ["heading", "para", "math", "table"]


def test_chunks_track_pages_and_heading_path():
    pages = [(1, "# Chapter 1\n## Section A\n" + "word " * 100), (2, "More text here. " * 40)]
    chunks = build_chunks(pages, "book1", target=600, max_chars=900)
    assert chunks and chunks[0].page_start == 1 and chunks[-1].page_end == 2
    assert chunks[0].heading_path[:2] == ["Chapter 1", "Section A"]
    assert all(len(c.text) <= 1200 for c in chunks)


def test_chunk_keys_are_stable_and_unique():
    pages = [(1, "# T\n" + "alpha beta gamma. " * 200)]
    a = build_chunks(pages, "b", target=500, max_chars=800)
    b = build_chunks(pages, "b", target=500, max_chars=800)
    assert [c.key for c in a] == [c.key for c in b]
    assert len({c.key for c in a}) == len(a)
    assert build_chunks(pages, "other", 500, 800)[0].key != a[0].key


def test_oversized_table_is_split_with_header_repeated():
    rows = "\n".join(f"| {i} | value {i} |" for i in range(200))
    page = "| n | v |\n|---|---|\n" + rows
    chunks = build_chunks([(1, page)], "b", target=500, max_chars=600)
    assert len(chunks) > 1
    assert all(c.text.startswith("| n | v |") for c in chunks)


def test_noise_chunks_are_dropped():
    assert build_chunks([(1, "...\n\n---\n\n12")], "b") == []


def test_unbroken_text_is_hard_split():
    chunks = build_chunks([(1, "x" * 5000)], "b", target=500, max_chars=800)
    assert len(chunks) >= 6 and all(len(c.text) <= 800 for c in chunks)
