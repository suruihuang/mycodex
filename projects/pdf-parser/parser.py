import re
import pymupdf
from pathlib import Path

INPUT_PDF = Path("input/test.pdf")
OUTPUT_MD = Path("output/result.md")

doc = pymupdf.open(INPUT_PDF)

page = doc[0]
page_dict = page.get_text("dict")

page_height = page.rect.height
page_width = page.rect.width


def classify_line(text, font_size, font_name, bbox):
    text = text.strip()
    y0 = bbox[1]

    # Header
    if y0 < page_height * 0.06:
        return "HEADER"

    # Footer
    if y0 > page_height * 0.92:
        return "FOOTER"

    # Large drop cap
    if len(text) == 1 and font_size >= 20:
        return "DROP_CAP"

    # Main title
    if font_size >= 20:
        return "TITLE"

    # Author area
    if 10.5 <= font_size <= 11.5 and y0 < page_height * 0.25:
        return "AUTHOR"

    # IEEE-style section heading
    if re.match(r"^[IVXLC]+\.\s+[A-Z][A-Z\s\-]+$", text):
        return "HEADING"

    # Footnote
    if font_size < 7.0:
        return "FOOTNOTE"

    # Publication metadata
    if font_size <= 8.0:
        return "METADATA"

    return "BODY"


# -------------------------------------------------
# Step 1: collect text fragments
# -------------------------------------------------

items = []

for block in page_dict["blocks"]:

    if "lines" not in block:
        continue

    for line in block["lines"]:

        text = "".join(
            span["text"] for span in line["spans"]
        ).strip()

        if not text:
            continue

        first_span = line["spans"][0]

        font_size = round(first_span["size"], 1)
        font_name = first_span["font"]
        bbox = list(line["bbox"])

        line_type = classify_line(
            text,
            font_size,
            font_name,
            bbox
        )

        items.append({
            "text": text,
            "type": line_type,
            "size": font_size,
            "font": font_name,
            "bbox": bbox
        })


# -------------------------------------------------
# Step 2: merge nearby fragments on same visual row
# -------------------------------------------------

items.sort(
    key=lambda x: (
        round(x["bbox"][1], 1),
        x["bbox"][0]
    )
)

merged = []

Y_TOLERANCE = 1.5
X_GAP_TOLERANCE = 12.0

for item in items:

    if not merged:
        merged.append(item.copy())
        continue

    last = merged[-1]

    same_row = abs(
        item["bbox"][1] - last["bbox"][1]
    ) <= Y_TOLERANCE

    horizontal_gap = item["bbox"][0] - last["bbox"][2]

    close_enough = -2.0 <= horizontal_gap <= X_GAP_TOLERANCE

    if same_row and close_enough:

        if (
            last["text"]
            and not last["text"].endswith("-")
            and not item["text"].startswith((",", ".", ";", ":", ")"))
        ):
            last["text"] += " "

        last["text"] += item["text"]

        last["bbox"][2] = max(
            last["bbox"][2],
            item["bbox"][2]
        )

        last["bbox"][3] = max(
            last["bbox"][3],
            item["bbox"][3]
        )

    else:
        merged.append(item.copy())


# -------------------------------------------------
# Step 3: merge drop cap with following body text
# -------------------------------------------------

final_lines = []
i = 0

while i < len(merged):

    current = merged[i]

    if (
        current["type"] == "DROP_CAP"
        and i + 1 < len(merged)
        and merged[i + 1]["type"] == "BODY"
    ):
        next_item = merged[i + 1]

        merged_text = current["text"] + next_item["text"]

        final_lines.append({
            "text": merged_text,
            "type": "BODY",
            "size": next_item["size"],
            "bbox": next_item["bbox"]
        })

        i += 2
        continue

    final_lines.append(current)
    i += 1


# -------------------------------------------------
# Step 4: build Markdown
# -------------------------------------------------

title_parts = []
author_parts = []
body_lines = []

for item in final_lines:

    line_type = item["type"]
    text = item["text"].strip()

    if line_type in {"HEADER", "FOOTER", "METADATA"}:
        continue

    if line_type == "TITLE":
        title_parts.append(text)

    elif line_type == "AUTHOR":
        author_parts.append(text)

    elif line_type == "HEADING":
        body_lines.append("")
        body_lines.append(f"## {text}")
        body_lines.append("")

    elif line_type == "FOOTNOTE":
        body_lines.append("")
        body_lines.append(f"> {text}")
        body_lines.append("")

    elif line_type == "BODY":
        body_lines.append(text)


# -------------------------------------------------
# Step 5: clean title and authors
# -------------------------------------------------

title = " ".join(title_parts)

authors = " ".join(author_parts)
authors = re.sub(r"\s+", " ", authors).strip()


# -------------------------------------------------
# Step 6: basic paragraph merging
# -------------------------------------------------

paragraphs = []
buffer = ""

for line in body_lines:

    if not line:
        if buffer:
            paragraphs.append(buffer.strip())
            buffer = ""
        paragraphs.append("")
        continue

    if line.startswith("## ") or line.startswith("> "):
        if buffer:
            paragraphs.append(buffer.strip())
            buffer = ""
        paragraphs.append(line)
        continue

    if buffer:
        if buffer.endswith("-"):
            buffer = buffer[:-1] + line
        else:
            buffer += " " + line
    else:
        buffer = line

if buffer:
    paragraphs.append(buffer.strip())


# -------------------------------------------------
# Step 7: write Markdown
# -------------------------------------------------

OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)

with OUTPUT_MD.open("w", encoding="utf-8") as f:

    if title:
        f.write(f"# {title}\n\n")

    if authors:
        f.write(f"{authors}\n\n")

    for paragraph in paragraphs:

        if paragraph == "":
            f.write("\n")
        else:
            f.write(paragraph + "\n\n")


doc.close()

print(f"Markdown saved to: {OUTPUT_MD}")