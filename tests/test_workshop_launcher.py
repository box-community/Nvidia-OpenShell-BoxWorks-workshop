import os as _os

_os.environ.pop("BOX_FOLDER_ID", None)  # these tests use the local sample_box, never live Box

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import workshop  # noqa: E402


class LauncherTest(unittest.TestCase):
    def run_launcher(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = workshop.main(list(argv))
        return code, out.getvalue()

    def test_help_and_unknown_command(self):
        self.assertEqual(self.run_launcher("help")[0], 0)
        self.assertEqual(self.run_launcher("nope")[0], 2)

    def test_env_sets_a_setting_for_the_run(self):
        with mock.patch.dict(os.environ, {}, clear=False), mock.patch("runpy.run_module") as run_module:
            code, _ = self.run_launcher("--env", "AKF_RERANK_MIN_LOGIT=-2.0", "eval", "--summary")
            self.assertEqual(os.environ["AKF_RERANK_MIN_LOGIT"], "-2.0")
        self.assertEqual(code, 0)
        self.assertEqual(run_module.call_args.args[0], "akf_workshop.evals.run_eval")
        self.assertEqual(sys.argv[1:], ["--summary"])

    def test_env_needs_name_and_value(self):
        self.assertEqual(self.run_launcher("--env", "NOVALUE", "eval")[0], 2)

    def test_my_questions_copies_the_example_once(self):
        with tempfile.TemporaryDirectory() as folder:
            cwd = os.getcwd()
            os.chdir(folder)
            try:
                self.run_launcher("my-questions")
                self.assertTrue(Path("my_questions.json").exists())
                Path("my_questions.json").write_text("[]")
                self.run_launcher("my-questions")
                self.assertEqual(Path("my_questions.json").read_text(), "[]")
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
