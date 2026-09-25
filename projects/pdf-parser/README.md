# PDF Parser

A PDF parsing prototype for extracting and structuring text from research papers.

## Current Features

- PDF text extraction
- Structured block parsing
- Font size and bounding box inspection
- Basic Markdown output

## Planned Improvements

- Heading detection
- Multi-column reading order
- Header/footer removal
- Paragraph merging
- Table and image handling

## Setup

Using pip:

```bash
pip install -r requirements.txt
conda env create -f environment.yml
python parser.py
