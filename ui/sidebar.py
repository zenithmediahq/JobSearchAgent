from typing import Any

import streamlit as st


def render_sidebar() -> dict[str, Any]:
    with st.sidebar:
        st.header("Sökning")
        query = st.text_input("Jobbtitel eller sökord", value="IT support")
        location = st.text_input("Plats", value="Skåne")
        min_score = st.slider("Minsta matchning (%)", 0, 100, 40, 5)
        filter_by_score = st.checkbox(
            "Dölj jobb under min score",
            value=False,
        )

        st.markdown("---")
        st.header("Filter")
        filter_remote = st.checkbox("Endast distans / hybrid")
        filter_fulltime = st.checkbox("Endast heltid")

        st.markdown("---")
        st.header("Jobbkällor")

        source_options = {
            "Platsbanken": st.checkbox("Platsbanken", value=True),
            "Indeed": st.checkbox("Indeed", value=True),
            "LinkedIn": st.checkbox("LinkedIn", value=False),
            "JobbSafari": st.checkbox("JobbSafari", value=False),
        }

        selected_sources = [
            source for source, enabled in source_options.items()
            if enabled
        ]

    return {
        "query": query,
        "location": location,
        "min_score": min_score,
        "filter_remote": filter_remote,
        "filter_fulltime": filter_fulltime,
        "selected_sources": selected_sources,
        "filter_by_score": filter_by_score,
    }