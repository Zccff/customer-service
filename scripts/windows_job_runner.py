"""Fixed Windows equivalents of the Makefile jobs exposed by the admin page."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Recipe:
    name: str
    kind: str
    target: str = ""
    args: tuple[str, ...] = ()
    ml: bool = False
    stdin_path: str = ""


RECIPES: dict[str, Recipe] = {
    recipe.name: recipe for recipe in (
        Recipe("kb-preview", "python", "scripts/show_kb.py"),
        Recipe("kb-build", "python", "scripts/build_kb.py"),
        Recipe("kb-mine", "python", "scripts/mine_knowledge.py"),
        Recipe("kb-vectorize", "python", "scripts/vectorize_kb.py"),
        Recipe("kb-repatch", "python", "scripts/kb_repatch.py"),
        Recipe("seed-conv", "sql", stdin_path="sql/ch03-seed.sql"),
        Recipe("kb-reset", "reset"),
        Recipe("eval-rag", "python", "scripts/eval_ch04.py"),
        Recipe("cost-report", "python", "scripts/cost_by_intent.py", ("--days", "7")),
        Recipe("eval-flywheel", "python", "scripts/eval_flywheel.py",
               ("--triggered-by", "手动")),
        Recipe("calibrate-confidence", "python", "scripts/calibrate_confidence.py"),
        Recipe("ch10-golden", "python", "scripts/ch10/validate_golden.py"),
        Recipe("ch10-corpus", "python", "scripts/ch10/build_corpus.py"),
        Recipe("ch10-dataset", "python", "scripts/ch10/build_dataset.py"),
        Recipe("ch10-train", "python", "scripts/ch10/train.py", ml=True),
        Recipe("ch10-eval", "python", "scripts/ch10/evaluate.py", ml=True),
        Recipe("ch10-export", "python", "scripts/ch10/export_onnx.py", ml=True),
        Recipe("ch10-threshold-scan", "python", "scripts/ch10/scan_threshold_replay.py"),
        Recipe("classifier-up", "classifier-up", ml=True),
        Recipe("classifier-down", "classifier-down", ml=True),
        Recipe("classify-pool", "python", "scripts/ch10/classify_pool.py"),
        Recipe("classify-pool-force", "python", "scripts/ch10/classify_pool.py", ("--force",)),
    )
}


def recipe(name: str) -> Recipe | None:
    return RECIPES.get(name)


def _python_for(recipe_spec: Recipe, repo_root: Path,
                python_executable: Path | None = None) -> Path:
    if python_executable is not None:
        return Path(python_executable)
    if recipe_spec.ml:
        for relative in (".venv-ml/Scripts/python.exe", ".venv/Scripts/python.exe"):
            candidate = repo_root / relative
            if candidate.is_file():
                return candidate
    return Path(sys.executable)


def command_argv(name: str, repo_root: Path = REPO_ROOT,
                 python_executable: Path | None = None) -> tuple[str, ...]:
    recipe_spec = RECIPES[name]
    if recipe_spec.kind != "python":
        raise ValueError(f"{name} is a {recipe_spec.kind} recipe")
    python = _python_for(recipe_spec, repo_root, python_executable)
    return (str(python), str(repo_root / recipe_spec.target), *recipe_spec.args)


def _environment(repo_root: Path) -> dict[str, str]:
    env = {
        **os.environ,
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "HF_HOME": str(repo_root / ".runtime-models" / "huggingface"),
    }
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(repo_root) + (os.pathsep + current if current else "")
    return env


def _run_command(argv: tuple[str, ...], repo_root: Path, env: dict[str, str],
                 stdin=None) -> int:
    completed = subprocess.run(argv, cwd=repo_root, env=env, stdin=stdin, check=False)
    return completed.returncode


def run(name: str, repo_root: Path = REPO_ROOT) -> int:
    recipe_spec = recipe(name)
    if recipe_spec is None:
        print(f"Unknown Windows job: {name}", file=sys.stderr)
        return 2
    env = _environment(repo_root)

    if recipe_spec.kind == "python":
        return _run_command(command_argv(name, repo_root), repo_root, env)
    if recipe_spec.kind == "sql":
        argv = ("docker", "exec", "-i", "mewhelp-mysql", "mysql",
                "--default-character-set=utf8mb4", "-uroot", "-proot", "mewhelp")
        with (repo_root / recipe_spec.stdin_path).open("rb") as sql:
            return _run_command(argv, repo_root, env, stdin=sql)
    if recipe_spec.kind == "reset":
        mysql = ("docker", "exec", "-i", "mewhelp-mysql", "mysql", "-uroot", "-proot",
                 "mewhelp", "-e", "SET FOREIGN_KEY_CHECKS=0; DELETE FROM knowledge_chunks; "
                 "DELETE FROM qa_extraction_staging; SET FOREIGN_KEY_CHECKS=1;")
        rc = _run_command(mysql, repo_root, env)
        if rc:
            return rc
        python = _python_for(recipe_spec, repo_root)
        drop = (str(python), "-c", "from app.kb import milvus_client as m; "
                "m.drop(m.get_client(), 'knowledge')")
        return _run_command(drop, repo_root, env)
    from scripts import windows_classifier

    python = _python_for(recipe_spec, repo_root)
    if recipe_spec.kind == "classifier-up":
        return windows_classifier.start(repo_root, python, env)
    return windows_classifier.stop(repo_root)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: windows_job_runner.py JOB_NAME", file=sys.stderr)
        return 2
    return run(args[0])


if __name__ == "__main__":
    raise SystemExit(main())
