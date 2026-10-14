"""Settings shared by every agent: model, paths and run limits."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_DB_PATH = PROJECT_ROOT / "data" / "campus_customs.db"  # never written
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
MCP_SERVER_PATH = PROJECT_ROOT / "mcp_server" / "server.py"
# CAMPUS_CUSTOMS_AUDIT lets tests write to a scratch trail instead of the real one.
AUDIT_PATH = Path(
    os.environ.get("CAMPUS_CUSTOMS_AUDIT") or PROJECT_ROOT / "output" / "audit_trail.json"
)
PYTHON = sys.executable

# The only model any agent may use.
MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# --- Loop guards --------------------------------------------------------------
MAX_DELEGATION_DEPTH = 2  # Boss (0) -> specialist (1) -> specialist (2); no deeper
MAX_DELEGATIONS_PER_TICKET = 6  # total delegate() calls across the whole ticket
MAX_STEPS_PER_AGENT_RUN = 8  # model requests one agent may make in one run
MAX_STEPS_PER_TICKET = 30  # model requests across all agents for one ticket
MAX_TOOL_CALLS_PER_TICKET = 40
MAX_TOKENS_PER_TICKET = 250_000  # input + output tokens across all agents

TICKET_LIMITS = UsageLimits(
    request_limit=MAX_STEPS_PER_TICKET,
    tool_calls_limit=MAX_TOOL_CALLS_PER_TICKET,
    total_tokens_limit=MAX_TOKENS_PER_TICKET,
)


def build_model() -> OpenAIResponsesModel:
    """gpt-6-luna through Portkey's OpenAI-compatible endpoint (no temperature).

    Reads PORTKEY_API_KEY from the project's own .env (copy .env.example), falling
    back to the course folder's shared .env one level up. Earlier files win.
    """
    for env_file in (PROJECT_ROOT / ".env", PROJECT_ROOT.parent / ".env"):
        load_dotenv(env_file)
    client = AsyncOpenAI(
        api_key="unused-openai-key",
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-api-key": os.environ["PORTKEY_API_KEY"]},
        timeout=60.0,  # normal calls take 2-10s; fail fast on a stalled request
        max_retries=2,
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
