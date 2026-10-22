from __future__ import annotations

import base64
import os
import unittest
from unittest.mock import patch

from akf_workshop import nvidia_clients

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


class ParseClientTests(unittest.TestCase):
    def setUp(self) -> None:
        patch.dict(os.environ, {"NVIDIA_USE_REMOTE": "0"}).start()
        self.addCleanup(patch.stopall)

    def test_parse2_body_shape(self) -> None:
        seen = {}

        def fake(url, payload):
            seen.update(payload)
            return {"choices": [{"message": {"content": "<x_0.1><y_0.1>Hi<x_0.2><y_0.2><class_Text>"}, "finish_reason": "stop"}]}

        with patch.object(nvidia_clients, "_post_json", fake):
            raw = nvidia_clients.parse_image_remote(PNG, mime="image/png")
        self.assertEqual(seen["model"], "nvidia/nemotron-parse-2.0")
        parts = seen["messages"][0]["content"]
        self.assertEqual(parts[0], {"type": "text", "text": nvidia_clients.PARSE2_PROMPT})
        self.assertTrue(parts[1]["image_url"]["url"].startswith("data:image/png;base64," + base64.b64encode(PNG).decode()[:8]))
        self.assertEqual(seen["max_tokens"], 2000)
        self.assertIn("<class_Text>", raw)

    def test_parse_v1_body_shape_and_arguments(self) -> None:
        seen = {}

        def fake(url, payload):
            seen.update(payload)
            return {"choices": [{"message": {"content": None, "tool_calls": [{"function": {"name": "markdown_bbox", "arguments": "[[{\"text\": \"x\"}]]"}}]}}]}

        with patch.object(nvidia_clients, "_post_json", fake):
            raw = nvidia_clients.parse_image_remote_v1(PNG, mime="image/png")
        self.assertEqual(seen["model"], "nvidia/nemotron-parse")
        self.assertEqual(seen["tools"], [{"type": "function", "function": {"name": "markdown_bbox"}}])
        self.assertEqual(seen["messages"][0]["content"][0]["type"], "image_url")
        self.assertEqual(raw, "[[{\"text\": \"x\"}]]")

    def test_parse_v1_without_tool_call_returns_empty(self) -> None:
        with patch.object(nvidia_clients, "_post_json", lambda u, p: {"choices": [{"message": {"content": "", "tool_calls": None}}]}):
            self.assertEqual(nvidia_clients.parse_image_remote_v1(PNG), "")


if __name__ == "__main__":
    unittest.main()
