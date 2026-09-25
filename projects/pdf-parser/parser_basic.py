import pymupdf
from pathlib import Path

# Input and output paths
input_pdf = Path("input/test.pdf")
output_md = Path("output/test.md")

# Open PDF
doc = pymupdf.open(input_pdf)

# Extract text from each page
with open(output_md, "w", encoding="utf-8") as f:
    for page_number, page in enumerate(doc, start=1):
        text = page.get_text()

        f.write(f"\n\n<!-- Page {page_number} -->\n\n")
        f.write(text)

doc.close()

print(f"Done! Markdown saved to: {output_md}")