import streamlit as st

from services.cv_parser import extract_text_from_upload


def render_profile_input() -> str:
    st.subheader("Din profil")

    uploaded_file = st.file_uploader(
        "Ladda upp CV (PDF, DOCX eller TXT)",
        type=["pdf", "docx", "txt"],
    )

    cv_text_input = st.text_area(
        "Eller klistra in CV-text manuellt",
        height=140,
        placeholder="Klistra in din CV-text här...",
    )

    final_cv_text = ""

    if uploaded_file is not None:
        final_cv_text = extract_text_from_upload(uploaded_file)
        st.success(f"Filen '{uploaded_file.name}' är inläst.")
    elif cv_text_input.strip():
        final_cv_text = cv_text_input.strip()

    return final_cv_text