"""Builds tiny, valid text PDFs in memory so tests don't need a PDF-writing dependency."""


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(pages: list[str]) -> bytes:
    """One page per string; each line of a string becomes a line of Helvetica text.

    An empty string produces a page with no text (like a scanned image page).
    """
    objects: dict[int, bytes] = {
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    kids: list[int] = []
    next_id = 4
    for text in pages:
        page_id, content_id = next_id, next_id + 1
        next_id += 2
        ops = ["BT", "/F1 11 Tf", "14 TL", "50 750 Td"]
        ops += [f"({_escape(line)}) Tj T*" for line in text.split("\n")] if text else []
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objects[content_id] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode()
        kids.append(page_id)
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kid_refs = " ".join(f"{kid} 0 R" for kid in kids)
    objects[2] = f"<< /Type /Pages /Kids [{kid_refs}] /Count {len(kids)} >>".encode()

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for obj_id in sorted(objects):
        offsets[obj_id] = len(out)
        out += f"{obj_id} 0 obj\n".encode() + objects[obj_id] + b"\nendobj\n"
    xref_position = len(out)
    size = max(objects) + 1
    out += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for obj_id in range(1, size):
        out += f"{offsets[obj_id]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_position}\n%%EOF\n".encode()
    return bytes(out)
