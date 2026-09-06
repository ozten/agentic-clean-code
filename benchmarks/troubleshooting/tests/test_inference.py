"""V09 and OA03-OA06 at the transport layer, using an in-process mock transport (no network)."""
import json
import unittest

import httpx2

from harness.inference import FIXED_REQUEST_SETTINGS, InferenceError, ModelSettings, ResponsesClient, build_payload

KEY = "sk-test-key-not-real-000000"
SETTINGS = ModelSettings("test-model", "medium", "all_turns")


def usage(I=10, O=5):
    return {"input_tokens": I, "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens": O, "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": I + O}


class Recorder:
    def __init__(self, behaviour):
        self.requests = []
        self.behaviour = behaviour

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        result = self.behaviour(request)
        if isinstance(result, Exception):
            raise result
        return result


def client_with(handler):
    http = httpx2.Client(transport=httpx2.MockTransport(handler))
    return ResponsesClient(KEY, timeout=5.0, http_client=http)


class TransportTests(unittest.TestCase):
    def test_429_produces_exactly_one_post(self):
        recorder = Recorder(lambda r: httpx2.Response(429, json={"error": {"message": "slow down"}}, headers={"x-request-id": "r429"}))
        client = client_with(recorder)
        payload = build_payload(SETTINGS, "inst", [{"role": "user", "content": "hi"}], [], 100)
        with self.assertRaises(InferenceError) as raised:
            client.create(payload, 5.0, "client-1")
        self.assertEqual(raised.exception.kind, "rate_limit")
        self.assertEqual(len(recorder.requests), 1)

    def test_connection_error_produces_exactly_one_post(self):
        recorder = Recorder(lambda r: httpx2.ConnectError("refused", request=r))
        client = client_with(recorder)
        with self.assertRaises(InferenceError) as raised:
            client.create(build_payload(SETTINGS, "i", [], [], 100), 5.0, "client-2")
        self.assertEqual(raised.exception.kind, "connection")
        self.assertEqual(len(recorder.requests), 1)

    def test_timeout_produces_exactly_one_post(self):
        recorder = Recorder(lambda r: httpx2.ReadTimeout("slow", request=r))
        client = client_with(recorder)
        with self.assertRaises(InferenceError) as raised:
            client.create(build_payload(SETTINGS, "i", [], [], 100), 5.0, "client-3")
        self.assertEqual(raised.exception.kind, "timeout")
        self.assertEqual(len(recorder.requests), 1)

    def test_success_carries_fixed_settings_and_client_request_id(self):
        def ok(request):
            return httpx2.Response(200, json={"id": "resp_1", "status": "completed", "model": "test-model-2026",
                                              "service_tier": "default", "output": [], "usage": usage()},
                                   headers={"x-request-id": "server-req-9"})
        recorder = Recorder(ok)
        client = client_with(recorder)
        payload = build_payload(SETTINGS, "inst", [{"role": "user", "content": "hi"}], [{"type": "function", "name": "f",
                                                                                           "parameters": {"type": "object", "properties": {}}}], 4096)
        result = client.create(payload, 5.0, "client-abc")
        request = recorder.requests[0]
        self.assertEqual(request.url.path, "/v1/responses")
        self.assertEqual(request.headers["x-client-request-id"], "client-abc")
        self.assertEqual(request.headers["authorization"], f"Bearer {KEY}")
        body = json.loads(request.content)
        for key, value in FIXED_REQUEST_SETTINGS.items():
            self.assertEqual(body[key], value, key)
        self.assertEqual(body["reasoning"], {"effort": "medium", "context": "all_turns"})
        self.assertEqual(body["max_output_tokens"], 4096)
        self.assertEqual(body["include"], ["reasoning.encrypted_content"])
        self.assertNotIn("previous_response_id", body)
        self.assertEqual(result.request_id, "server-req-9")
        self.assertEqual(result.response_id, "resp_1")
        self.assertEqual(result.usage, usage())
        self.assertNotIn(KEY, json.dumps(result.raw))
        self.assertNotIn(KEY, json.dumps(payload))

    def test_count_input_hits_token_count_endpoint(self):
        def ok(request):
            return httpx2.Response(200, json={"object": "response.input_tokens", "input_tokens": 42})
        recorder = Recorder(ok)
        client = client_with(recorder)
        result = client.count_input(SETTINGS, "inst", [{"role": "user", "content": "x"}], [], 5.0, "count-1")
        self.assertEqual(result.input_tokens, 42)
        self.assertEqual(recorder.requests[0].url.path, "/v1/responses/input_tokens")
        self.assertEqual(recorder.requests[0].headers["x-client-request-id"], "count-1")
        body = json.loads(recorder.requests[0].content)
        self.assertEqual(body["model"], "test-model")
        self.assertEqual(body["truncation"], "disabled")

    def test_explicit_key_required(self):
        with self.assertRaises(ValueError):
            ResponsesClient("")


if __name__ == "__main__":
    unittest.main()
