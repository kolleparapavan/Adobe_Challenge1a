# 📄 PDF Outline Extractor (Headings and Title) using PyMuPDF + Docker

This project extracts a *document title* and a flat list of headings (H1, H2, H3) from *all PDF files in a folder* using a multi-step heuristic algorithm. It outputs the result as a structured JSON file per PDF.

---

## 🔍 What It Does

- Scans all .pdf files in the input/ folder.
- Detects:
  - *Document title* (from top-centered large text).
  - *Headings* (H1, H2, H3) using:
    - Font size & boldness
    - Text patterns (e.g., 1.1, Appendix A)
    - Filtering metadata (e.g., repeated headers/footers, long paragraphs)
- Writes the results as .json into the output/ folder.

---

## 🧠 How the Solution Works

### 1. *Font Style Analysis*
- Collects font size, font name, and bold/italic flags for all text.
- Finds the *body font style* (most frequent).
- Identifies *heading styles* as:
  - Larger than body font
  - Or bold if body is not

### 2. *Page Metadata Filtering*
- Detects repeating text in header/footer areas (e.g., page numbers, dates).
- Removes these from title/heading detection.

### 3. *Title Extraction*
- Extracts centered, top-half blocks with large fonts.
- Cleans up known OCR duplication errors (e.g., "Pr r Proposal o posal").

### 4. *Heading Detection*
- Uses style-based and prefix-based rules:
  - 1., 1.1., Appendix A, Phase II → structured levels
  - Only short, standalone lines are accepted

### 5. *Batch Processing*
- Loops through all PDF files in the input/ folder
- Saves output as JSON in the output/ folder with the same base name.

---

## 🐳 Run with Docker

### 📁 Folder Structure