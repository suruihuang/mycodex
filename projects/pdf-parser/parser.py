import pymupdf
from pathlib import Path

input_pdf = Path("input/test.pdf")

doc = pymupdf.open(input_pdf)

# Only analyze the first page
page = doc[0]

page_dict = page.get_text("dict")

for block_number, block in enumerate(page_dict["blocks"]):

    # Skip images
    if "lines" not in block:
        continue

    print(f"\n--- BLOCK {block_number} ---")

    for line in block["lines"]:

        # Combine all spans in the same line
        line_text = "".join(
            span["text"] for span in line["spans"]
        ).strip()

        if not line_text:
            continue

        # Get basic information from the first span
        first_span = line["spans"][0]

        font_size = round(first_span["size"], 1)
        font_name = first_span["font"]
        bbox = line["bbox"]

        print(
            "LINE:", line_text,
            "| SIZE:", font_size,
            "| FONT:", font_name,
            "| BBOX:", bbox
        )

doc.close()