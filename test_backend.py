"""Offline API checks. Run: python -m unittest test_backend -v"""

from contextlib import ExitStack
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from google.genai import errors
import httpx

import backend


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}))
        self.stack.enter_context(patch.object(backend, "load_dotenv"))
        self.gemini = self.stack.enter_context(patch.object(backend.genai, "Client"))
        self.embed = self.stack.enter_context(patch.object(backend.rag_engine, "load_embedding_model"))
        self.collection = self.stack.enter_context(patch.object(backend.rag_engine, "get_collection"))
        self.answer = self.stack.enter_context(patch.object(backend.rag_engine, "answer_question", return_value="Test reply"))
        self.client = self.stack.enter_context(TestClient(backend.app))

    def test_history_reaches_shared_brain_without_leaking_to_next_request(self):
        body = {"message": "Who received it?", "history": [
            {"question": "Check TXN100235", "answer": "It is pending."}
        ]}
        response = self.client.post("/chat", json=body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"reply": "Test reply"})
        self.answer.assert_called_once_with(
            self.gemini.return_value, self.collection.return_value,
            self.embed.return_value, "Who received it?",
            history=[("Check TXN100235", "It is pending.")],
        )
        self.client.post("/chat", json={"message": "New conversation"})
        self.assertEqual(self.answer.call_args.kwargs["history"], [])
        self.embed.assert_called_once_with()
        self.collection.assert_called_once_with(self.embed.return_value)
        self.gemini.assert_called_once_with(api_key="test-key")
        self.stack.close()
        self.gemini.return_value.close.assert_called_once_with()

    def test_invalid_input_is_rejected_before_calling_brain(self):
        for body in [
            {}, {"message": "   "}, {"message": 123},
            {"message": "Hello", "history": [{"question": "Missing answer"}]},
            {"message": "Hello", "history": [{"question": "Q", "answer": "A"}] * 11},
        ]:
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/chat", json=body).status_code, 422)
        self.answer.assert_not_called()

    def test_ten_complete_exchanges_are_accepted(self):
        history = [{"question": str(i), "answer": "A"} for i in range(10)]
        response = self.client.post("/chat", json={"message": "Next", "history": history})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.answer.call_args.kwargs["history"], [(str(i), "A") for i in range(10)])

    def test_cors_preflight_and_error_response(self):
        for origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
            headers = {"Origin": origin, "Access-Control-Request-Method": "POST",
                       "Access-Control-Request-Headers": "Content-Type"}
            response = self.client.options("/chat", headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["access-control-allow-origin"], origin)
        headers["Origin"] = "http://unlisted.example"
        response = self.client.options("/chat", headers=headers)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access-control-allow-origin", response.headers)
        response = self.client.post("/chat", json={"message": ""}, headers={"Origin": "http://localhost:5173"})
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")

    def test_service_errors_become_useful_http_errors(self):
        cases = [
            (errors.ClientError(429, {}), 429),
            (errors.ClientError(400, {}), 502),
            (errors.ServerError(503, {}), 503),
            (httpx.ConnectError("connection failed"), 503),
            (httpx.ReadTimeout("timed out"), 504),
            (RuntimeError("private debug details"), 500),
        ]
        for error, status in cases:
            with self.subTest(status=status), patch.object(backend.logger, "exception"):
                self.answer.side_effect = error
                response = self.client.post("/chat", json={"message": "Hello"}, headers={"Origin": "http://localhost:5173"})
                self.assertEqual(response.status_code, status)
                self.assertIsInstance(response.json()["detail"], str)
                self.assertNotIn("private debug details", response.text)
                self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")
        self.answer.side_effect = None
        self.assertEqual(self.client.post("/chat", json={"message": "Hello"}).status_code, 200)

    def test_docs_are_available(self):
        self.assertEqual(self.client.get("/docs").status_code, 200)
        schema = self.client.get("/openapi.json").json()
        self.assertIn("post", schema["paths"]["/chat"])


if __name__ == "__main__":
    unittest.main()
