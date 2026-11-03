"""Run any workshop command, the same way on Mac, Windows and Linux. No install needed.

    python3 workshop.py <command> [arguments]          (on Windows: python workshop.py ...)

Commands:
    test           run the test suite
    walkthrough    run one stage of the search lane (files, parse, chunk, embed, search, rerank, answer)
    agent          ask the agent a question
    eval           run the golden-question eval
    my-questions   create my_questions.json from the example, to edit
    setup-box      create the workshop folders, groups and files in Box
    box-token      store a Box token in OpenShell (agent-security steps, Mac and Linux)

Put --env NAME=VALUE before the command to set a setting for that one run, for example:
    python3 workshop.py --env AKF_RERANK_MIN_LOGIT=-2.0 eval --summary
"""
from __future__ import annotations

import os
import runpy
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMANDS = {
    "walkthrough": "akf_workshop.walkthrough",
    "agent": "akf_workshop.agent.cli",
    "eval": "akf_workshop.evals.run_eval",
    "setup-box": "akf_workshop.box_source.setup_box",
    "box-token": "akf_workshop.box_source.openshell_token",
}


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(ROOT / "src"))
    while argv[:1] == ["--env"]:
        if len(argv) < 2 or "=" not in argv[1]:
            print("--env needs NAME=VALUE, for example --env AKF_RERANK_MIN_LOGIT=-2.0", file=sys.stderr)
            return 2
        name, value = argv[1].split("=", 1)
        os.environ[name] = value
        argv = argv[2:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    command, rest = argv[0], argv[1:]
    if command == "test":
        import unittest

        tests = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests"))
        result = unittest.TextTestRunner(verbosity=1).run(tests)
        return 0 if result.wasSuccessful() else 1
    if command == "my-questions":
        target = Path("my_questions.json")
        if target.exists():
            print(f"{target} already exists; edit it, or delete it to start again.")
        else:
            shutil.copyfile(ROOT / "src" / "akf_workshop" / "evals" / "my_questions.example.json", target)
            print(f"Created {target}. Open it in your editor, then run: python3 workshop.py eval --summary --golden {target}")
        return 0
    if command not in COMMANDS:
        print(f"Unknown command: {command}. Run 'python3 workshop.py help' for the list.", file=sys.stderr)
        return 2
    sys.argv = [f"workshop.py {command}", *rest]
    try:
        runpy.run_module(COMMANDS[command], run_name="__main__", alter_sys=True)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
