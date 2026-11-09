from __future__ import annotations


def build_text_pdf(pages: tuple[str, ...]) -> bytes:
    """Return a deterministic, uncompressed PDF containing Helvetica text."""
    if not pages:
        raise ValueError("at least one page is required")
    encoded_pages = tuple(page.encode("ascii") for page in pages)
    page_ids = tuple(4 + index * 2 for index in range(len(pages)))
    content_ids = tuple(page_id + 1 for page_id in page_ids)
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Count {len(pages)} /Kids [{kids}] >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for page_id, content_id, page in zip(page_ids, content_ids, encoded_pages):
        lines = page.splitlines() or [b""]
        escaped = [
            line.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            for line in lines
        ]
        text = b" Tj T* ".join(b"(" + line + b")" for line in escaped) + b" Tj"
        stream = b"BT /F1 12 Tf 14 TL 72 720 Td " + text + b" ET"
        objects.extend(
            (
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 3 0 R >> >> "
                    f"/Contents {content_id} 0 R >>"
                ).encode("ascii"),
                b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
                + stream
                + b"\nendstream",
            )
        )
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{object_id} 0 obj\n".encode("ascii"))
        document.extend(body)
        document.extend(b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(document)
