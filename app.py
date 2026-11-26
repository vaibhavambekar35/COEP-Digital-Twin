import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
STORE_NAME_FILE = ROOT_DIR / "store_name.txt"
FALLBACK_ANSWER = "I don't have that information."
SYSTEM_INSTRUCTION = (
    "Answer only using the provided documents about COEP Technological University. "
    "If the answer is not in the documents, say you don't have that information. Be concise and friendly."
)
MAX_MESSAGE_LENGTH = 2000
GEMINI_REQUEST_TIMEOUT_SECONDS = 60

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    history: list[ChatMessage] = Field(default_factory=list, max_length=12)


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="COEP Digital Twin", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "https://yourwebsite.com").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def _read_store_name() -> str:
    configured_store = os.getenv("FILE_SEARCH_STORE_NAME", "").strip()
    if configured_store:
        return configured_store
    try:
        store_name = STORE_NAME_FILE.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail="The document index is not ready yet. Run `python ingest.py` first.",
        ) from exc
    if not store_name:
        raise HTTPException(
            status_code=503,
            detail="The document index is empty. Run `python ingest.py` first.",
        )
    return store_name


def _get_gemini_client() -> Any:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="The server is missing GEMINI_API_KEY. Add it to the local .env file and restart.",
        )
    from google import genai

    return genai.Client(api_key=api_key)


def _get_field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _citation_sources(interaction: Any) -> list[str]:
    # Only filenames explicitly cited by File Search count as grounding.
    sources: list[str] = []
    steps = _get_field(interaction, "steps", []) or []
    for step in steps:
        step_type = _get_field(step, "type")
        if getattr(step_type, "value", step_type) != "model_output":
            continue
        for content in _get_field(step, "content", []) or []:
            annotations = _get_field(content, "annotations", []) or []
            for annotation in annotations:
                annotation_type = _get_field(annotation, "type")
                if getattr(annotation_type, "value", annotation_type) != "file_citation":
                    continue
                file_name = _get_field(annotation, "file_name")
                if file_name and file_name not in sources:
                    sources.append(file_name)
    return sources


def _format_prompt(message: str, history: list[ChatMessage]) -> str:
    recent_history = history[-8:]
    if not recent_history:
        return message
    transcript = "\n".join(
        f"{item.role}: {item.content}" for item in recent_history
    )
    return (
        "Conversation history for context only (not evidence):\n"
        f"{transcript}\n\nCurrent user question: {message}"
    )


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(ROOT_DIR / "static" / "index.html")


@app.get("/widget.js", include_in_schema=False)
def widget_script() -> FileResponse:
    return FileResponse(
        ROOT_DIR / "static" / "widget.js",
        media_type="application/javascript",
    )


@app.get("/health")
def health() -> dict[str, str | bool]:
    configured_store = bool(os.getenv("FILE_SEARCH_STORE_NAME", "").strip())
    if not configured_store and STORE_NAME_FILE.is_file():
        configured_store = bool(STORE_NAME_FILE.read_text(encoding="utf-8").strip())
    return {
        "status": "ok",
        "configured": bool(os.getenv("GEMINI_API_KEY") and configured_store),
    }


@app.post("/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    store_name = _read_store_name()
    client = _get_gemini_client()
    prompt = _format_prompt(payload.message, payload.history)

    try:
        interaction = client.interactions.create(
            model=MODEL_NAME,
            input=prompt,
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[
                {
                    "type": "file_search",
                    "file_search_store_names": [store_name],
                }
            ],
            store=False,
            timeout=GEMINI_REQUEST_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        logger.warning("Gemini File Search request timed out")
        raise HTTPException(
            status_code=504,
            detail="Document search is taking longer than expected. Please try again.",
        ) from exc
    except Exception as exc:
        logger.exception("Gemini File Search request failed")
        raise HTTPException(
            status_code=502,
            detail="I couldn't reach the document search service. Please try again shortly.",
        ) from exc

    answer = (_get_field(interaction, "output_text", "") or "").strip()
    sources = _citation_sources(interaction)
    # A missing citation is treated as insufficient evidence, even if text was generated.
    if not answer or not sources:
        return ChatResponse(answer=FALLBACK_ANSWER, sources=[])
    return ChatResponse(answer=answer, sources=sources)


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "You're sending messages too quickly. Wait a moment and try again."},
    )