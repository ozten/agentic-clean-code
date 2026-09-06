"""V08 and V12: key handling, preflight classification, no paid path in ordinary tests."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from harness import preflight
from harness.env import (KEY_VARIABLE, load_settings, parse_dotenv, redact, sandbox_environment,
                         write_dotenv_value)


class DotenvTests(unittest.TestCase):
    def test_parse_variants(self):
        text = "# comment\nexport OPEN_AI_API_KEY='sk-test-1234567890'\nHARNESS_CONCURRENCY=2 # trailing\nEMPTY=\n"
        values = parse_dotenv(text)
        self.assertEqual(values[KEY_VARIABLE], "sk-test-1234567890")
        self.assertEqual(values["HARNESS_CONCURRENCY"], "2")
        self.assertEqual(values["EMPTY"], "")

    def test_key_comes_only_from_dotenv_not_process_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("OPEN_AI_API_KEY=\n")
            settings = load_settings(path, environ={"OPENAI_API_KEY": "sk-from-shell-should-be-ignored"})
            self.assertFalse(settings.key_present)
            self.assertEqual(settings.key_fingerprint(), "absent")
            path.write_text("OPEN_AI_API_KEY=sk-real-12345678\n")
            settings = load_settings(path, environ={})
            self.assertTrue(settings.key_present)
            self.assertNotIn("sk-real", settings.key_fingerprint())

    def test_write_dotenv_value_replaces_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("OTHER=1\nOPEN_AI_API_KEY=old\n")
            write_dotenv_value(KEY_VARIABLE, "new-value", path)
            self.assertEqual(path.read_text(), "OTHER=1\nOPEN_AI_API_KEY=new-value\n")

    def test_sandbox_environment_has_no_key_and_no_inherited_variables(self):
        os.environ["OPEN_AI_API_KEY_CANARY"] = "canary"
        try:
            env = sandbox_environment(Path("/tmp/x"))
        finally:
            del os.environ["OPEN_AI_API_KEY_CANARY"]
        self.assertNotIn("OPEN_AI_API_KEY", env)
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("OPEN_AI_API_KEY_CANARY", env)
        self.assertFalse(any("KEY" in name for name in env))

    def test_redact(self):
        self.assertEqual(redact("token sk-abcdefghij here", ["sk-abcdefghij"]), "token [REDACTED] here")
        self.assertEqual(redact("short", ["abc"]), "short")


class FakeRawResponse:
    def __init__(self, status, request_id="req_1", count=3):
        class Http:
            status_code = status
            headers = {"x-request-id": request_id}
        self.http_response = Http()
        self._count = count

    def parse(self):
        class Page:
            data = [object()] * self._count
        return Page()


def factory_raising(exceptions):
    calls = []

    def factory(settings):
        class Models:
            class with_raw_response:
                @staticmethod
                def list():
                    calls.append(1)
                    step = exceptions[min(len(calls) - 1, len(exceptions) - 1)]
                    if isinstance(step, Exception):
                        raise step
                    return step

        class Client:
            models = Models()
        return Client()
    return factory, calls


class PreflightTests(unittest.TestCase):
    def settings(self, key):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(f"OPEN_AI_API_KEY={key}\n")
            return load_settings(path, environ={})

    def test_missing_key_fails_locally_without_any_request(self):
        factory, calls = factory_raising([FakeRawResponse(200)])
        result = preflight.check_openai_key(self.settings(""), client_factory=factory)
        self.assertEqual(result.kind, "missing")
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(calls, [])
        self.assertIn("missing or empty", result.escalation_message())

    def test_auth_error_escalates_without_retry(self):
        import openai
        import httpx2

        response = httpx2.Response(401, json={"error": {"message": "bad key"}}, request=httpx2.Request("GET", "https://x"))
        exc = openai.AuthenticationError("bad key", response=response, body=None)
        factory, calls = factory_raising([exc])
        result = preflight.check_openai_key(self.settings("sk-bad-key-000000"), client_factory=factory, sleep=lambda s: None)
        self.assertEqual(result.kind, "auth")
        self.assertEqual(result.exit_code, 3)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("sk-bad-key-000000", result.detail)

    def test_network_errors_retry_then_escalate_as_network(self):
        import openai
        import httpx2

        exc = openai.APIConnectionError(request=httpx2.Request("GET", "https://x"))
        factory, calls = factory_raising([exc])
        slept = []
        result = preflight.check_openai_key(self.settings("sk-some-key-000000"), backoff=(0.01, 0.02), sleep=slept.append,
                                            client_factory=factory)
        self.assertEqual(result.kind, "network")
        self.assertEqual(result.exit_code, 4)
        self.assertEqual(len(calls), 3)
        self.assertEqual(slept, [0.01, 0.02])
        self.assertIn("does not establish that the key is bad", result.escalation_message())

    def test_network_error_then_success(self):
        import openai
        import httpx2

        exc = openai.APIConnectionError(request=httpx2.Request("GET", "https://x"))
        factory, calls = factory_raising([exc, FakeRawResponse(200, "req_ok", 5)])
        result = preflight.check_openai_key(self.settings("sk-some-key-000000"), backoff=(0.01,), sleep=lambda s: None,
                                            client_factory=factory)
        self.assertTrue(result.ok)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.model_count, 5)
        self.assertEqual(result.request_id, "req_ok")

    def test_record_never_contains_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory, _ = factory_raising([FakeRawResponse(200)])
            result = preflight.check_openai_key(self.settings("sk-secret-key-0000000"), client_factory=factory)
            path = preflight.record_preflight(result, Path(tmp))
            self.assertNotIn("sk-secret", path.read_text())
            self.assertEqual(json.loads(path.read_text().splitlines()[-1])["kind"], "ok")


class NoPaidPathTests(unittest.TestCase):
    """V12: nothing in this test suite reaches the network; paid entry points require a manifest."""

    def test_cli_paid_commands_require_explicit_arguments(self):
        from harness.cli import build_parser

        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["qualify"])           # manifest is mandatory
        args = parser.parse_args(["run"])
        from harness.scheduler import execute_run

        with self.assertRaises(ValueError):
            execute_run(None, None)


if __name__ == "__main__":
    unittest.main()
