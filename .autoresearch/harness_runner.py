#!/usr/bin/env python3
"""
Autoresearch Git-Ratchet Harness Runner
Self-contained runner designed to run in any Python environment.
Enforces the loop: Propose -> Test -> Evaluate -> Commit (Ratchet) or Revert.
"""

import os
import sys
import re
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

# Core Paths
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
AUTORESEARCH_DIR = WORKSPACE_ROOT / ".autoresearch"
CONFIG_PATH = AUTORESEARCH_DIR / "config.json"
BASELINE_PATH = AUTORESEARCH_DIR / "baseline.json"
RUNS_DIR = AUTORESEARCH_DIR / "runs"
LATEST_LOG_PATH = RUNS_DIR / "latest_run.log"
HISTORY_PATH = RUNS_DIR / "history.json"

# Ensure run directory exists
RUNS_DIR.mkdir(parents=True, exist_ok=True)


def log_color(message: str, color: str = "white"):
    """Simple ANSI terminal color logging helper."""
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "cyan": "\033[96m",
        "bold": "\033[1m",
        "end": "\033[0m"
    }
    prefix = colors.get(color, "")
    suffix = colors.get("end", "")
    print(f"{prefix}{message}{suffix}")


def check_git_repo() -> bool:
    """Verifies that the workspace is a Git repository, offering initialization if missing."""
    git_dir = WORKSPACE_ROOT / ".git"
    if not git_dir.exists():
        log_color("Workspace is not a Git repository. Git is required for the commit/revert loop.", "yellow")
        choice = input("Initialize a Git repository here? (y/n): ").strip().lower()
        if choice.startswith('y'):
            try:
                subprocess.run(["git", "init"], cwd=WORKSPACE_ROOT, check=True, stdout=subprocess.DEVNULL)
                subprocess.run(["git", "add", "."], cwd=WORKSPACE_ROOT, check=True, stdout=subprocess.DEVNULL)
                subprocess.run(["git", "commit", "-m", "Initial commit before starting autoresearch loop"], cwd=WORKSPACE_ROOT, check=True, stdout=subprocess.DEVNULL)
                log_color("Successfully initialized Git repository!", "green")
                return True
            except Exception as e:
                log_color(f"Error initializing Git: {e}", "red")
                return False
        else:
            log_color("Git is required to run the ratchet loop. Exiting.", "red")
            return False
    return True


def get_git_status(target_files: List[str]) -> Tuple[List[str], List[str]]:
    """Returns lists of modified and untracked target files."""
    try:
        modified_out = subprocess.check_output(
            ["git", "diff", "--name-only"], cwd=WORKSPACE_ROOT, text=True
        ).splitlines()
        
        status_out = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=WORKSPACE_ROOT, text=True
        ).splitlines()
        
        untracked = [line[3:] for line in status_out if line.startswith("?? ")]
        
        modified_targets = [f for f in modified_out if f in target_files]
        untracked_targets = [f for f in untracked if f in target_files]
        
        return modified_targets, untracked_targets
    except Exception as e:
        log_color(f"Error checking git status: {e}", "red")
        return [], []


def revert_target_files(files: List[str]):
    """Discards changes in modified target files and deletes untracked target files."""
    if not files:
        return
    try:
        # Restore modified target files
        subprocess.run(["git", "restore"] + files, cwd=WORKSPACE_ROOT, check=True)
        # Delete untracked files
        for f in files:
            p = WORKSPACE_ROOT / f
            if p.exists() and not p.is_dir():
                try:
                    p.unlink()
                except OSError:
                    pass
        log_color(f"Reverted changes in files: {files}", "yellow")
    except Exception as e:
        log_color(f"Error reverting target files: {e}", "red")


def commit_target_changes(files: List[str], message: str) -> bool:
    """Stages and commits only the specified target files."""
    try:
        subprocess.run(["git", "add"] + files, cwd=WORKSPACE_ROOT, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=WORKSPACE_ROOT, check=True)
        log_color(f"Committed changes in target files with message: '{message}'", "green")
        return True
    except Exception as e:
        log_color(f"Error committing target changes: {e}", "red")
        return False


def load_config() -> Dict[str, Any]:
    """Loads loop configuration from config.json."""
    if not CONFIG_PATH.exists():
        default_config = {
            "target_files": [],
            "immutable_files": [".autoresearch/"],
            "evaluation_command": "pytest",
            "metric_to_optimize": "tests.passed",
            "optimize_direction": "higher",
            "git_ratchet": True,
            "max_iterations": 5
        }
        CONFIG_PATH.write_text(json.dumps(default_config, indent=2))
        return default_config
    return json.loads(CONFIG_PATH.read_text())


def load_baseline() -> Dict[str, Any]:
    """Loads baseline metrics, initializing them if missing."""
    if not BASELINE_PATH.exists():
        default_baseline = {
            "syntax_ok": True,
            "type_errors": 9999,
            "lint_errors": 9999,
            "tests": {
                "total": 0,
                "passed": 0,
                "failed": 9999,
                "pass_rate": 0.0
            },
            "performance": {
                "latency_ms": 9999.0,
                "pnl": -9999.0
            }
        }
        BASELINE_PATH.write_text(json.dumps(default_baseline, indent=2))
        return default_baseline
    return json.loads(BASELINE_PATH.read_text())


def save_baseline(metrics: Dict[str, Any]):
    """Saves new baseline metrics."""
    BASELINE_PATH.write_text(json.dumps(metrics, indent=2))


def log_run_history(status: str, metrics: Dict[str, Any], message: str):
    """Appends iteration results to history logs."""
    history = []
    if HISTORY_PATH.exists():
        try:
            history = json.loads(HISTORY_PATH.read_text())
        except Exception:
            pass
    history.append({
        "status": status,
        "metrics": metrics,
        "message": message
    })
    HISTORY_PATH.write_text(json.dumps(history, indent=2))


def run_evaluation(command: str) -> Tuple[bool, str]:
    """Executes the test command, capturing raw outputs to latest_run.log."""
    log_color(f"Executing evaluation command: '{command}'", "cyan")
    try:
        res = subprocess.run(
            command, shell=True, text=True, cwd=WORKSPACE_ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        LATEST_LOG_PATH.write_text(res.stdout)
        return res.returncode == 0, res.stdout
    except Exception as e:
        LATEST_LOG_PATH.write_text(str(e))
        return False, str(e)


def parse_pytest_output(output: str) -> Dict[str, Any]:
    """Parses pytest summary line (passed, failed, pass_rate)."""
    passed = 0
    failed = 0
    total = 0
    
    summary_match = re.search(r"===\s+([\d\s\w,\s]+)\s+in\s+[\d\.]+s\s+===", output)
    if summary_match:
        summary = summary_match.group(1)
        passed_m = re.search(r"(\d+)\s+passed", summary)
        failed_m = re.search(r"(\d+)\s+failed", summary)
        if passed_m:
            passed = int(passed_m.group(1))
        if failed_m:
            failed = int(failed_m.group(1))
        total = passed + failed
    else:
        passed = len(re.findall(r"PASSED", output))
        failed = len(re.findall(r"FAILED", output))
        total = passed + failed
        
    pass_rate = (passed / total) if total > 0 else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate
    }


def parse_type_errors(target_files: List[str]) -> int:
    """Runs mypy on modified files if installed to count type errors."""
    try:
        res = subprocess.run(
            ["mypy"] + target_files, cwd=WORKSPACE_ROOT, shell=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        error_match = re.search(r"Found\s+(\d+)\s+error", res.stdout)
        if error_match:
            return int(error_match.group(1))
        if "Success: no issues found" in res.stdout:
            return 0
    except FileNotFoundError:
        pass
    return 0


def parse_lint_errors(target_files: List[str]) -> int:
    """Runs ruff on modified files if installed to count lint violations."""
    try:
        res = subprocess.run(
            ["ruff", "check"] + target_files, cwd=WORKSPACE_ROOT, shell=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        error_match = re.search(r"Found\s+(\d+)\s+error", res.stdout)
        if error_match:
            return int(error_match.group(1))
    except FileNotFoundError:
        pass
    return 0


def get_metric_value(metrics: Dict[str, Any], key_path: str) -> Optional[Any]:
    """Helper to extract nested dictionary keys (e.g. 'tests.passed')."""
    parts = key_path.split(".")
    val = metrics
    for part in parts:
        if isinstance(val, dict) and part in val:
            val = val[part]
        else:
            return None
    return val


def main():
    if not check_git_repo():
        sys.exit(1)
        
    config = load_config()
    baseline = load_baseline()
    
    target_files = config.get("target_files", [])
    if not target_files:
        log_color("Error: No 'target_files' specified in config.json.", "red")
        sys.exit(1)
        
    # Check if target files have modifications
    modified, untracked = get_git_status(target_files)
    changed_files = modified + untracked
    
    if not changed_files:
        log_color("No changes detected in target files. Propose a change and run again.", "yellow")
        sys.exit(0)
        
    log_color(f"Evaluating changes in files: {changed_files}", "cyan")
    
    # 1. Run command
    success, output = run_evaluation(config["evaluation_command"])
    
    # 2. Parse metrics
    test_metrics = parse_pytest_output(output)
    type_errs = parse_type_errors(changed_files)
    lint_errs = parse_lint_errors(changed_files)
    
    current_metrics = {
        "syntax_ok": "SyntaxError" not in output,
        "type_errors": type_errs,
        "lint_errors": lint_errs,
        "tests": test_metrics,
        "performance": {
            "latency_ms": 9999.0,  # Default
            "pnl": -9999.0        # Default
        }
    }
    
    # Check for custom metrics (e.g. latency, PnL) printed in output
    latency_match = re.search(r"latency:\s*([\d\.]+)\s*ms", output, re.IGNORECASE)
    if latency_match:
        current_metrics["performance"]["latency_ms"] = float(latency_match.group(1))
        
    pnl_match = re.search(r"pnl:\s*([\d\.\-]+)", output, re.IGNORECASE)
    if pnl_match:
        current_metrics["performance"]["pnl"] = float(pnl_match.group(1))
        
    # 3. Evaluate Improvement
    metric_key = config.get("metric_to_optimize", "tests.passed")
    direction = config.get("optimize_direction", "higher")
    
    # Hard gates
    if current_metrics["tests"]["failed"] > 0:
        log_color(f"✘ FAILED: Regression! {current_metrics['tests']['failed']} tests failed.", "red")
        revert_target_files(changed_files)
        log_run_history("REVERTED", current_metrics, f"Failing tests: {current_metrics['tests']['failed']} failed")
        sys.exit(1)
        
    if current_metrics["type_errors"] > baseline.get("type_errors", 9999):
        log_color(f"✘ FAILED: Type checking errors increased from {baseline['type_errors']} to {current_metrics['type_errors']}.", "red")
        revert_target_files(changed_files)
        log_run_history("REVERTED", current_metrics, "Type check regressions")
        sys.exit(1)
        
    if current_metrics["lint_errors"] > baseline.get("lint_errors", 9999):
        log_color(f"✘ FAILED: Lint violations increased from {baseline['lint_errors']} to {current_metrics['lint_errors']}.", "red")
        revert_target_files(changed_files)
        log_run_history("REVERTED", current_metrics, "Lint check regressions")
        sys.exit(1)
        
    curr_val = get_metric_value(current_metrics, metric_key)
    base_val = get_metric_value(baseline, metric_key)
    
    if curr_val is None or base_val is None:
        log_color(f"Error: Metric key '{metric_key}' not found in results.", "red")
        sys.exit(1)
        
    improved = False
    if direction == "higher" and curr_val > base_val:
        improved = True
    elif direction == "lower" and curr_val < base_val:
        improved = True
        
    if improved:
        log_color(f"✔ SUCCESS! Metric '{metric_key}' improved from {base_val} to {curr_val}!", "green")
        commit_msg = f"Autoresearch Ratchet: Improved {metric_key} from {base_val} to {curr_val}"
        
        if config.get("git_ratchet", True):
            if commit_target_changes(changed_files, commit_msg):
                save_baseline(current_metrics)
                log_run_history("COMMITTED", current_metrics, commit_msg)
        else:
            log_color("Git commit skipped (git_ratchet is disabled in config.json). Baseline not updated.", "yellow")
    else:
        log_color(f"✘ FAILED: Metric '{metric_key}' is {curr_val} (baseline was {base_val}). No improvement.", "red")
        revert_target_files(changed_files)
        log_run_history("REVERTED", current_metrics, f"No metric improvement for {metric_key}")
        sys.exit(1)


if __name__ == "__main__":
    main()
