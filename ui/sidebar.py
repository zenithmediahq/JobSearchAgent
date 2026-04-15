import streamlit as st


def render_sidebar() -> tuple[str, str, int, bool, bool, list[str]]:
    with st.sidebar:
        st.header("Sökning")
        query = st.text_input("Jobbtitel eller sökord", value="IT support")
        location = st.text_input("Plats", value="Skåne")
        min_score = st.slider("Minsta matchning (%)", 0, 100, 40, 5)

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

    return (
        query,
        location,
        min_score,
        filter_remote,
        filter_fulltime,
        selected_sources,
    )