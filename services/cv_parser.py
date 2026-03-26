from io import BytesIO
import fitz
from docx import Document


def extract_text_from_upload(uploaded_file) -> str:
    """Extraherar text från PDF, DOCX eller TXT-filer."""
    file_bytes = uploaded_file.read()
    filename = uploaded_file.name.lower()

    if filename.endswith(".pdf"):
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        return "\n".join(page.get_text() for page in doc).strip()

    if filename.endswith(".docx"):
        doc = Document(BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    return file_bytes.decode("utf-8", errors="replace")
