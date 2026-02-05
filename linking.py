import pdfplumber
import pytesseract
import json
import re
import os
import cv2
import numpy as np
from PIL import Image


# If tesseract not in PATH:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# ---------------- OCR preprocessing ----------------
def preprocess_for_ocr(pil_image):
    img = np.array(pil_image)

    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    else:
        gray = img

    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 10
    )

    return Image.fromarray(thresh)


# ---------------- Caption detection ----------------
def detect_caption_type(text):
    t = text.strip().lower()

    if re.match(r"^(table)\s*[ivx0-9]+", t):
        return "table"

    if re.match(r"^(fig\.|figure)\s*[0-9]+", t):
        return "figure"

    return None


def group_words_into_lines(words, y_threshold=3):
    """
    Groups extracted words into lines using their vertical position.
    Returns lines with bbox coordinates.
    """
    if not words:
        return []

    words = sorted(words, key=lambda w: (w["top"], w["x0"]))

    lines = []
    current_line = [words[0]]
    current_top = words[0]["top"]

    for w in words[1:]:
        if abs(w["top"] - current_top) <= y_threshold:
            current_line.append(w)
        else:
            lines.append(current_line)
            current_line = [w]
            current_top = w["top"]

    if current_line:
        lines.append(current_line)

    line_objects = []
    for line in lines:
        text = " ".join([w["text"] for w in line]).strip()

        x0 = min(w["x0"] for w in line)
        x1 = max(w["x1"] for w in line)
        top = min(w["top"] for w in line)
        bottom = max(w["bottom"] for w in line)

        line_objects.append({
            "text": text,
            "bbox": (x0, top, x1, bottom),
            "top": top,
            "bottom": bottom
        })

    return line_objects


def extract_paragraphs_from_lines(lines, gap_threshold=12):
    """
    Merge lines into paragraphs based on vertical gaps.
    """
    if not lines:
        return []

    paragraphs = []
    current_para_text = lines[0]["text"]
    para_top = lines[0]["top"]
    para_bottom = lines[0]["bottom"]

    for i in range(1, len(lines)):
        prev = lines[i - 1]
        curr = lines[i]

        gap = curr["top"] - prev["bottom"]

        if gap > gap_threshold:
            paragraphs.append({
                "text": current_para_text.strip(),
                "top": para_top,
                "bottom": para_bottom
            })

            current_para_text = curr["text"]
            para_top = curr["top"]
            para_bottom = curr["bottom"]
        else:
            current_para_text += " " + curr["text"]
            para_bottom = max(para_bottom, curr["bottom"])

    paragraphs.append({
        "text": current_para_text.strip(),
        "top": para_top,
        "bottom": para_bottom
    })

    return paragraphs


# ---------------- Linking logic ----------------
def bbox_vertical_distance(b1, b2):
    """
    Distance between two bboxes in vertical direction.
    b = (x0, top, x1, bottom)
    """
    return abs(b1[1] - b2[1])


def is_below(caption_bbox, obj_bbox):
    return obj_bbox[1] >= caption_bbox[3]


def is_above(para_bbox, obj_bbox):
    return para_bbox[3] <= obj_bbox[1]


def build_phase4_links(pdf_path, output_json_path):

    output = {
        "pdf_path": pdf_path,
        "pages": []
    }

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

        for page_no, page in enumerate(pdf.pages, start=1):

            print(f"➡️ Phase 4 Linking Page {page_no}/{total_pages}")

            words = page.extract_words()
            lines = group_words_into_lines(words)

            # ---- Detect captions ----
            captions = []
            for ln in lines:
                cap_type = detect_caption_type(ln["text"])
                if cap_type:
                    captions.append({
                        "type": cap_type,
                        "caption": ln["text"],
                        "bbox": ln["bbox"]
                    })

            # ---- Extract tables with bbox ----
            tables = []
            try:
                table_objects = page.find_tables()
                for t_index, t_obj in enumerate(table_objects, start=1):
                    tables.append({
                        "table_number": t_index,
                        "bbox": t_obj.bbox,
                        "rows": t_obj.extract(),
                        "caption": None
                    })
            except:
                pass

            # ---- Extract images with bbox + OCR ----
            images = []
            for img_index, img in enumerate(page.images, start=1):
                bbox = (img["x0"], img["top"], img["x1"], img["bottom"])

                try:
                    cropped = page.crop(bbox)
                    pil_img = cropped.to_image(resolution=300).original
                    processed = preprocess_for_ocr(pil_img)

                    ocr_text = pytesseract.image_to_string(processed).strip()
                except:
                    ocr_text = ""

                images.append({
                    "image_number": img_index,
                    "bbox": bbox,
                    "ocr_text": ocr_text,
                    "caption": None
                })

            # ---- Caption → Object linking (BEST RULE) ----
            # Caption usually appears ABOVE object
            for cap in captions:
                if cap["type"] == "table":
                    best_table = None
                    best_dist = 999999

                    for t in tables:
                        if is_below(cap["bbox"], t["bbox"]):
                            dist = t["bbox"][1] - cap["bbox"][3]
                            if dist < best_dist:
                                best_dist = dist
                                best_table = t

                    if best_table:
                        best_table["caption"] = cap["caption"]

                if cap["type"] == "figure":
                    best_img = None
                    best_dist = 999999

                    for im in images:
                        if is_below(cap["bbox"], im["bbox"]):
                            dist = im["bbox"][1] - cap["bbox"][3]
                            if dist < best_dist:
                                best_dist = dist
                                best_img = im

                    if best_img:
                        best_img["caption"] = cap["caption"]

            # ---- Paragraph extraction ----
            paragraphs = extract_paragraphs_from_lines(lines)

            # ---- Paragraph → linked objects (citation style) ----
            linked_blocks = []

            for para in paragraphs:
                para_bbox = (0, para["top"], page.width, para["bottom"])

                linked_tables = []
                linked_images = []

                # Link table if it is immediately below paragraph
                for t in tables:
                    if is_above(para_bbox, t["bbox"]):
                        vertical_gap = t["bbox"][1] - para_bbox[3]
                        if vertical_gap < 120:  # strong heuristic
                            linked_tables.append(t)

                # Link image if immediately below paragraph
                for im in images:
                    if is_above(para_bbox, im["bbox"]):
                        vertical_gap = im["bbox"][1] - para_bbox[3]
                        if vertical_gap < 120:
                            linked_images.append(im)

                linked_blocks.append({
                    "paragraph_text": para["text"],
                    "bbox": para_bbox,
                    "linked_tables": linked_tables,
                    "linked_images": linked_images
                })

            output["pages"].append({
                "page": page_no,
                "captions_found": captions,
                "tables_found": tables,
                "images_found": images,
                "blocks": linked_blocks
            })

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("\n✅ Phase 4 Perfect Linking Completed.")
    print("📌 Output saved at:", output_json_path)


if __name__ == "__main__":

    file_hash = "962ae562ca933789fddeee27ca086458"

    pdf_path = f"data/uploads/{file_hash}.pdf"
    output_path = f"data/cache/{file_hash}_phase4_linked.json"

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"❌ PDF not found: {pdf_path}")

    build_phase4_links(pdf_path, output_path)
