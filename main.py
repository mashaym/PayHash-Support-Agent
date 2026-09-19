"""
Terminal chat loop for the PayHash support agent (Milestone 1: RAG answering).

Run with: python main.py
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors

import rag_engine


def main():
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found. Add it to your .env file.")
        sys.exit(1)

    gemini_client = genai.Client(api_key=api_key)

    print("Loading embedding model (first run downloads it, later runs use the cache)...")
    embed_model = rag_engine.load_embedding_model()

    print("Opening knowledge base index...")
    collection = rag_engine.get_collection(embed_model)

    print("\nPayHash Support Agent — Milestone 5 (answer + lookup + escalate + refuse)")
    print("Type a support question, or 'quit' to exit.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not question:
            continue
        if question.lower() in {"quit", "exit"}:
            print("Goodbye.")
            break

        try:
            answer = rag_engine.answer_question(gemini_client, collection, embed_model, question)
            print(f"Agent: {answer}\n")
        except errors.ClientError as e:
            if e.code == 429:
                print("Agent: I'm being rate-limited right now — please wait a moment and try again.\n")
            else:
                print(f"Agent: There was a problem with the request ({e.code}). Please try again.\n")
        except errors.ServerError as e:
            print(f"Agent: The AI service is having issues right now ({e.code}). Please try again shortly.\n")
        except (httpx.ConnectError, httpx.TimeoutException):
            print("Agent: I couldn't reach the AI service — check your network connection and try again.\n")
        except Exception as e:
            print(f"Agent: Something unexpected went wrong: {e}\n")


if __name__ == "__main__":
    main()
