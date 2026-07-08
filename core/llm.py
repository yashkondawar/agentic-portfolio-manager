"""Shared LLM factory.

Single source of truth for building the chat model from environment
variables, so strategies and the UI don't each re-implement provider
selection. Supports Groq (default), Azure OpenAI and OpenAI, matching the
existing behaviour previously duplicated in ``main.py`` and ``app.py``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def get_llm(temperature: float | None = None) -> Any:
    """Return a LangChain chat model based on ``MODEL_PROVIDER``.

    Providers: ``groq`` (default), ``azure_openai``, ``openai``.
    """
    provider = os.getenv("MODEL_PROVIDER", "groq").lower()
    temp = (
        temperature
        if temperature is not None
        else float(os.getenv("MODEL_TEMPERATURE", "0.1"))
    )

    if provider == "azure_openai":
        from langchain_openai import AzureChatOpenAI

        logger.info("Using Azure OpenAI LLM")
        return AzureChatOpenAI(
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
            temperature=temp,
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        logger.info("Using OpenAI LLM")
        return ChatOpenAI(
            model=os.getenv("MODEL_NAME", "gpt-4o"),
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=temp,
        )

    from langchain_groq import ChatGroq

    logger.info("Using Groq LLM")
    return ChatGroq(
        model=os.getenv("MODEL_NAME", "llama-3.3-70b-versatile"),
        api_key=os.getenv("GROQ_API_KEY"),
    )


__all__ = ["get_llm"]
