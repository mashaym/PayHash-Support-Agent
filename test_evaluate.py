"""Offline checks of the evaluator, not a replacement for live agent evaluation."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from evaluate import PacedClient, evaluate_case, main, make_report
from evaluation_cases import TEST_CASES, TestCase
import tools


def response(text=None, tool=None):
    return SimpleNamespace(text=text, function_calls=[SimpleNamespace(name=tool)] if tool else None)


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log_path = Path(self.temp.name) / "evaluation-escalations.log"
        self.brain = SimpleNamespace(
            tools=tools,
            GEMINI_MODEL_NAME="test-model",
            AVAILABLE_FUNCTIONS={
                "get_transaction_status": tools.get_transaction_status,
                "escalate_to_human": tools.escalate_to_human,
            },
        )
        self.original_functions = self.brain.AVAILABLE_FUNCTIONS
        self.original_log_path = tools.ESCALATIONS_LOG_PATH

    def client(self, responses):
        raw = Mock()
        raw.models.generate_content.side_effect = responses
        return PacedClient(raw, delay=0)

    def run_case(self, client, expected="ANSWER", action=None):
        case = TestCase("sample", "Test question", expected, "Expected policy rationale")
        if action is None:
            action = lambda client, *_args, **_kwargs: client.models.generate_content().text
        self.brain.answer_question = action
        result = evaluate_case(self.brain, client, None, None, case, self.log_path)
        self.assertIs(self.brain.AVAILABLE_FUNCTIONS, self.original_functions)
        self.assertEqual(tools.ESCALATIONS_LOG_PATH, self.original_log_path)
        return result

    def test_lookup_requires_execution_and_preserves_not_found_result(self):
        client = self.client([response(tool="get_transaction_status"), response("Not found.")])

        def action(client, *_args, **_kwargs):
            client.models.generate_content()
            self.brain.AVAILABLE_FUNCTIONS["get_transaction_status"](transaction_id="TXN999999")
            return client.models.generate_content().text

        result = self.run_case(client, "LOOKUP", action)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["tool_calls"][0]["result"]["found"])
        self.assertEqual(result["requested_tools"], ["get_transaction_status"])
        self.assertEqual(client.api_calls, 2)  # No judge call for tool routes.

    def test_real_escalation_is_isolated_and_takes_precedence_over_lookup(self):
        client = self.client([response(tool="get_transaction_status"), response(tool="escalate_to_human"), response("Handed off.")])

        def action(client, *_args, **_kwargs):
            client.models.generate_content()
            self.brain.AVAILABLE_FUNCTIONS["get_transaction_status"](transaction_id="TXN100234")
            client.models.generate_content()
            self.brain.AVAILABLE_FUNCTIONS["escalate_to_human"](summary="Test case", category="wrong_recipient_or_reversal")
            return client.models.generate_content().text

        normal_log = Path(self.temp.name) / "normal.log"
        normal_log.write_text("keep me", encoding="utf-8")
        with patch.object(tools, "ESCALATIONS_LOG_PATH", normal_log):
            self.original_log_path = normal_log
            result = self.run_case(client, "ESCALATE", action)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["tool_calls"]), 2)
        self.assertIn("Test case", self.log_path.read_text(encoding="utf-8"))
        self.assertEqual(normal_log.read_text(encoding="utf-8"), "keep me")

    def test_no_tool_verdict_is_blind_and_can_fail_expected_route(self):
        client = self.client([response("I cannot give investment advice."), response(json.dumps({"label": "REFUSE", "reason": "Declines advice."}))])
        result = self.run_case(client, expected="ANSWER")
        self.assertEqual((result["status"], result["actual"]), ("FAIL", "REFUSE"))
        judge_call = client.client.models.generate_content.call_args.kwargs
        payload = json.loads(judge_call["contents"])
        self.assertEqual(set(payload), {"question", "history", "reply"})
        self.assertNotIn("expected", payload)
        self.assertNotIn("Expected policy rationale", judge_call["contents"])
        self.assertIsNone(judge_call["config"].tools)

    def test_a_claimed_handoff_without_execution_is_not_a_tool_pass(self):
        client = self.client([response("I handed it off."), response(json.dumps({"label": "UNCLEAR", "reason": "Claims handoff without a tool."}))])
        result = self.run_case(client, expected="ESCALATE")
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["tool_calls"], [])

    def test_tool_loop_without_final_model_text_does_not_pass(self):
        client = self.client([response(tool="get_transaction_status")])

        def action(client, *_args, **_kwargs):
            client.models.generate_content()
            self.brain.AVAILABLE_FUNCTIONS["get_transaction_status"](transaction_id="TXN100235")
            return "Please rephrase."

        result = self.run_case(client, "LOOKUP", action)
        self.assertEqual((result["status"], result["actual"]), ("FAIL", "INCOMPLETE"))

    def test_api_error_after_escalation_is_error_not_pass(self):
        error = RuntimeError("SDK error")
        error.code = 429
        client = self.client([response(tool="escalate_to_human"), error])

        def action(client, *_args, **_kwargs):
            client.models.generate_content()
            self.brain.AVAILABLE_FUNCTIONS["escalate_to_human"](summary="Test", category="lost_or_stolen_card")
            return client.models.generate_content().text

        result = self.run_case(client, "ESCALATE", action)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["error_code"], 429)
        self.assertTrue(result["tool_calls"][0]["success"])

    def test_failed_tool_does_not_pass_and_wrappers_are_restored(self):
        broken = Mock(side_effect=OSError("write failed"))
        self.brain.AVAILABLE_FUNCTIONS["escalate_to_human"] = broken
        client = self.client([response(tool="escalate_to_human")])

        def action(client, *_args, **_kwargs):
            client.models.generate_content()
            self.brain.AVAILABLE_FUNCTIONS["escalate_to_human"](summary="Test", category="lost_or_stolen_card")

        result = self.run_case(client, "ESCALATE", action)
        self.assertEqual(result["status"], "ERROR")
        self.assertFalse(result["tool_calls"][0]["success"])
        self.assertIs(self.brain.AVAILABLE_FUNCTIONS["escalate_to_human"], broken)

    def test_bad_judge_output_is_error_not_guess(self):
        for verdict in ["not JSON", "null", '{"label":"LOOKUP","reason":"wrong enum"}']:
            with self.subTest(verdict=verdict):
                client = self.client([response("Some reply"), response(verdict)])
                result = self.run_case(client)
                self.assertEqual(result["status"], "ERROR")
                self.assertEqual(result["error_stage"], "judge")

    def test_report_keeps_errors_reviews_and_unrun_cases_visible(self):
        results = [
            {"id": TEST_CASES[0].id, "status": "PASS"},
            {"id": TEST_CASES[1].id, "status": "ERROR"},
            {"id": TEST_CASES[2].id, "status": "REVIEW"},
        ]
        report = make_report(TEST_CASES[:4], results, "test", 15, 6)
        self.assertEqual(report["counts"], {"PASS": 1, "FAIL": 0, "REVIEW": 1, "ERROR": 1})
        self.assertEqual(report["attempted"], 3)
        self.assertEqual(report["not_run"], [TEST_CASES[3].id])

    def test_pacing_applies_after_requests_and_counts_failures(self):
        client = self.client([response("First"), RuntimeError("failure")])
        client.delay = 15
        with patch("evaluate.time.monotonic", side_effect=[100, 105, 120]), patch("evaluate.time.sleep") as sleep:
            client.models.generate_content()
            with self.assertRaises(RuntimeError):
                client.models.generate_content()
            sleep.assert_called_once_with(10)
        self.assertEqual(client.api_calls, 2)

    def test_case_list_can_be_reviewed_offline(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--list", "--limit", "4"]), 0)
        for label in ("ANSWER", "LOOKUP", "ESCALATE", "REFUSE"):
            self.assertIn(label, output.getvalue())
        self.assertEqual(len(TEST_CASES), 18)
        self.assertEqual(len({case.id for case in TEST_CASES}), 18)


if __name__ == "__main__":
    unittest.main()
