"""Structure-aware chunking of page markdown.

- Keeps tables and $$ math blocks atomic (tables split by rows with header repeated only when oversized).
- Tracks the heading path and page range for every chunk.
- Stable chunk keys => idempotent upserts.
"""
import hashlib
import re
import uuid
from dataclasses import dataclass, field

_NS = uuid.UUID("6f1c5e0a-3a39-4f0e-9b6a-5a1f0c2d7e11")
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_SENT_SPLIT = re.compile(r"(?<=[.!?؟۔])\s+")


@dataclass
class Block:
    text: str
    page: int
    kind: str  # heading | para | table | math
    level: int = 0


@dataclass
class Chunk:
    index: int
    text: str
    heading_path: list[str]
    page_start: int
    page_end: int
    key: str = ""

    @property
    def point_id(self) -> str:
        return str(uuid.uuid5(_NS, self.key))


def split_blocks(page_text: str, page: int) -> list[Block]:
    blocks: list[Block] = []
    buf: list[str] = []
    in_math = False

    def flush(kind="para"):
        nonlocal buf
        txt = "\n".join(buf).strip()
        if txt:
            blocks.append(Block(txt, page, kind))
        buf = []

    for line in page_text.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if in_math:
            buf.append(line)
            if s.endswith("$$"):
                in_math = False
                flush("math")
            continue
        if s.startswith("$$") and not (len(s) > 3 and s.endswith("$$")):
            flush()
            buf.append(line)
            in_math = True
            continue
        if s.startswith("$$") and s.endswith("$$") and len(s) > 3:
            flush()
            buf.append(line)
            flush("math")
            continue
        m = _HEADING.match(s)
        if m:
            flush()
            blocks.append(Block(m.group(2), page, "heading", len(m.group(1))))
            continue
        if s.startswith("|"):
            if buf and not buf[0].strip().startswith("|"):
                flush()
            buf.append(line)
            continue
        if not s:
            if buf and buf[0].strip().startswith("|"):
                flush("table")
            else:
                flush()
            continue
        if buf and buf[0].strip().startswith("|"):
            flush("table")
        buf.append(line)
    if in_math:
        flush("math")
    elif buf and buf[0].strip().startswith("|"):
        flush("table")
    else:
        flush()
    return blocks


def _split_oversized(b: Block, max_chars: int) -> list[Block]:
    if len(b.text) <= max_chars:
        return [b]
    parts: list[str] = []
    if b.kind == "table":
        lines = b.text.split("\n")
        header = lines[:2] if len(lines) > 2 else lines[:1]
        cur = list(header)
        for ln in lines[len(header):]:
            if sum(len(x) + 1 for x in cur) + len(ln) > max_chars and len(cur) > len(header):
                parts.append("\n".join(cur))
                cur = list(header)
            cur.append(ln)
        parts.append("\n".join(cur))
    else:
        cur = ""
        for sent in _SENT_SPLIT.split(b.text):
            while len(sent) > max_chars:  # no sentence boundary at all: hard split
                if cur:
                    parts.append(cur)
                    cur = ""
                parts.append(sent[:max_chars])
                sent = sent[max_chars:]
            if cur and len(cur) + len(sent) + 1 > max_chars:
                parts.append(cur)
                cur = sent
            else:
                cur = f"{cur} {sent}".strip()
        if cur:
            parts.append(cur)
    return [Block(p, b.page, b.kind) for p in parts if p.strip()]


def build_chunks(pages: list[tuple[int, str]], book_id: str, target: int = 1500, max_chars: int = 2400) -> list[Chunk]:
    """pages: [(page_number, markdown_text)] in reading order."""
    blocks: list[Block] = []
    for pn, txt in pages:
        for b in split_blocks(txt or "", pn):
            blocks.extend(_split_oversized(b, max_chars) if b.kind != "heading" else [b])

    chunks: list[Chunk] = []
    heading_stack: list[tuple[int, str]] = []
    cur: list[Block] = []
    cur_len = 0
    cur_path: list[str] = []

    def path() -> list[str]:
        return [h for _, h in heading_stack]

    def flush():
        nonlocal cur, cur_len
        if not cur:
            return
        text = "\n\n".join(b.text for b in cur).strip()
        if sum(ch.isalnum() for ch in text) >= 15:
            c = Chunk(len(chunks), text, cur_path, cur[0].page, cur[-1].page)
            c.key = hashlib.sha256(f"{book_id}:{c.index}:{hashlib.sha256(text.encode()).hexdigest()}".encode()).hexdigest()[:32]
            chunks.append(c)
        cur, cur_len = [], 0

    for b in blocks:
        if b.kind == "heading":
            # a major heading closes the current chunk if it has substance
            if b.level <= 2 and cur_len >= 400:
                flush()
            while heading_stack and heading_stack[-1][0] >= b.level:
                heading_stack.pop()
            heading_stack.append((b.level, b.text))
            if not cur:
                cur_path = path()
            cur.append(b)
            cur_len += len(b.text)
            continue
        if cur and cur_len + len(b.text) > target:
            # carry heading-only tail into next chunk to avoid orphan headings
            tail = []
            while cur and cur[-1].kind == "heading":
                tail.insert(0, cur.pop())
            flush()
            cur = tail
            cur_len = sum(len(x.text) for x in tail)
            cur_path = path()
        if all(x.kind == "heading" for x in cur):  # first body block: use the deepest heading in effect
            cur_path = path()
        cur.append(b)
        cur_len += len(b.text)
    flush()
    return chunks


def embedding_text(chunk: Chunk, title: str, subject: str) -> str:
    head = " > ".join(chunk.heading_path)
    return f"{subject} — {title}\n{head}\n\n{chunk.text}".strip()
