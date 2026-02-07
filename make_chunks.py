import json
import os
import hashlib
import re


# ---------------- Utility: Clean text ----------------
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)  #replaces multiple spaces/newlines/tabs with single space
    return text.strip()


# ---------------- Convert table rows into readable text ----------------
def table_to_text(table_rows):
    if not table_rows:
        return ""

    lines = []
    for row in table_rows:
        clean_row = []
        for cell in row:
            if cell is None:
                clean_row.append("")
            else:
                clean_row.append(str(cell).strip())

        lines.append(" | ".join(clean_row))

    return "\n".join(lines).strip()


# ---------------- Chunk Builder ----------------
def build_chunk_text(page_no, paragraph_text=None, tables=None, images=None, chunk_type="paragraph"):
    chunk_text = f"[PAGE: {page_no}]\n"
    chunk_text += f"[CHUNK TYPE: {chunk_type.upper()}]\n\n"

    citations = []

    # ---------- Paragraph ----------
    if paragraph_text:
        chunk_text += "PARAGRAPH:\n"
        chunk_text += clean_text(paragraph_text) + "\n\n"

    # ---------- Tables ----------
    if tables:
        for t in tables:
            caption = t.get("caption") or f"Table {t.get('table_number')}"
            citations.append(caption)

            chunk_text += f"[CITED TABLE: {caption}]\n"
            chunk_text += table_to_text(t.get("rows", [])) + "\n\n"

    # ---------- Images / Figures ----------
    if images:
        for im in images:
            caption = im.get("caption") or f"Image {im.get('image_number')}"
            citations.append(caption)

            ocr_text = clean_text(im.get("ocr_text", ""))

            chunk_text += f"[CITED FIGURE: {caption}]\n"
            if ocr_text:
                chunk_text += ocr_text + "\n\n"
            else:
                chunk_text += "(No OCR text extracted)\n\n"

    return chunk_text.strip(), citations


# ---------------- Split long text into smaller chunks ----------------
def split_long_text(text, max_chars=1400):
    if len(text) <= max_chars:
        return [text]

    parts = []
    start = 0
    while start < len(text):
        parts.append(text[start:start + max_chars])
        start += max_chars

    return parts


# ---------------- Main Phase 5 ----------------
def make_chunks(phase4_json_path, output_chunks_path):

    if not os.path.exists(phase4_json_path):
        raise FileNotFoundError(f" Phase 4 file not found: {phase4_json_path}")

    with open(phase4_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_chunks = []   #stores all final chunks
    seen_hashes = set()  #prevents duplicate chunks

    for page_data in data["pages"]:
        page_no = page_data["page"]

        # Extract all objects on that page
        tables_found = page_data.get("tables_found", [])
        images_found = page_data.get("images_found", [])

        # Keep track of used tables/images
        used_table_ids = set()
        used_image_ids = set()

        # ---------------- PARAGRAPH BASED CHUNKS ----------------
        for block in page_data.get("blocks", []):

            paragraph_text = block.get("paragraph_text", "").strip()
            if not paragraph_text:
                continue

            linked_tables = block.get("linked_tables", [])
            linked_images = block.get("linked_images", [])

            # mark linked ones as used
            for t in linked_tables:
                used_table_ids.add(str(t.get("bbox")))  #We store bbox string as unique ID for table.

            for im in linked_images:
                used_image_ids.add(str(im.get("bbox")))

            chunk_text, citations = build_chunk_text(
                page_no=page_no,
                paragraph_text=paragraph_text,
                tables=linked_tables,
                images=linked_images,
                chunk_type="paragraph"
            )

            # split if too long
            sub_chunks = split_long_text(chunk_text, max_chars=1600)

            for sub in sub_chunks:
                chunk_id = hashlib.md5(sub.encode("utf-8")).hexdigest()

                if chunk_id not in seen_hashes:
                    seen_hashes.add(chunk_id)

                    all_chunks.append({
                        "chunk_id": chunk_id,
                        "page": page_no,
                        "text": sub,
                        "citations": citations,
                        "contains_table": len(linked_tables) > 0,
                        "contains_figure": len(linked_images) > 0,
                        "chunk_type": "paragraph"
                    })

        # ---------------- TABLE ONLY CHUNKS (if not linked) ----------------
        for t in tables_found:
            table_id = str(t.get("bbox"))

            if table_id in used_table_ids:
                continue

            chunk_text, citations = build_chunk_text(
                page_no=page_no,
                paragraph_text=None,
                tables=[t],
                images=None,
                chunk_type="table_only"
            )

            chunk_id = hashlib.md5(chunk_text.encode("utf-8")).hexdigest()

            if chunk_id not in seen_hashes:
                seen_hashes.add(chunk_id)

                all_chunks.append({
                    "chunk_id": chunk_id,
                    "page": page_no,
                    "text": chunk_text,
                    "citations": citations,
                    "contains_table": True,
                    "contains_figure": False,
                    "chunk_type": "table_only"
                })

        # ---------------- FIGURE ONLY CHUNKS (if not linked) ----------------
        for im in images_found:
            image_id = str(im.get("bbox"))

            if image_id in used_image_ids:
                continue

            chunk_text, citations = build_chunk_text(
                page_no=page_no,
                paragraph_text=None,
                tables=None,
                images=[im],
                chunk_type="figure_only"
            )

            chunk_id = hashlib.md5(chunk_text.encode("utf-8")).hexdigest()

            if chunk_id not in seen_hashes:
                seen_hashes.add(chunk_id)

                all_chunks.append({
                    "chunk_id": chunk_id,
                    "page": page_no,
                    "text": chunk_text,
                    "citations": citations,
                    "contains_table": False,
                    "contains_figure": True,
                    "chunk_type": "figure_only"
                })

        # ---------------- PAGE FULL TEXT FALLBACK CHUNK ----------------
        # This ensures absolutely nothing is missed.
        page_full_text = page_data.get("page_full_text", "").strip()

        if page_full_text:
            page_full_text = clean_text(page_full_text)

            # Break into multiple chunks
            text_parts = split_long_text(page_full_text, max_chars=1600)

            for idx, part in enumerate(text_parts, start=1):
                fallback_text = f"[PAGE: {page_no}]\n[CHUNK TYPE: FULL_TEXT_FALLBACK]\n\n{part}"

                chunk_id = hashlib.md5(fallback_text.encode("utf-8")).hexdigest()

                if chunk_id not in seen_hashes:
                    seen_hashes.add(chunk_id)

                    all_chunks.append({
                        "chunk_id": chunk_id,
                        "page": page_no,
                        "text": fallback_text,
                        "citations": [],
                        "contains_table": False,
                        "contains_figure": False,
                        "chunk_type": "full_text_fallback"
                    })

    # ---------------- SAVE CHUNKS ----------------
    with open(output_chunks_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)

    print("\n✅ Phase 5 Chunking Completed Successfully!")
    print("📌 Total Chunks Created:", len(all_chunks))
    print("📌 Output saved at:", output_chunks_path)


# ---------------- RUN ----------------
if __name__ == "__main__":

    file_hash = "962ae562ca933789fddeee27ca086458"

    phase4_json_path = f"data/cache/{file_hash}_phase4_universal.json"
    output_chunks_path = f"data/cache/{file_hash}_chunks_final.json"

    make_chunks(phase4_json_path, output_chunks_path)
