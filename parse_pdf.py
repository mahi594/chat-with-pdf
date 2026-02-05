import pdfplumber
import pytesseract
import json
import cv2
import numpy as np
from PIL import Image
from pytesseract import Output


# If tesseract is not in PATH, uncomment and set correct path:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def preprocess_image_for_ocr(pil_image):
    """
    Improves OCR quality for flowcharts, tables, graphs.
    """
    img = np.array(pil_image)

    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    else:
        gray = img

    # Increase contrast + thresholding
    gray = cv2.GaussianBlur(gray, (3, 3), 0) #Removes noise and smoothens the image.
    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 10
    )

    return Image.fromarray(thresh)


def extract_table_text_from_image(pil_image):
    """
    Extracts table text using OCR word positioning.
    Returns a readable reconstructed table-like string.
    """
    processed = preprocess_image_for_ocr(pil_image)

    data = pytesseract.image_to_data(processed, output_type=Output.DICT)

    lines = {}
    n = len(data["text"])

    for i in range(n):
        word = data["text"][i].strip()
        conf = int(data["conf"][i])

        if word == "" or conf < 40:
            continue

        line_num = data["line_num"][i]
        if line_num not in lines:
            lines[line_num] = []

        lines[line_num].append(word)

    table_text = ""
    for line_num in sorted(lines.keys()):
        table_text += " | ".join(lines[line_num]) + "\n"

    return table_text.strip()


def parse_pdf_to_text(pdf_path, cache_path):

    parsed_data = {
        "pdf_path": pdf_path,
        "text_blocks": [],
        "tables": [],
        "ocr_tables": [],
        "images_and_flowcharts": [],
        "errors": []
    }

    print(f"\n Parsing PDF: {pdf_path}")

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        print(f" Total Pages Found: {total_pages}\n")

        for page_no, page in enumerate(pdf.pages, start=1):

            print(f" Processing Page {page_no}/{total_pages}")

            # ---------------- TEXT EXTRACTION ----------------
            try:
                text = page.extract_text() or ""
                text = text.strip()

                if text:
                    parsed_data["text_blocks"].append({
                        "page": page_no,
                        "content": text
                    })

            except Exception as e:
                parsed_data["errors"].append({
                    "page": page_no,
                    "type": "text_extraction_error",
                    "error": str(e)
                })

            # ---------------- NORMAL TABLE EXTRACTION ----------------
            try:
                tables = page.extract_tables()

                for t_index, table in enumerate(tables, start=1):
                    parsed_data["tables"].append({
                        "page": page_no,
                        "table_number": t_index,
                        "rows": table
                    })

            except Exception as e:
                parsed_data["errors"].append({
                    "page": page_no,
                    "type": "table_extraction_error",
                    "error": str(e)
                })

            # ---------------- OCR FULL PAGE (TABLES + FIGURES) ----------------
            # If the page has very little text but has images,
            # we assume it's scanned/diagram heavy -> OCR whole page
            try:
                page_img = page.to_image(resolution=300).original
                
                processed_page_img = preprocess_image_for_ocr(page_img) # Preprocess for better OCR

                full_page_ocr = pytesseract.image_to_string(processed_page_img).strip()

                if full_page_ocr:
                    parsed_data["images_and_flowcharts"].append({
                        "page": page_no,
                        "type": "full_page_ocr",
                        "ocr_text": full_page_ocr
                    })

            except Exception as e:
                parsed_data["errors"].append({
                    "page": page_no,
                    "type": "full_page_ocr_error",
                    "error": str(e)
                })

            # ---------------- IMAGE OCR (FLOWCHARTS / TABLE IMAGES) ----------------
            try:
                images = page.images
                print(f"   🖼️ Images found: {len(images)}")

                for img_index, img in enumerate(images, start=1):
                    try:
                        bbox = (img["x0"], img["top"], img["x1"], img["bottom"])
                        cropped = page.crop(bbox)

                        pil_image = cropped.to_image(resolution=300).original
                        
                        processed_img = preprocess_image_for_ocr(pil_image)

                        ocr_text = pytesseract.image_to_string(processed_img).strip()

                        # Save as flowchart/graph/image OCR
                        parsed_data["images_and_flowcharts"].append({
                            "page": page_no,
                            "image_number": img_index,
                            "bbox": bbox,
                            "type": "image_or_flowchart_or_graph",
                            "ocr_text": ocr_text
                        })

                        # Try table reconstruction also (OCR structured)
                        table_text = extract_table_text_from_image(pil_image)

                        if len(table_text.splitlines()) >= 2:
                            parsed_data["ocr_tables"].append({
                                "page": page_no,
                                "image_number": img_index,
                                "bbox": bbox,
                                "table_text": table_text
                            })

                    except Exception as e:
                        parsed_data["errors"].append({
                            "page": page_no,
                            "type": "image_ocr_error",
                            "image_number": img_index,
                            "error": str(e)
                        })

            except Exception as e:
                parsed_data["errors"].append({
                    "page": page_no,
                    "type": "image_loop_error",
                    "error": str(e)
                })

            print(f" Finished Page {page_no}\n")

    # ---------------- SAVE CACHE JSON ----------------
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2, ensure_ascii=False)

    print(f" DONE! Parsed output saved to: {cache_path}")
    print(f" Total Text Blocks: {len(parsed_data['text_blocks'])}")
    print(f" Total Tables (pdfplumber): {len(parsed_data['tables'])}")
    print(f" Total OCR Tables (image based): {len(parsed_data['ocr_tables'])}")
    print(f" Total OCR Images/Flowcharts: {len(parsed_data['images_and_flowcharts'])}")
    print(f" Total Errors Logged: {len(parsed_data['errors'])}")

    return parsed_data
