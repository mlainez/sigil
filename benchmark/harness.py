#!/usr/bin/env python3
"""Sigil Benchmark Harness — measures correctness and token consumption across languages and models."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SIGIL_BIN = REPO_ROOT / "interpreter" / "_build" / "default" / "vm.exe"
TASKS_DIR = Path(__file__).resolve().parent / "tasks"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

LANGUAGES = ["sigil", "python", "javascript", "go"]
MAX_RETRIES = 5
EXEC_TIMEOUT = 10  # seconds

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Attempt:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    thinking_tokens: int = 0
    code: str = ""
    parse_ok: bool = False
    test_results: list = field(default_factory=list)
    error: str = ""

@dataclass
class RunResult:
    task_id: str = ""
    language: str = ""
    model: str = ""
    run_index: int = 0
    attempts: list = field(default_factory=list)
    first_attempt_correct: bool = False
    final_correct: bool = False
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_thinking_tokens: int = 0
    total_tokens: int = 0
    attempts_to_correct: int = 0
    wall_time_s: float = 0.0


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

def load_sigil_system_prompt() -> str:
    grammar = (REPO_ROOT / ".sigil.grammar").read_text()
    return (
        "You are a Sigil code generator. Sigil is an S-expression language for AI.\n"
        "Here is the complete language grammar and reference:\n\n"
        f"{grammar}\n\n"
        "Generate ONLY a complete Sigil program as a (module ...) with a (fn main -> int ...) entry point.\n"
        "The program receives input via (argv) — command-line arguments after the filename.\n"
        "Print output to stdout with (print ...) or (println ...).\n"
        "Return 0 from main on success.\n"
        "Output ONLY the code inside a ```sigil code block. No explanations."
    )


def load_python_system_prompt() -> str:
    return (
        "You are a Python code generator.\n"
        "Generate ONLY a complete Python program.\n"
        "The program receives input via sys.argv[1], sys.argv[2], etc.\n"
        "Print output to stdout.\n"
        "Output ONLY the code inside a ```python code block. No explanations."
    )


def load_javascript_system_prompt() -> str:
    return (
        "You are a JavaScript code generator.\n"
        "Generate ONLY a complete Node.js program.\n"
        "The program receives input via process.argv[2], process.argv[3], etc.\n"
        "Print output to stdout using console.log() or process.stdout.write().\n"
        "Output ONLY the code inside a ```javascript code block. No explanations."
    )


def load_go_system_prompt() -> str:
    return (
        "You are a Go code generator.\n"
        "Generate ONLY a complete Go program with package main and func main().\n"
        "The program receives input via os.Args[1], os.Args[2], etc.\n"
        "Print output to stdout using fmt.Print/fmt.Println.\n"
        "Output ONLY the code inside a ```go code block. No explanations."
    )


def load_sigil_finetuned_prompt() -> str:
    """Minimal prompt for a model that was fine-tuned on Sigil — no grammar needed."""
    return (
        "Generate a Sigil program as a (module ...) with (fn main -> int ...).\n"
        "Input via (argv). Output via (print)/(println). Return 0.\n"
        "Output ONLY code in a ```sigil block."
    )


SYSTEM_PROMPTS = {
    "sigil": load_sigil_system_prompt,
    "sigil_finetuned": load_sigil_finetuned_prompt,
    "python": load_python_system_prompt,
    "javascript": load_javascript_system_prompt,
    "go": load_go_system_prompt,
}

# ---------------------------------------------------------------------------
# Model backends
# ---------------------------------------------------------------------------

def call_anthropic(model: str, system: str, messages: list) -> dict:
    """Call Anthropic API. Returns {content, prompt_tokens, completion_tokens, thinking_tokens}."""
    import anthropic
    client = anthropic.Anthropic()

    resp = client.messages.create(
        model=model,
        max_tokens=8192,
        system=system,
        messages=messages,
    )
    content = ""
    for block in resp.content:
        if block.type == "text":
            content += block.text

    thinking = 0
    if hasattr(resp.usage, "cache_read_input_tokens"):
        pass  # just standard usage
    return {
        "content": content,
        "prompt_tokens": resp.usage.input_tokens,
        "completion_tokens": resp.usage.output_tokens,
        "thinking_tokens": thinking,
    }


def call_claude_cli(model: str, system: str, messages: list) -> dict:
    """Call Claude Code CLI. Returns same shape as anthropic API."""
    # Build the prompt: system context + conversation
    prompt_parts = [system, ""]
    for msg in messages:
        if msg["role"] == "user":
            prompt_parts.append(msg["content"])
        elif msg["role"] == "assistant":
            prompt_parts.append(f"[Previous response]\n{msg['content']}")
    prompt = "\n\n".join(prompt_parts)

    try:
        result = subprocess.run(
            ["claude", "--print", "--model", model, "--output-format", "json", "-p", prompt],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return {
                "content": result.stdout or result.stderr,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "thinking_tokens": 0,
            }
        try:
            data = json.loads(result.stdout)
            content = data.get("result", result.stdout)
            usage = data.get("usage", {})
            # Real token counts from Claude CLI JSON
            input_tok = usage.get("input_tokens", 0)
            cache_create = usage.get("cache_creation_input_tokens", 0)
            cache_read = usage.get("cache_read_input_tokens", 0)
            output_tok = usage.get("output_tokens", 0)
            return {
                "content": content,
                "prompt_tokens": input_tok + cache_create + cache_read,
                "completion_tokens": output_tok,
                "thinking_tokens": 0,
            }
        except (json.JSONDecodeError, KeyError):
            return {
                "content": result.stdout,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "thinking_tokens": 0,
            }
    except FileNotFoundError:
        return {"content": "", "prompt_tokens": 0, "completion_tokens": 0,
                "thinking_tokens": 0}
    except subprocess.TimeoutExpired:
        return {"content": "", "prompt_tokens": 0, "completion_tokens": 0,
                "thinking_tokens": 0}


def call_openai_compat(base_url: str, model: str, system: str, messages: list, api_key: str = "not-needed") -> dict:
    """Call OpenAI-compatible API (LMStudio, Ollama, vLLM, Together.ai). Returns same shape as anthropic."""
    import openai
    client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=300.0)

    full_messages = [{"role": "system", "content": system}] + messages
    resp = client.chat.completions.create(
        model=model,
        messages=full_messages,
        max_tokens=8192,
        temperature=0.2,
    )
    choice = resp.choices[0]
    usage = resp.usage
    return {
        "content": choice.message.content or "",
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "thinking_tokens": 0,
    }


# ---------------------------------------------------------------------------
# Code extraction
# ---------------------------------------------------------------------------

def extract_code(response: str, language: str) -> str:
    """Extract code from a markdown code block in the response."""
    lang_tags = {
        "sigil": ["sigil", "lisp", "scheme"],
        "python": ["python", "py"],
        "javascript": ["javascript", "js"],
        "go": ["go", "golang"],
    }
    tags = lang_tags.get(language, [language])

    # Try language-specific fences first
    for tag in tags:
        marker = f"```{tag}"
        if marker in response:
            start = response.index(marker) + len(marker)
            nl_pos = response.find("\n", start)
            if nl_pos == -1:
                continue
            end = response.find("```", nl_pos)
            if end == -1:
                return response[nl_pos + 1:].strip()
            return response[nl_pos + 1:end].strip()

    # Fallback: any code fence
    if "```" in response:
        first = response.index("```")
        nl_pos = response.find("\n", first)
        if nl_pos == -1:
            return response.strip()
        rest = response[nl_pos + 1:]
        if "```" in rest:
            end = rest.index("```")
            return rest[:end].strip()
        return rest.strip()

    # No fence — return the whole thing
    return response.strip()


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def execute_sigil(code: str, args: list) -> tuple[bool, str, str]:
    """Write code to temp file, run with sigil interpreter. Returns (success, stdout, stderr)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sigil", delete=False) as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(
                [str(SIGIL_BIN), f.name] + args,
                capture_output=True, text=True, timeout=EXEC_TIMEOUT,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "TIMEOUT"
        finally:
            os.unlink(f.name)


def execute_python(code: str, args: list) -> tuple[bool, str, str]:
    """Write code to temp file, run with python3. Returns (success, stdout, stderr)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(
                [sys.executable, f.name] + args,
                capture_output=True, text=True, timeout=EXEC_TIMEOUT,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "TIMEOUT"
        finally:
            os.unlink(f.name)


def execute_javascript(code: str, args: list) -> tuple[bool, str, str]:
    """Write code to temp file, run with node. Returns (success, stdout, stderr)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(
                ["node", f.name] + args,
                capture_output=True, text=True, timeout=EXEC_TIMEOUT,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "TIMEOUT"
        finally:
            os.unlink(f.name)


def execute_go(code: str, args: list) -> tuple[bool, str, str]:
    """Write code to temp file, compile and run with go. Returns (success, stdout, stderr)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".go", delete=False, dir="/tmp") as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(
                ["go", "run", f.name] + args,
                capture_output=True, text=True, timeout=EXEC_TIMEOUT,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "TIMEOUT"
        finally:
            os.unlink(f.name)


EXECUTORS = {
    "sigil": execute_sigil,
    "python": execute_python,
    "javascript": execute_javascript,
    "go": execute_go,
}

# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_tests(code: str, language: str, test_cases: list) -> tuple[bool, list]:
    """Run all test cases. Returns (all_passed, results_list)."""
    executor = EXECUTORS[language]
    results = []
    all_passed = True
    for i, tc in enumerate(test_cases):
        args = tc["args"]
        expected = tc["expected"]
        success, stdout, stderr = executor(code, args)
        passed = success and stdout == expected
        if not passed:
            all_passed = False
        results.append({
            "case": i,
            "args": args,
            "expected": repr(expected),
            "actual": repr(stdout),
            "stderr": stderr[:500] if stderr else "",
            "passed": passed,
        })
    return all_passed, results


# ---------------------------------------------------------------------------
# Single benchmark run
# ---------------------------------------------------------------------------

def run_benchmark(
    task: dict,
    language: str,
    model_name: str,
    call_fn,
    run_index: int = 0,
) -> RunResult:
    """Run a single (task, language, model) benchmark with retries."""

    result = RunResult(
        task_id=task["id"],
        language=language,
        model=model_name,
        run_index=run_index,
    )
    t0 = time.time()

    system = SYSTEM_PROMPTS[language]()
    messages = [{"role": "user", "content": task["description"]}]

    for attempt_num in range(MAX_RETRIES):
        # Call model
        try:
            resp = call_fn(model_name, system, messages)
        except Exception as e:
            attempt = Attempt(error=f"API error: {e}")
            result.attempts.append(asdict(attempt))
            break

        code = extract_code(resp["content"], language)
        attempt = Attempt(
            prompt_tokens=resp["prompt_tokens"],
            completion_tokens=resp["completion_tokens"],
            thinking_tokens=resp["thinking_tokens"],
            code=code,
        )

        result.total_prompt_tokens += resp["prompt_tokens"]
        result.total_completion_tokens += resp["completion_tokens"]
        result.total_thinking_tokens += resp["thinking_tokens"]

        # Check if code was extracted
        if not code:
            attempt.error = "No code extracted from response"
            result.attempts.append(asdict(attempt))
            messages.append({"role": "assistant", "content": resp["content"]})
            messages.append({"role": "user", "content": "No code was found in your response. Please output ONLY the code inside a code block."})
            continue

        attempt.parse_ok = True  # We got code at least

        # Run tests
        all_passed, test_results = run_tests(code, language, task["test_cases"])
        attempt.test_results = test_results
        result.attempts.append(asdict(attempt))

        if attempt_num == 0:
            result.first_attempt_correct = all_passed

        if all_passed:
            result.final_correct = True
            result.attempts_to_correct = attempt_num + 1
            break

        # Build error feedback for retry
        failures = [r for r in test_results if not r["passed"]]
        feedback = f"Your code failed {len(failures)}/{len(test_results)} test cases:\n"
        for f in failures[:3]:  # Show max 3 failures
            feedback += f"  args={f['args']} expected={f['expected']} got={f['actual']}"
            if f["stderr"]:
                feedback += f" stderr={f['stderr'][:200]}"
            feedback += "\n"
        feedback += "Fix the code and output ONLY the corrected code in a code block."

        messages.append({"role": "assistant", "content": resp["content"]})
        messages.append({"role": "user", "content": feedback})

    if not result.final_correct:
        result.attempts_to_correct = MAX_RETRIES + 1

    result.total_tokens = (
        result.total_prompt_tokens
        + result.total_completion_tokens
        + result.total_thinking_tokens
    )
    result.wall_time_s = time.time() - t0
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_tasks(task_ids: Optional[list] = None) -> list:
    """Load task definitions from JSON files."""
    tasks = []
    for f in sorted(TASKS_DIR.glob("*.json")):
        task = json.loads(f.read_text())
        if task_ids is None or task["id"] in task_ids:
            tasks.append(task)
    return tasks


def main():
    parser = argparse.ArgumentParser(description="Sigil Benchmark Harness")
    parser.add_argument("--languages", nargs="+", default=["sigil", "python"],
                        choices=LANGUAGES, help="Languages to benchmark")
    parser.add_argument("--tasks", nargs="*", default=None,
                        help="Task IDs to run (default: all)")
    parser.add_argument("--runs", type=int, default=3,
                        help="Number of runs per (task, language, model)")
    parser.add_argument("--model", required=True,
                        help="Model name (e.g. claude-sonnet-4-5-20250514, qwen2.5-coder-7b)")
    parser.add_argument("--provider", default="anthropic",
                        choices=["anthropic", "openai-compat", "together", "ollama", "lmstudio", "claude-cli"],
                        help="API provider")
    parser.add_argument("--base-url", default=None,
                        help="Base URL override (auto-set per provider if omitted)")
    parser.add_argument("--api-key", default=None,
                        help="API key for provider (or set TOGETHER_API_KEY env var)")
    parser.add_argument("--finetuned", action="store_true",
                        help="Model is fine-tuned on Sigil — skip grammar system prompt, use minimal instructions only")
    parser.add_argument("--output", default=None,
                        help="Output JSON file (default: results/<model>_<timestamp>.json)")

    args = parser.parse_args()

    # Set up call function
    PROVIDER_DEFAULTS = {
        "ollama": "http://localhost:11434/v1",
        "lmstudio": "http://localhost:1234/v1",
        "together": "https://api.together.xyz/v1",
        "openai-compat": "http://localhost:1234/v1",
    }

    if args.provider == "anthropic":
        call_fn = call_anthropic
    elif args.provider == "claude-cli":
        call_fn = call_claude_cli
    else:
        base_url = args.base_url or PROVIDER_DEFAULTS.get(args.provider, "http://localhost:1234/v1")
        api_key = args.api_key or os.environ.get("TOGETHER_API_KEY", "not-needed")
        call_fn = lambda model, system, messages: call_openai_compat(
            base_url, model, system, messages, api_key=api_key
        )

    # Override system prompt for fine-tuned Sigil models
    if args.finetuned:
        SYSTEM_PROMPTS["sigil"] = load_sigil_finetuned_prompt

    tasks = load_tasks(args.tasks)
    if not tasks:
        print("No tasks found!", file=sys.stderr)
        sys.exit(1)

    print(f"Benchmark: {len(tasks)} tasks × {len(args.languages)} languages × {args.runs} runs")
    print(f"Model: {args.model} via {args.provider}")
    print(f"Max retries per run: {MAX_RETRIES}")
    print()

    all_results = []
    total = len(tasks) * len(args.languages) * args.runs
    done = 0

    for task in tasks:
        for lang in args.languages:
            for run_idx in range(args.runs):
                done += 1
                label = f"[{done}/{total}] {task['id']} / {lang} / run {run_idx + 1}"
                print(f"{label} ...", end=" ", flush=True)

                result = run_benchmark(task, lang, args.model, call_fn, run_idx)
                all_results.append(asdict(result))

                status = "PASS" if result.final_correct else "FAIL"
                first = "1st" if result.first_attempt_correct else f"{result.attempts_to_correct}att"
                tokens = result.total_tokens
                print(f"{status} ({first}, {tokens} tok, {result.wall_time_s:.1f}s)")

    # Save results
    RESULTS_DIR.mkdir(exist_ok=True)
    if args.output:
        out_path = Path(args.output)
    else:
        ts = time.strftime("%Y%m%d_%H%M%S")
        safe_model = args.model.replace("/", "_").replace(":", "_")
        out_path = RESULTS_DIR / f"{safe_model}_{ts}.json"

    output = {
        "meta": {
            "model": args.model,
            "provider": args.provider,
            "languages": args.languages,
            "runs_per_combo": args.runs,
            "max_retries": MAX_RETRIES,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "results": all_results,
    }
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to {out_path}")

    # Print summary
    print_summary(all_results, args.languages)


def print_summary(results: list, languages: list):
    """Print a summary table."""
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    # Group by language
    for lang in languages:
        lang_results = [r for r in results if r["language"] == lang]
        if not lang_results:
            continue

        n = len(lang_results)
        first_correct = sum(1 for r in lang_results if r["first_attempt_correct"])
        final_correct = sum(1 for r in lang_results if r["final_correct"])
        avg_tokens = sum(r["total_tokens"] for r in lang_results) / n if n else 0
        avg_attempts = sum(r["attempts_to_correct"] for r in lang_results) / n if n else 0

        print(f"\n  {lang.upper()}")
        print(f"    Runs:                {n}")
        print(f"    First-attempt correct: {first_correct}/{n} ({100*first_correct/n:.0f}%)")
        print(f"    Final correct:         {final_correct}/{n} ({100*final_correct/n:.0f}%)")
        print(f"    Avg total tokens:      {avg_tokens:.0f}")
        print(f"    Avg attempts:          {avg_attempts:.1f}")

    # Per-tier breakdown
    print("\n  PER-TIER FIRST-ATTEMPT CORRECTNESS:")
    tiers = {}
    for r in results:
        # Reconstruct tier from task_id
        task_id = r["task_id"]
        tier = "?"
        for t_num in ["01", "02", "03"]:
            if task_id.startswith(t_num):
                tier = "1"
        for t_num in ["04", "05", "06", "07"]:
            if task_id.startswith(t_num):
                tier = "2"
        for t_num in ["08", "09", "10"]:
            if task_id.startswith(t_num):
                tier = "3"

        key = (r["language"], tier)
        if key not in tiers:
            tiers[key] = {"total": 0, "correct": 0}
        tiers[key]["total"] += 1
        if r["first_attempt_correct"]:
            tiers[key]["correct"] += 1

    for lang in languages:
        print(f"\n    {lang.upper()}:")
        for tier in ["1", "2", "3"]:
            key = (lang, tier)
            if key in tiers:
                t = tiers[key]
                pct = 100 * t["correct"] / t["total"] if t["total"] else 0
                print(f"      Tier {tier}: {t['correct']}/{t['total']} ({pct:.0f}%)")

    print()


if __name__ == "__main__":
    main()
