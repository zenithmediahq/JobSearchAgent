from openai import AsyncOpenAI
import streamlit as st
import os



def get_api_key(secret_name: str) -> str:
    try:
        value = st.secrets[secret_name]
        if value:
            return value
    except Exception:
        pass

    env_value = os.getenv(secret_name)
    if env_value:
        return env_value

    st.error(f"Saknar API-nyckel: {secret_name}")
    st.stop()


def get_ai_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=get_api_key("GEMINI_API_KEY"),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
