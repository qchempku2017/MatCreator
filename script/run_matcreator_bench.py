#!/usr/bin/env python3
"""Non-interactive end-to-end benchmark runner for the MatCreator agent.

Prerequisites:
    mat-bench-client setup --server http://<host>:<port> --token <TOKEN>

Usage:
    python agents/run_matcreator_bench.py [OPTIONS]

    --server URL        Bare server URL (default: saved config / $MAT_BENCH_SERVER_URL)
    --questions ID,...  Comma-separated question IDs (default: all)
    --capability CAP    Filter by capability
    --domain DOMAIN     Filter by domain
    --limit N           Max questions to run
    -j/--jobs N         Parallel workers (default: 1)
    --timeout SECS      Per-question subprocess timeout (default: 600)
    --max-turns N       Max matcreator turns (default: 50)
    --output-dir DIR    Output root (default: runs/matcreator_<timestamp>)
    --log-file FILE     Write log output to this file in addition to stderr
    --no-progress       Suppress tqdm progress bar

The matcreator agent is responsible for its own answer submission; this script
only handles session creation, question fetching (which records the start time
on the server), and subprocess orchestration.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import random
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Import mat_bench_client API — installed package or fallback to repo path
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    from mat_bench_client.cli import (
        _api,
        _load_config,
        _resolve_server,
        api_create_session,
        api_list_questions,
        api_get_question,
        api_download_data,
        api_get_evaluated_question_ids,
    )
except ImportError:
    sys.path.insert(0, str(_REPO_ROOT / 'mat_bench_client'))
    from mat_bench_client.cli import (  # type: ignore[no-redef]
        _api,
        _load_config,
        _resolve_server,
        api_create_session,
        api_list_questions,
        api_get_question,
        api_download_data,
        api_get_evaluated_question_ids,
    )


# ---------------------------------------------------------------------------
# Credentials helper
# ---------------------------------------------------------------------------

def _get_token() -> str:
    token = os.environ.get('MAT_BENCH_TOKEN') or _load_config().get('token')
    if not token:
        print(
            'error: no token found.\n'
            'Run: mat-bench-client setup --server <URL> --token <TOKEN>\n'
            'Or:  export MAT_BENCH_TOKEN=<TOKEN>',
            file=sys.stderr,
        )
        sys.exit(1)
    return token


# ---------------------------------------------------------------------------
# Per-question worker
# ---------------------------------------------------------------------------

def _run_question(
    qid: str,
    api_base: str,
    token: str,
    session_id: str,
    output_dir: Path,
    max_turns: int,
    timeout: int,
    model_name: str,
    flash: bool = False,
) -> dict:
    mat_session_id = f"{qid}_{session_id}_{random.randint(1000, 9999)}"

    workspace = output_dir / qid
    workspace.mkdir(parents=True, exist_ok=True)

    result: dict = {'question_id': qid, 'session_id': mat_session_id, 'exit_code': None, 'duration_s': None, 'error': None}
    t0 = time.monotonic()

    # Fetch question text and record start time on the server
    question = api_get_question(api_base, token, qid, session_id)
    print(question)  # for debugging
    question_text = question.get('prompt', '')

    # Download data files directly into the workspace
    data_paths: list[Path] = []
    for f in question.get('data_files', []):
        fname = f.get('filename') or f.get('key', '')
        if fname:
            dest = workspace / fname
            api_download_data(api_base, token, qid, fname, dest)
            data_paths.append(dest)

    data_section = ''
    if data_paths:
        lines = '\n'.join(f'  {p}' for p in data_paths)
        data_section = f'\n\nData files (already downloaded):\n{lines}'

    prompt = (
        f"{question_text}"
        f"{data_section}"
        f"\n\nWhen done, submit using:\n"
        f"```bash\n"
        f"mat-bench-client submit {qid} \\\n"
        f"  --answer \"<brief final answer>\" \\\n"
        f"  --model \"{model_name}\" \\\n"
        f"  --turns <number-of-agent-turns> \\\n"
        f"  --files <output_file1> <output_file2> ...\n"
        f"```\n"
        f"Each question can be submitted **once per session**."
    )
    prompt_file = workspace / 'prompt.txt'
    prompt_file.write_text(prompt, encoding='utf-8')

    cmd = [
        'matcreator', 'run',
        '-f', str(prompt_file),
        '--session-id', mat_session_id,
        '--max-turns', str(max_turns),
    ]
    if flash:
        cmd.append('--flash')

    try:
        proc = subprocess.run(
            cmd,
            timeout=timeout,
            capture_output=False,
            env={**os.environ, 'MAT_BENCH_SESSION_ID': session_id},
        )
        result['exit_code'] = proc.returncode
    except subprocess.TimeoutExpired:
        result['error'] = f'timeout after {timeout}s'
    except FileNotFoundError:
        result['error'] = 'matcreator not found in PATH'

    result['duration_s'] = round(time.monotonic() - t0, 2)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='run_matcreator_bench.py',
        description='End-to-end benchmark runner for the MatCreator agent.',
    )
    p.add_argument('--server', default=None, metavar='URL',
                   help='Bare server URL (default: saved config / $MAT_BENCH_SERVER_URL)')
    p.add_argument('--questions', default=None, metavar='ID,...',
                   help='Comma-separated question IDs to run (default: all)')
    p.add_argument('--capability', default=None)
    p.add_argument('--domain', default=None)
    p.add_argument('--limit', type=int, default=None, metavar='N')
    p.add_argument('-j', '--jobs', type=int, default=1, metavar='N',
                   help='Parallel workers (default: 1)')
    p.add_argument('--timeout', type=int, default=600, metavar='SECS',
                   help='Per-question subprocess timeout in seconds (default: 600)')
    p.add_argument('--max-turns', type=int, default=50, metavar='N',
                   help='Max matcreator turns (default: 50)')
    p.add_argument('--output-dir', default=None, metavar='DIR',
                   help='Output directory (default: runs/matcreator_<timestamp>)')
    p.add_argument('--log-file', default=None, metavar='FILE',
                   help='Write log output to this file (default: <output-dir>/run.log)')
    p.add_argument('--no-progress', action='store_true',
                   help='Suppress tqdm progress bar')
    p.add_argument('--model', default='matcreator', metavar='NAME',
                   help='Model/agent name reported in submission (default: matcreator)')
    p.add_argument('--flash', action='store_true', default=False,
                   help='Run MatCreator in Flash mode (thinking agent executes directly, no DAG).')
    p.add_argument('--reuse-session', action='store_true', default=False,
                   help='Reuse the session_id stored in ~/.mat-bench-client/config.yaml instead of creating a new one.')
    p.add_argument('--session-id', default=None, metavar='SESSION_ID',
                   help='Explicit session ID to reuse (implies --reuse-session; overrides config value).')
    return p


def main() -> int:
    args = _build_parser().parse_args()

    # Output directory (needed before logging so we can place the default log file)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = Path(args.output_dir) if args.output_dir else (
        _REPO_ROOT / 'runs' / f'matcreator_{timestamp}'
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # Logging setup — default log file lives inside output_dir
    log_file = Path(args.log_file) if args.log_file else output_dir / 'run.log'
    log_handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(log_file, encoding='utf-8'),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        datefmt='%H:%M:%S',
        handlers=log_handlers,
    )

    # Credentials + server
    token = _get_token()
    server = _resolve_server(args.server)
    api_base = _api(server)

    # Create or reuse session
    if args.session_id or args.reuse_session:
        if args.session_id:
            session_id = args.session_id
        else:
            session_id = _load_config().get('session_id')
        if not session_id:
            logging.error('No session_id found in ~/.mat-bench-client/config.yaml. Run: mat-bench-client setup')
            return 1
        logging.info('Reusing session: %s', session_id)
    else:
        logging.info('Creating new session on %s ...', api_base)
        session_id = api_create_session(api_base, token, args.model)
        logging.info('Session: %s', session_id)
    (output_dir / 'session_id.txt').write_text(session_id, encoding='utf-8')

    log_path = output_dir / 'run_log.jsonl'

    # Resolve question list
    if args.questions:
        question_ids = [q.strip() for q in args.questions.split(',') if q.strip()]
    else:
        logging.info('Listing questions ...')
        questions = api_list_questions(
            api_base, token,
            capability=args.capability,
            domain=args.domain,
            limit=args.limit,
        )
        question_ids = [q['id'] for q in questions]
        if args.limit:
            question_ids = question_ids[:args.limit]

    if not question_ids:
        logging.error('No questions to run.')
        return 1

    # When reusing a session, skip questions that have already been evaluated
    if args.session_id or args.reuse_session:
        evaluated_ids = api_get_evaluated_question_ids(api_base, token, session_id)
        if evaluated_ids:
            original_count = len(question_ids)
            question_ids = [qid for qid in question_ids if qid not in evaluated_ids]
            skipped = original_count - len(question_ids)
            if skipped:
                logging.info('Skipping %d already-evaluated question(s); %d remaining.', skipped, len(question_ids))
        if not question_ids:
            logging.info('All questions already evaluated. Nothing to do.')
            return 0

    logging.info('Running %d question(s) with %d worker(s)', len(question_ids), args.jobs)
    for qid in question_ids:
        logging.info('  [ ] %s', qid)

    # Optional tqdm progress bar
    use_tqdm = not args.no_progress
    if use_tqdm:
        try:
            from tqdm import tqdm  # type: ignore[import]
        except ImportError:
            use_tqdm = False

    ok_count = 0
    err_count = 0

    if use_tqdm:
        bar = tqdm(total=len(question_ids), desc='Questions', file=sys.stderr, unit='q')  # type: ignore[possibly-undefined]
    else:
        bar = None

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {
            executor.submit(
                _run_question,
                qid, api_base, token, session_id,
                output_dir, args.max_turns, args.timeout, args.model, args.flash,
            ): qid
            for qid in question_ids
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            qid = result['question_id']
            if result.get('error'):
                err_count += 1
                logging.warning('[ERR] %s  %s', qid, result['error'])
            else:
                ok_count += 1
                logging.info('[OK ] %s  session=%s  exit=%s  %.1fs', qid, result['session_id'], result['exit_code'], result['duration_s'])
            with open(log_path, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps(result) + '\n')
            if bar is not None:
                bar.update(1)

    if bar is not None:
        bar.close()

    logging.info(
        'Completed %d/%d  (%d ok, %d errors)',
        ok_count + err_count, len(question_ids), ok_count, err_count,
    )
    logging.info('Session: %s', session_id)
    logging.info('Log: %s', log_path)

    return 0 if err_count == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
