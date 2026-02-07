import pdfplumber
import pytesseract
import json
import re   #regex matching captions like “Fig. 1”, “Table"
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
#Detects whether a line is a caption or not.
def detect_caption(text):
    text = text.strip()

    # Match TABLE II, TABLE 2, Table 1
    table_match = re.match(r"^(table)\s+([ivxlcdm]+|\d+)\b\.?", text, re.IGNORECASE)

    if table_match:
        return {
            "type": "table",
            "number": table_match.group(2),
            "caption": text
        }

    # Match Fig. 3, Fig 3, Figure 3
    fig_match = re.match(r"^(fig\.?|figure)\s+(\d+)\b\.?", text, re.IGNORECASE)

    if fig_match:
        return {
            "type": "figure",
            "number": fig_match.group(2),
            "caption": text
        }


    return None


# ---------------- Group words into lines ----------------
#y_threshold=3 = how close two words must be vertically to be considered in the same line.
def group_words_into_lines(words, y_threshold=3):
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

    if current_line:   #Because the last line will never be added inside loop automatically.
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


# ---------------- Extract paragraphs ----------------
def extract_paragraphs_from_lines(lines, gap_threshold=12):
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


# ---------------- Geometry helpers ----------------
def vertical_gap(bbox1, bbox2):  #bbox= bounding boxes
    """
    Returns positive gap if bbox2 is below bbox1.
    bbox = (x0, top, x1, bottom)
    """
    return bbox2[1] - bbox1[3]


def vertical_overlap(b1, b2):
    """
    checks if vertical projection overlaps
    """
    return not (b1[3] < b2[1] or b2[3] < b1[1])


def horizontal_overlap(b1, b2):
    """
    checks if horizontal projection overlaps
    """
    return not (b1[2] < b2[0] or b2[2] < b1[0])


def bbox_center_distance(b1, b2):
    c1y = (b1[1] + b1[3]) / 2
    c2y = (b2[1] + b2[3]) / 2
    return abs(c1y - c2y)


# ---------------- Universal Caption Linking ----------------
def link_caption_to_nearest_object(caption, objects):
    """
    Links caption to nearest object either above or below.
    Uses vertical distance + overlap scoring.
    """

    cap_bbox = caption["bbox"]

    best_obj = None
    best_score = 999999

    for obj in objects:
        obj_bbox = obj["bbox"]

        # Prefer objects that overlap horizontally
        overlap_bonus = 0
        if horizontal_overlap(cap_bbox, obj_bbox):
            overlap_bonus = -200  # reduce score strongly

        dist = bbox_center_distance(cap_bbox, obj_bbox)

        score = dist + overlap_bonus

        if score < best_score:
            best_score = score
            best_obj = obj

    return best_obj


# ---------------- Universal Paragraph Linking ----------------
def link_paragraph_to_objects(paragraph, objects, max_distance=160):
    """
    Links paragraph to nearby objects (above or below).
    """
    para_bbox = (0, paragraph["top"], 9999, paragraph["bottom"])

    linked = []

    for obj in objects:
        obj_bbox = obj["bbox"]

        dist = bbox_center_distance(para_bbox, obj_bbox)

        if dist <= max_distance:
            linked.append(obj)

    return linked


# ---------------- Main Phase 4 ----------------
def build_phase4_links(pdf_path, output_json_path):

    output = {
        "pdf_path": pdf_path,
        "pages": []
    }

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

        for page_no, page in enumerate(pdf.pages, start=1):

            print(f"➡️ Universal Linking Page {page_no}/{total_pages}")
            
            try:
                page_full_text = page.extract_text(layout=True) or ""
            except:
                page_full_text = ""

            words = page.extract_words()    #Extracts all words with coordinates
            lines = group_words_into_lines(words)

            # -------- Captions detection --------
            captions = []
            for i in range(len(lines)):
              cap = detect_caption(lines[i]["text"])

              if cap:
                full_caption = lines[i]["text"].strip()

                # Check next line (caption title line)
                if i + 1 < len(lines):
                   next_line = lines[i + 1]["text"].strip()

                    # If next line looks like a caption title
                   if len(next_line) < 140 and (next_line.isupper() or next_line.istitle()):
                       full_caption += " " + next_line

                cap["caption"] = full_caption
                cap["bbox"] = lines[i]["bbox"]
                captions.append(cap)

            # -------- Extract tables --------
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

            # -------- Extract images --------
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

            # -------- Link captions to tables/images (above or below) --------
            for cap in captions:
                if cap["type"] == "table":
                    best_table = link_caption_to_nearest_object(cap, tables)
                    if best_table:   #Assign the caption to that table.
                        best_table["caption"] = cap["caption"]

                if cap["type"] == "figure":
                    best_img = link_caption_to_nearest_object(cap, images)
                    if best_img:  #Assign caption to that image.
                        best_img["caption"] = cap["caption"]

            # -------- Extract paragraphs --------
            paragraphs = extract_paragraphs_from_lines(lines)

            # -------- Link paragraphs to nearest objects (both sides) --------
            blocks = []

            for para in paragraphs:
                linked_tables = link_paragraph_to_objects(para, tables, max_distance=200)
                linked_images = link_paragraph_to_objects(para, images, max_distance=200)

                blocks.append({
                    "paragraph_text": para["text"],
                    "bbox": (0, para["top"], page.width, para["bottom"]),
                    "linked_tables": linked_tables,
                    "linked_images": linked_images
                })

            output["pages"].append({
                "page": page_no,
                "page_full_text": page_full_text.strip(),
                "captions_found": captions,
                "tables_found": tables,
                "images_found": images,
                "blocks": blocks
            })

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("\n✅ Universal Phase 4 Linking Completed.")
    print("📌 Output saved at:", output_json_path)


if __name__ == "__main__":

    file_hash = "962ae562ca933789fddeee27ca086458"

    pdf_path = f"data/uploads/{file_hash}.pdf"
    output_path = f"data/cache/{file_hash}_phase4_universal.json"

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"❌ PDF not found: {pdf_path}")

    build_phase4_links(pdf_path, output_path)
