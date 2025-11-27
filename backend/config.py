"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key (kept for backward compatibility, not used anymore)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Council members - list of OpenRouter model identifiers
# These will be mapped to Cursor CLI model names
# Using "max" mode models: gpt-5.1-high, opus-4.5-thinking (max variant), gemini-3-pro
COUNCIL_MODELS = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-opus-4.5",
    "x-ai/grok-4",
]

# Chairman model - synthesizes final response (using gemini-3-pro in max mode)
CHAIRMAN_MODEL = "google/gemini-3-pro-preview"

# OpenRouter API endpoint (kept for backward compatibility, not used anymore)
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Mapping from OpenRouter model identifiers to Cursor CLI model names
# Using "max" mode models: -high suffix for GPT, -thinking for Claude, direct names for others
# Verified available models: gpt-5.1-high, opus-4.5-thinking, gemini-3-pro, grok
CURSOR_MODEL_MAP = {
    "openai/gpt-5.1": "gpt-5.1-high",  # Max mode: use -high variant
    "openai/gpt-4o": "gpt-4o",  # Fallback option
    "google/gemini-3-pro-preview": "gemini-3-pro",  # Direct model name
    "google/gemini-2.5-flash": "auto",  # Fallback to auto if not available
    "anthropic/claude-sonnet-4.5": "sonnet-4.5-thinking",  # Max mode: use -thinking variant
    "anthropic/claude-opus-4.5": "opus-4.5-thinking",  # Max mode: use -thinking variant (opus-4.5-high doesn't exist)
    "anthropic/claude-opus": "opus-4.5-thinking",  # Max mode variant
    "x-ai/grok-4": "grok",  # Standard Cursor model name
}

# Data directory for conversation storage
DATA_DIR = "data/conversations"

# Temporary directory for Cursor CLI outputs
CURSOR_OUTPUT_DIR = "data/cursor_outputs"

# Workspace directory for Cursor CLI commands
# Set this to the project path you want models to have context about
# Can be set via CURSOR_WORKSPACE environment variable, or defaults to None (current directory)
CURSOR_WORKSPACE = os.getenv("CURSOR_WORKSPACE", None)
