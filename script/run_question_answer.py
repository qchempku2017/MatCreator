#!/usr/bin/env python3
"""Run MatCreator to generate and validate reference answers for benchmark questions.

Questions are taken from the question_beta_test/ directory as .tar.gz archives.
Each MatCreator instance extracts the archive, solves the task described in
question.yaml, and produces an updated question directory with revised reference
answers and rubrics.

Sessions are stored in the default MatCreator workspace so they remain accessible
from the web frontend.

Usage:
    python script/run_question_answer.py [OPTIONS]

    -q/--questions ID [ID ...]   Question IDs to run (default: all)
    -j/--jobs N                  Parallel workers (default: 1)
    --max-turns N                Max agent turns (default: 80)
    --output-dir DIR             Working file root (default: runs/gen_answers_<timestamp>)
    --timeout SECS               Per-question subprocess timeout (default: 3600)
    --list                       Print available question IDs and exit
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_QUESTIONS_DIR = _REPO_ROOT / "question_beta_test"


def _get_workspace_root() -> Path:
    env_val = os.environ.get("MATCLAW_WORKSPACE", "")
    if env_val:
        return Path(env_val).expanduser().resolve()
    return _REPO_ROOT / "agents" / "MatCreator" / ".workspace"


# ---------------------------------------------------------------------------
# Question discovery
# ---------------------------------------------------------------------------

def _list_questions() -> list[str]:
    return sorted(p.stem.removesuffix(".tar") for p in _QUESTIONS_DIR.glob("*.tar.gz"))


def _extract_question(qid: str, questions_dir: Path, dest_dir: Path) -> Path:
    archive = questions_dir / f"{qid}.tar.gz"
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(dest_dir)
    # Detect the extracted top-level directory (may differ from qid in edge cases)
    candidates = [p for p in dest_dir.iterdir() if p.is_dir()]
    if len(candidates) == 1:
        return candidates[0]
    # Fall back to qid-named directory if multiple entries exist
    named = dest_dir / qid
    if named.is_dir():
        return named
    raise RuntimeError(f"Cannot determine extracted directory for {qid} in {dest_dir}")


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(human_prompt_seed: str, data_files: list, work_dir: Path, reference_answer_prompt: str = "") -> str:
    print("reference_answer_prompt:", repr(reference_answer_prompt))
    lines = [human_prompt_seed]
    if data_files:
        upload_dir = work_dir / "uploads"
        lines += [
            "",
            "The user uploaded the following file(s) for this message."
            " They are saved in the current session workspace."
            " Use these paths when inspecting or processing the files:",
        ]
        for entry in data_files:
            filename = Path(entry["path"]).name
            abs_path = upload_dir / filename
            lines.append(f"- {filename}: uploads/{filename} (absolute path: {abs_path})")
    if reference_answer_prompt:
        lines += [
            "",
            "---",
            "## Reference Answer (consult ONLY after completing the task)",
            "",
            "Do NOT read this section before or during execution. Use it solely to"
            " verify and validate your results after the full workflow is complete.",
            "",
            reference_answer_prompt,
        ]
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Per-question worker
# ---------------------------------------------------------------------------

def _run_question(
    qid: str,
    output_dir: Path,
    max_turns: int,
    timeout: int,
    flash: bool = False,
) -> dict:
    session_id = f"{qid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Place question files directly in the session workdir so the agent's bash
    # tools (which always cwd to the session workdir) can find them with plain
    # relative paths, and the frontend can browse results at the expected location.
    work_dir = _get_workspace_root() / "sessions" / session_id
    work_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {"question_id": qid, "session_id": session_id, "exit_code": None, "duration_s": None, "error": None}
    t0 = time.monotonic()

    # Extract archive and stage files
    extract_dir = work_dir / "_extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    question_dir = _extract_question(qid, _QUESTIONS_DIR, extract_dir)

    with open(question_dir / "question.yaml", encoding="utf-8") as f:
        meta = yaml.safe_load(f)

    human_prompt_seed = meta["human_prompt_seed"]
    data_files: list = meta.get("data_files", [])
    #print(meta)
    reference_answer_prompt: str = meta.get("reference_answer_prompt", "")

    upload_dir = work_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    for entry in data_files:
        src = question_dir / entry["path"]
        if src.exists():
            shutil.copy(src, upload_dir / src.name)

    prompt_file = work_dir / "prompt.txt"
    prompt_file.write_text(_build_prompt(human_prompt_seed, data_files, work_dir, reference_answer_prompt), encoding="utf-8")

    cmd = [
        "matcreator", "run",
        "-f", str(prompt_file),
        "--session-id", session_id,
        "--max-turns", str(max_turns),
    ]
    if flash:
        cmd.append("--flash")

    try:
        proc = subprocess.run(cmd, timeout=timeout, capture_output=False)
        result["exit_code"] = proc.returncode
    except subprocess.TimeoutExpired:
        result["error"] = f"timeout after {timeout}s"
    except FileNotFoundError:
        result["error"] = "matcreator not found in PATH"

    result["duration_s"] = round(time.monotonic() - t0, 2)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_question_answer.py",
        description="Generate/validate reference answers for benchmark questions using MatCreator.",
    )
    p.add_argument(
        "-q", "--questions", nargs="+", default=None, metavar="ID",
        help="Question IDs to run (default: all); pass 'all' to run every question",
    )
    p.add_argument(
        "-j", "--jobs", type=int, default=1, metavar="N",
        help="Parallel workers (default: 1)",
    )
    p.add_argument(
        "--max-turns", type=int, default=80, metavar="N",
        help="Max MatCreator turns per question (default: 80)",
    )
    p.add_argument(
        "--output-dir", default=None, metavar="DIR",
        help="Root directory for per-question working files (default: runs/gen_answers_<timestamp>)",
    )
    p.add_argument(
        "--timeout", type=int, default=3600, metavar="SECS",
        help="Per-question subprocess timeout in seconds (default: 3600)",
    )
    p.add_argument(
        "--flash", action="store_true", default=False,
        help="Run MatCreator in Flash mode (thinking agent executes directly, no DAG).",
    )
    p.add_argument(
        "--list", action="store_true",
        help="Print available question IDs and exit",
    )
    return p


def main() -> int:
    args = _build_parser().parse_args()

    available = _list_questions()

    if args.list:
        for qid in available:
            print(qid)
        return 0

    if not available:
        print(f"error: no .tar.gz files found in {_QUESTIONS_DIR}", file=sys.stderr)
        return 1

    # Resolve question list
    if args.questions and args.questions != ["all"]:
        unknown = set(args.questions) - set(available)
        if unknown:
            print(f"error: unknown question(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            print(f"available: {', '.join(available)}", file=sys.stderr)
            return 1
        question_ids = args.questions
    else:
        question_ids = available

    # Output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        Path(args.output_dir) if args.output_dir
        else _REPO_ROOT / "runs" / f"gen_answers_{timestamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # Logging
    log_file = output_dir / "run.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )

    results_path = output_dir / "results.jsonl"

    logging.info("Output directory: %s", output_dir)
    logging.info("Running %d question(s) with %d worker(s)", len(question_ids), args.jobs)
    for qid in question_ids:
        logging.info("  [ ] %s", qid)

    ok_count = 0
    err_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {
            executor.submit(
                _run_question, qid, output_dir, args.max_turns, args.timeout, args.flash,
            ): qid
            for qid in question_ids
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            qid = result["question_id"]
            if result.get("error"):
                err_count += 1
                logging.warning("[ERR] %s  %s", qid, result["error"])
            else:
                ok_count += 1
                logging.info(
                    "[OK ] %s  session=%s  exit=%s  %.1fs",
                    qid, result["session_id"], result["exit_code"], result["duration_s"]
                )
            with open(results_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(result) + "\n")

    logging.info(
        "Completed %d/%d  (%d ok, %d errors)",
        ok_count + err_count, len(question_ids), ok_count, err_count,
    )
    logging.info("Results: %s", results_path)
    return 0 if err_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
