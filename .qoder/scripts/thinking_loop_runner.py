#!/usr/bin/env python3
"""
TradeXV2 Elite Quantitative Engineering - Thinking Loop & Autoresearch Runner
Automates the propose-test-evaluate-commit/revert loop inspired by Andrej Karpathy's autoresearch.
"""

import os
import sys
import re
import json
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.syntax import Syntax
    from rich.prompt import Prompt, Confirm
except ImportError:
    # Fallback to simple print if Rich is not installed (though it's in requirements.txt)
    print("Warning: 'rich' library is not available. Using basic terminal output.")
    class DummyConsole:
        def print(self, *args, **kwargs):
            print(*args)
    Console = DummyConsole
    Panel = lambda text, **kwargs: text
    Table = lambda **kwargs: None
    Prompt = type('Prompt', (), {'ask': lambda text, **kwargs: input(text)})
    Confirm = type('Confirm', (), {'ask': lambda text, **kwargs: input(text).lower().startswith('y')})

console = Console()

# Default Paths
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
QODER_DIR = WORKSPACE_ROOT / ".qoder"
PLANS_DIR = QODER_DIR / "plans"
SCRIPTS_DIR = QODER_DIR / "scripts"
BASELINE_PATH = PLANS_DIR / "baseline_metric.json"
HISTORY_PATH = PLANS_DIR / "thinking_loop_history.json"
DEFAULT_OBJECTIVE_PATH = WORKSPACE_ROOT / "loop_objective.md"

# Ensure directories exist
PLANS_DIR.mkdir(parents=True, exist_ok=True)


def check_git_repo() -> bool:
    """Verifies if the workspace is a Git repository, initializing it if requested."""
    git_dir = WORKSPACE_ROOT / ".git"
    if not git_dir.exists():
        console.print("[yellow]Workspace is not a Git repository. Git is required for the ratchet/revert loop.[/yellow]")
        if Confirm.ask("Would you like to initialize a Git repository in this directory?"):
            try:
                subprocess.run(["git", "init"], cwd=WORKSPACE_ROOT, check=True, stdout=subprocess.DEVNULL)
                subprocess.run(["git", "add", "."], cwd=WORKSPACE_ROOT, check=True, stdout=subprocess.DEVNULL)
                subprocess.run(["git", "commit", "-m", "Initial commit before starting thinking loop"], cwd=WORKSPACE_ROOT, check=True, stdout=subprocess.DEVNULL)
                console.print("[green]Successfully initialized Git repository and created initial commit![/green]\n")
                return True
            except Exception as e:
                console.print(f"[red]Error initializing Git: {e}[/red]")
                return False
        else:
            console.print("[red]Git repository is required. Exiting.[/red]")
            return False
    return True


def get_git_status() -> Tuple[List[str], List[str]]:
    """Returns lists of modified and untracked files."""
    try:
        modified = subprocess.check_output(
            ["git", "diff", "--name-only"], cwd=WORKSPACE_ROOT, text=True
        ).splitlines()
        
        untracked = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=WORKSPACE_ROOT, text=True
        ).splitlines()
        untracked_files = [line[3:] for line in untracked if line.startswith("?? ")]
        
        return modified, untracked_files
    except Exception as e:
        console.print(f"[red]Error running git status: {e}[/red]")
        return [], []


def revert_files(files: List[str]) -> bool:
    """Reverts changes in the specified files."""
    if not files:
        return True
    try:
        # Check out modified files
        subprocess.run(["git", "restore"] + files, cwd=WORKSPACE_ROOT, check=True)
        # Remove untracked files
        for f in files:
            p = WORKSPACE_ROOT / f
            if p.exists() and not p.is_dir():
                try:
                    p.unlink()
                except OSError:
                    pass
        return True
    except Exception as e:
        console.print(f"[red]Error reverting files {files}: {e}[/red]")
        return False


def commit_changes(message: str) -> bool:
    """Commits all current changes in the workspace."""
    try:
        subprocess.run(["git", "add", "."], cwd=WORKSPACE_ROOT, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=WORKSPACE_ROOT, check=True)
        return True
    except Exception as e:
        console.print(f"[red]Error committing changes: {e}[/red]")
        return False


def load_objective(path: Path) -> Dict[str, Any]:
    """Reads and parses the loop_objective.md file."""
    if not path.exists():
        # Create a default objective file
        default_content = (
            "# Loop Objective: Example Optimization\n\n"
            "## Goal\n"
            "Optimize execution speed and type safety of the broker adapters.\n\n"
            "## Target Metric\n"
            "tests.passed > 0 and type_errors == 0\n\n"
            "## Target Files\n"
            "- brokers/runtime/__init__.py\n\n"
            "## Verification Command\n"
            "pytest tests/ -v\n"
        )
        path.write_text(default_content)
        console.print(f"[yellow]Created sample objective file at {path}[/yellow]")
    
    content = path.read_text()
    
    # Parse target files
    target_files = []
    files_match = re.search(r"## Target Files\s*\n((?:\s*-\s*[^\n]+\n*)+)", content)
    if files_match:
        target_files = [line.strip().lstrip("-").strip() for line in files_match.group(1).strip().split("\n")]
        
    # Parse verification command
    verification_cmd = "pytest"
    cmd_match = re.search(r"## Verification Command\s*\n\s*`?([^`\n]+)`?", content)
    if cmd_match:
        verification_cmd = cmd_match.group(1).strip()
        
    return {
        "content": content,
        "target_files": target_files,
        "verification_command": verification_cmd
    }


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
        save_baseline(default_baseline)
        return default_baseline
    try:
        return json.loads(BASELINE_PATH.read_text())
    except Exception:
        return {}


def save_baseline(baseline: Dict[str, Any]):
    """Saves baseline metrics to local settings."""
    BASELINE_PATH.write_text(json.dumps(baseline, indent=2))


def log_history(iteration: int, status: str, metrics: Dict[str, Any], message: str):
    """Logs the details of the loop run to history."""
    history = []
    if HISTORY_PATH.exists():
        try:
            history = json.loads(HISTORY_PATH.read_text())
        except Exception:
            pass
    
    history.append({
        "iteration": iteration,
        "status": status,
        "metrics": metrics,
        "commit_message": message
    })
    HISTORY_PATH.write_text(json.dumps(history, indent=2))


def run_verification(cmd: str) -> Tuple[bool, str]:
    """Runs a verification shell command and captures its outputs."""
    console.print(f"[cyan]Running verification command: [bold]{cmd}[/bold][/cyan]")
    try:
        res = subprocess.run(
            cmd, cwd=WORKSPACE_ROOT, shell=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        return res.returncode == 0, res.stdout
    except Exception as e:
        return False, str(e)


def parse_pytest_output(output: str) -> Dict[str, Any]:
    """Parses raw stdout from pytest to extract total, passed, and failed runs."""
    passed = 0
    failed = 0
    total = 0
    
    # Try parsing summary lines like: "1 passed, 2 failed in 0.12s"
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
        # Fallback to checking line by line for PASSED / FAILED test lines
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


def parse_mypy_output(output: str) -> int:
    """Parses mypy output to extract type error counts."""
    # Pattern: "Found 5 errors in 2 files"
    error_match = re.search(r"Found\s+(\d+)\s+error", output)
    if error_match:
        return int(error_match.group(1))
    if "Success: no issues found" in output:
        return 0
    return 0


def parse_ruff_output(output: str) -> int:
    """Parses ruff output to extract lint error counts."""
    # Pattern: "Found 4 errors."
    error_match = re.search(r"Found\s+(\d+)\s+error", output)
    if error_match:
        return int(error_match.group(1))
    return 0


def parse_performance_metrics(output: str) -> Dict[str, Any]:
    """Extracts custom performance or quant metrics if printed in output."""
    latency = 9999.0
    pnl = -9999.0
    
    # Try finding latency metrics
    latency_match = re.search(r"latency:\s*([\d\.]+)\s*ms", output, re.IGNORECASE)
    if latency_match:
        latency = float(latency_match.group(1))
        
    # Try finding PnL metrics
    pnl_match = re.search(r"pnl:\s*([\d\.\-]+)", output, re.IGNORECASE)
    if pnl_match:
        pnl = float(pnl_match.group(1))
        
    return {
        "latency_ms": latency,
        "pnl": pnl
    }


def evaluate_metrics(current: Dict[str, Any], baseline: Dict[str, Any], metric_key: str) -> Tuple[bool, str]:
    """Compares current metrics to baseline, determining if there is a regression or improvement."""
    # 1. Hard verification gates
    if current["tests"]["failed"] > 0:
        return False, f"Regression: {current['tests']['failed']} unit tests failed."
    
    if current["type_errors"] > baseline.get("type_errors", 9999):
        return False, f"Regression: Type errors increased from {baseline.get('type_errors')} to {current['type_errors']}."
        
    if current["lint_errors"] > baseline.get("lint_errors", 9999):
        return False, f"Regression: Lint errors increased from {baseline.get('lint_errors')} to {current['lint_errors']}."
        
    # 2. Check metric improvements based on metric_key path
    if metric_key == "tests.passed":
        if current["tests"]["passed"] > baseline["tests"]["passed"]:
            return True, f"Improvement: Passed tests increased from {baseline['tests']['passed']} to {current['tests']['passed']}."
        elif current["tests"]["passed"] == baseline["tests"]["passed"]:
            return False, "No change: Test count remains identical."
        else:
            return False, "Regression: Fewer tests passed."
            
    elif metric_key == "performance.latency_ms":
        curr_lat = current["performance"]["latency_ms"]
        base_lat = baseline.get("performance", {}).get("latency_ms", 9999.0)
        if curr_lat < base_lat:
            return True, f"Improvement: Latency reduced from {base_lat}ms to {curr_lat}ms."
        return False, f"No improvement: Latency is {curr_lat}ms (baseline was {base_lat}ms)."
        
    elif metric_key == "performance.pnl":
        curr_pnl = current["performance"]["pnl"]
        base_pnl = baseline.get("performance", {}).get("pnl", -9999.0)
        if curr_pnl > base_pnl:
            return True, f"Improvement: PnL increased from {base_pnl} to {curr_pnl}."
        return False, f"No improvement: PnL is {curr_pnl} (baseline was {base_pnl})."

    # Default fallback
    return False, "No target metric improvement identified."


def render_dashboard(iteration: int, baseline: Dict[str, Any], current: Optional[Dict[str, Any]] = None):
    """Renders a status dashboard in the terminal."""
    os.system("clear" if os.name == "posix" else "cls")
    
    console.print(Panel.fit(
        f"[bold cyan]TradeXV2 Elite Quantitative Engineering[/bold cyan]\n"
        f"[bold white]RATChET / THINKING LOOP RUNNER[/bold white] (Karpathy Pattern)",
        border_style="cyan"
    ))
    
    table = Table(title=f"Loop Status — Iteration {iteration}", show_header=True, header_style="bold magenta")
    table.add_column("Metric Group")
    table.add_column("Metric Name")
    table.add_column("Baseline Value")
    table.add_column("Current Value")
    table.add_column("Status")
    
    # Unit Tests
    c_passed = current["tests"]["passed"] if current else "N/A"
    c_failed = current["tests"]["failed"] if current else "N/A"
    table.add_row(
        "Unit Tests", "Passed Tests", 
        str(baseline["tests"]["passed"]), str(c_passed),
        "[green]OK[/green]" if (current and c_failed == 0) else "[yellow]Pending[/yellow]"
    )
    table.add_row(
        "Unit Tests", "Failed Tests", 
        str(baseline["tests"]["failed"]), str(c_failed),
        "[green]OK[/green]" if (current and c_failed == 0) else "[red]Regressed[/red]" if (current and c_failed > 0) else "[yellow]Pending[/yellow]"
    )
    
    # Types & Formatting
    c_types = current["type_errors"] if current else "N/A"
    c_lints = current["lint_errors"] if current else "N/A"
    table.add_row(
        "Code Health", "Type Errors (mypy)", 
        str(baseline.get("type_errors", "N/A")), str(c_types),
        "[green]OK[/green]" if (current and c_types <= baseline.get("type_errors", 9999)) else "[red]Regressed[/red]" if current else "[yellow]Pending[/yellow]"
    )
    table.add_row(
        "Code Health", "Lint Errors (ruff)", 
        str(baseline.get("lint_errors", "N/A")), str(c_lints),
        "[green]OK[/green]" if (current and c_lints <= baseline.get("lint_errors", 9999)) else "[red]Regressed[/red]" if current else "[yellow]Pending[/yellow]"
    )
    
    # Performance
    b_lat = baseline.get("performance", {}).get("latency_ms", "N/A")
    c_lat = current["performance"]["latency_ms"] if (current and current["performance"]["latency_ms"] < 9999.0) else "N/A"
    b_pnl = baseline.get("performance", {}).get("pnl", "N/A")
    c_pnl = current["performance"]["pnl"] if (current and current["performance"]["pnl"] > -9999.0) else "N/A"
    
    table.add_row("Performance", "Latency (ms)", str(b_lat), str(c_lat), "")
    table.add_row("Performance", "PnL", str(b_pnl), str(c_pnl), "")
    
    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Run the thinking loop optimization harness.")
    parser.add_argument("--objective", type=str, default="loop_objective.md", help="Objective markdown file")
    parser.add_argument("--max-iterations", type=int, default=5, help="Maximum number of loop iterations")
    parser.add_argument("--metric-key", type=str, default="tests.passed", help="Metric to optimize (e.g. tests.passed, performance.latency_ms)")
    parser.add_argument("--interactive", action="store_true", default=True, help="Wait for manual code edits at each iteration")
    args = parser.parse_args()
    
    if not check_git_repo():
        sys.exit(1)
        
    objective_path = Path(args.objective)
    objective = load_objective(objective_path)
    
    baseline = load_baseline()
    
    iteration = 1
    max_iter = args.max_iterations
    
    while iteration <= max_iter:
        render_dashboard(iteration, baseline)
        
        console.print(f"\n[bold green]Objective:[/bold green] {objective_path.name}")
        console.print(f"[bold green]Target Files:[/bold green] {', '.join(objective['target_files'])}")
        
        # Verify clean workspace before edits
        modified, untracked = get_git_status()
        target_modifications = [f for f in modified + untracked if f in objective["target_files"]]
        other_modifications = [f for f in modified + untracked if f not in objective["target_files"]]
        
        if other_modifications:
            console.print(f"[yellow]Warning: Uncommitted changes found in non-target files: {other_modifications}[/yellow]")
            if not Confirm.ask("Would you like to stash them or proceed anyway?"):
                sys.exit(0)
                
        if args.interactive:
            console.print("\n[bold yellow]Ready for edits.[/bold yellow] Please modify target files to optimize the metric.")
            Prompt.ask("Press [Enter] once you have saved changes to target files to run verification")
        
        # 1. Run Verification Command
        success, output = run_verification(objective["verification_command"])
        
        # Check type errors & lint errors in target files specifically (mock values if checks not run)
        type_errors = 0
        lint_errors = 0
        
        # Run type checking if mypy is available
        mypy_ok, mypy_out = run_verification(f"mypy {' '.join(objective['target_files'])}")
        if mypy_ok or "Found" in mypy_out:
            type_errors = parse_mypy_output(mypy_out)
            
        # Run linter if ruff is available
        ruff_ok, ruff_out = run_verification(f"ruff check {' '.join(objective['target_files'])}")
        if ruff_ok or "Found" in ruff_out:
            lint_errors = parse_ruff_output(ruff_out)
            
        # Parse output test metrics
        test_metrics = parse_pytest_output(output)
        perf_metrics = parse_performance_metrics(output)
        
        current_run_metrics = {
            "syntax_ok": "SyntaxError" not in output,
            "type_errors": type_errors,
            "lint_errors": lint_errors,
            "tests": test_metrics,
            "performance": perf_metrics
        }
        
        render_dashboard(iteration, baseline, current_run_metrics)
        
        # 2. Evaluate
        improved, reason = evaluate_metrics(current_run_metrics, baseline, args.metric_key)
        
        if improved:
            console.print(f"\n[green]✔ Evaluation SUCCESS![/green] {reason}")
            
            commit_msg = f"Loop Ratchet [Iter {iteration}]: Optimized {args.metric_key} - {reason}"
            if Confirm.ask("Would you like to COMMIT and RATCHET these changes?"):
                commit_changes(commit_msg)
                baseline = current_run_metrics
                save_baseline(baseline)
                log_history(iteration, "COMMITTED", current_run_metrics, commit_msg)
                console.print(f"[green]Changes committed. Baseline updated to iteration {iteration} metrics.[/green]")
            else:
                log_history(iteration, "SKIPPED_COMMIT", current_run_metrics, "User declined commit")
                console.print("[yellow]Changes NOT committed, but kept in workspace.[/yellow]")
        else:
            console.print(f"\n[red]✘ Evaluation FAILED![/red] {reason}")
            
            # Find files to revert
            modified, untracked = get_git_status()
            files_to_revert = [f for f in modified + untracked if f in objective["target_files"]]
            
            if files_to_revert:
                if Confirm.ask(f"Would you like to REVERT changes in target files to restore baseline? ({files_to_revert})"):
                    revert_files(files_to_revert)
                    log_history(iteration, "REVERTED", current_run_metrics, f"Reverted: {reason}")
                    console.print("[green]Workspace successfully reverted to baseline.[/green]")
                else:
                    log_history(iteration, "REVERT_DECLINED", current_run_metrics, "User declined revert")
                    console.print("[yellow]Revert declined. Workspace remains modified.[/yellow]")
            else:
                console.print("[yellow]No target files were modified. Nothing to revert.[/yellow]")
                
        iteration += 1
        if iteration <= max_iter:
            if not Confirm.ask("Proceed to next iteration?"):
                break
                
    console.print("\n[bold cyan]Loop run complete. Check history at .qoder/plans/thinking_loop_history.json[/bold cyan]")


if __name__ == "__main__":
    main()
