import pdfplumber

def analyze_pdf(file_path):
    stats = {
        "pages": 0,
        "words": 0,
        "tables": 0,
        "images": 0,
        "flowcharts_or_graphs": 0
    }

    with pdfplumber.open(file_path) as pdf:
        stats["pages"] = len(pdf.pages)

        for page in pdf.pages:
            text = page.extract_text() or ""
            upper_text = text.upper()

            # -------------------------
            # TEXT METRICS
            # -------------------------
            stats["words"] += len(text.split())

            # -------------------------
            # TABLE INFERENCE
            # -------------------------
            # 1. Structural table detection
            tables = page.extract_tables()
            if tables:
                stats["tables"] += len(tables)

            # 2. Layout-based grid inference (backup signal)
            if len(page.lines) > 10 and len(page.rects) > 5:
                stats["tables"] += 1

            # -------------------------
            # IMAGE COUNT
            # -------------------------
            stats["images"] += len(page.images)

            # -------------------------
            # FLOWCHART / GRAPH INFERENCE
            # -------------------------
            # Strong layout signal
            graphic_score = (
                len(page.lines) +
                len(page.rects) +
                len(page.curves)
            )

            # Weak semantic cue (non-hardcoded)
            semantic_hint = (
                "FIG." in upper_text or
                "FIGURE" in upper_text or
                "FLOWCHART" in upper_text or
                "WORKFLOW" in upper_text
            )

            # Combined inference decision
            if graphic_score > 20 or semantic_hint:
                stats["flowcharts_or_graphs"] += 1

    return stats


if __name__ == "__main__":
    pdf_path= "sample.pdf"  # Replace with your PDF file path
    stats= analyze_pdf(pdf_path)
    print("PDF Analysis:")
    for key, value in stats.items():
        print(f"{key.capitalize()}: {value}")