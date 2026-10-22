import os as _os

_os.environ.pop("BOX_FOLDER_ID", None)  # these tests use the local sample_box, never live Box

import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from akf_workshop import walkthrough

ROOT = Path(__file__).resolve().parents[1]


def run(*argv: str) -> str:
    out = io.StringIO()
    env = {key: value for key, value in os.environ.items() if key not in {"NVIDIA_API_KEY", "NVIDIA_USE_REMOTE"}}
    with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(
        sys, "argv", ["walkthrough", "--sample-box", str(ROOT / "sample_box"), *argv]
    ), contextlib.redirect_stdout(out):
        walkthrough.main()
    return out.getvalue()


class WalkthroughTest(unittest.TestCase):
    def test_every_stage_runs_offline(self):
        for step in ("files", "parse", "chunk", "embed", "search", "rerank", "answer"):
            with self.subTest(step=step):
                self.assertIn("OFFLINE", run(step))

    def test_files_hides_restricted_file_from_attendee(self):
        output = run("files")
        self.assertIn("hidden from you", output)

    def test_search_filters_by_permission(self):
        attendee = run("search")
        lead = run("--user", "support-lead@example.com", "--groups", "support-leads", "search")
        self.assertNotIn("enterprise-support-policy.md", attendee)
        self.assertIn("enterprise-support-policy.md", lead)

    def test_answer_refuses_attendee_and_answers_support_lead(self):
        question = "When should enterprise incidents be escalated?"
        self.assertIn("insufficient_context", run("answer", question))
        lead = run("--user", "support-lead@example.com", "--groups", "support-leads", "answer", question)
        self.assertIn("status:          ok", lead)


    def test_parse_boxes_map_back_to_image_pixels(self):
        # Measured on the hosted Parse 2.0 endpoint: the title of response_targets.png (900 x 560)
        # sits at x 60, y 50 and came back as (0.2646, 0.3875); at 3x size it came back scaled.
        x1, y1, _, _ = walkthrough._box_to_pixels((0.2646, 0.3875, 0.5264, 0.4055), 900, 560)
        self.assertAlmostEqual(x1, 62, delta=3)
        self.assertAlmostEqual(y1, 50, delta=3)
        # A 2700 x 1680 image is shrunk (x0.61) to fit the canvas; its title at (180, 150) maps to (0.0667, 0.2944).
        x1, y1, _, _ = walkthrough._box_to_pixels((0.0667, 0.2944, 0.5, 0.5), 2700, 1680)
        self.assertAlmostEqual(x1, 180, delta=3)
        self.assertAlmostEqual(y1, 150, delta=3)

    def test_show_requires_remote_mode(self):
        with self.assertRaises(SystemExit):
            run("parse", "--file", str(ROOT / "tests" / "fixtures" / "response_targets.png"), "--show", "/tmp/unused.png")


if __name__ == "__main__":
    unittest.main()
