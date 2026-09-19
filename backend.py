"""FastAPI interface for the existing PayHash brain.

Run: python -X utf8 -m uvicorn backend:app --host 127.0.0.1 --port 8000
"""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import errors
import httpx
from pydantic import BaseModel, Field, StringConstraints

import rag_engine

logger = logging.getLogger(__name__)
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class HistoryTurn(BaseModel):
    """One completed user question and agent answer, oldest first."""

    question: NonEmptyText
    answer: NonEmptyText


class ChatRequest(BaseModel):
    message: NonEmptyText
    history: list[HistoryTurn] = Field(
        default_factory=list,
        max_length=rag_engine.MAX_HISTORY_TURNS,
        description="Up to 10 completed exchanges, oldest first. Exclude the current message.",
    )


class ChatResponse(BaseModel):
    reply: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load shared resources once per server process, and close Gemini on exit."""
    load_dotenv(Path(__file__).with_name(".env"))
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found. Add it to your .env file.")

    gemini_client = genai.Client(api_key=api_key)
    try:
        logger.info("Loading the embedding model and opening the knowledge base...")
        embed_model = rag_engine.load_embedding_model()
        app.state.gemini_client = gemini_client
        app.state.embed_model = embed_model
        app.state.collection = rag_engine.get_collection(embed_model)
        yield  # Requests are served between startup and shutdown.
    finally:
        gemini_client.close()


app = FastAPI(title="PayHash Support API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """Translate the web request into the same call used by the terminal."""
    # History belongs to this request, never to shared app.state.
    history = [(turn.question, turn.answer) for turn in payload.history]
    try:
        reply = rag_engine.answer_question(
            request.app.state.gemini_client,
            request.app.state.collection,
            request.app.state.embed_model,
            payload.message,
            history=history,
        )
    except errors.ClientError as exc:
        if exc.code == 429:
            raise HTTPException(429, "The AI service is rate-limiting requests. Please try again shortly.") from exc
        raise HTTPException(502, "The AI service could not process this request.") from exc
    except errors.ServerError as exc:
        raise HTTPException(503, "The AI service is temporarily unavailable.") from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "The AI service took too long to respond.") from exc
    except httpx.ConnectError as exc:
        raise HTTPException(503, "Could not connect to the AI service.") from exc
    except Exception as exc:
        logger.exception("PayHash could not complete a chat request")
        raise HTTPException(500, "Something went wrong while answering. Please try again.") from exc
    return ChatResponse(reply=reply)
