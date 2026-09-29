import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import jobs


class _FakeProcess:
    def __init__(self, pid: int = 4321, returncode: int = 0):
        self.pid = pid
        self.returncode = returncode

    async def wait(self):
        return self.returncode


@pytest.fixture(autouse=True)
def _clear_runs():
    jobs._runs.clear()
    yield
    jobs._runs.clear()


def test_windows_runner_has_a_fixed_recipe_for_every_registered_job():
    """Removing a recipe must fail before a management-page button reaches production."""
    from scripts import windows_job_runner

    assert set(windows_job_runner.RECIPES) == set(jobs.JOBS)
    assert windows_job_runner.recipe("not-a-job") is None
    for name in jobs.JOBS:
        recipe = windows_job_runner.recipe(name)
        assert recipe is not None
        assert recipe.name == name


def test_windows_python_recipe_uses_the_selected_interpreter_and_fixed_args(tmp_path):
    """A Python task must not route through make or accept command text from the request."""
    from scripts import windows_job_runner

    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    argv = windows_job_runner.command_argv("kb-preview", tmp_path, python_executable=python)

    assert argv == (str(python), str(tmp_path / "scripts" / "show_kb.py"))
    assert all("make" not in part.lower() for part in argv)


def test_ml_recipes_prefer_venv_ml_and_fall_back_to_venv(tmp_path):
    """The classifier's heavy commands must use the isolated ML environment when present."""
    from scripts import windows_job_runner

    base = tmp_path / ".venv" / "Scripts" / "python.exe"
    base.parent.mkdir(parents=True)
    base.touch()
    assert windows_job_runner.command_argv("ch10-train", tmp_path)[0] == str(base)

    ml = tmp_path / ".venv-ml" / "Scripts" / "python.exe"
    ml.parent.mkdir(parents=True)
    ml.touch()
    assert windows_job_runner.command_argv("ch10-train", tmp_path)[0] == str(ml)
    assert windows_job_runner.command_argv("kb-preview", tmp_path, python_executable=base)[0] == str(base)


def test_sql_recipe_streams_the_seed_file_without_a_shell(tmp_path, monkeypatch):
    """Seed SQL must be stdin data; it must never be interpolated into a shell command."""
    from scripts import windows_job_runner

    sql = tmp_path / "sql" / "ch03-seed.sql"
    sql.parent.mkdir()
    sql.write_bytes("INSERT INTO t VALUES ('中文');".encode("utf-8"))
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = tuple(argv)
        seen["shell"] = kwargs.get("shell", False)
        seen["stdin"] = kwargs["stdin"].read()
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(windows_job_runner.subprocess, "run", fake_run)
    assert windows_job_runner.run("seed-conv", repo_root=tmp_path) == 0
    assert seen == {
        "argv": ("docker", "exec", "-i", "mewhelp-mysql", "mysql",
                 "--default-character-set=utf8mb4", "-uroot", "-proot", "mewhelp"),
        "shell": False,
        "stdin": "INSERT INTO t VALUES ('中文');".encode("utf-8"),
    }


async def test_windows_start_uses_runner_and_utf8_environment(monkeypatch, tmp_path):
    """Dropping UTF-8 or the repository import path would break Chinese data on Windows."""
    captured = {}
    fake = _FakeProcess()

    async def fake_create(*argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return fake

    monkeypatch.setattr(jobs, "LOG_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_is_windows", lambda: True)
    monkeypatch.setattr(jobs.asyncio, "create_subprocess_exec", fake_create)
    run = await jobs.start("kb-preview")
    await run.watcher

    assert captured["argv"] == (
        sys.executable,
        str(jobs.REPO_ROOT / "scripts" / "windows_job_runner.py"),
        "kb-preview",
    )
    env = captured["kwargs"]["env"]
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(jobs.REPO_ROOT)
    assert "start_new_session" not in captured["kwargs"]
    assert captured["kwargs"]["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP


async def test_running_job_refuses_duplicate_start(monkeypatch):
    """Starting the same job twice must not launch a second process tree."""
    jobs._runs["kb-build"] = jobs.JobRun(status="running", pid=777)

    async def should_not_start(*args, **kwargs):
        raise AssertionError("a duplicate process was launched")

    monkeypatch.setattr(jobs.asyncio, "create_subprocess_exec", should_not_start)
    with pytest.raises(RuntimeError, match="正在运行中"):
        await jobs.start("kb-build")


async def test_simultaneous_starts_launch_only_one_process(monkeypatch, tmp_path):
    entered = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()
    calls = []
    class PendingProcess(_FakeProcess):
        async def wait(self):
            await finished.wait()
            return 0
    async def create(*args, **kwargs):
        calls.append(args)
        entered.set()
        await release.wait()
        return PendingProcess()
    monkeypatch.setattr(jobs, "LOG_DIR", tmp_path)
    monkeypatch.setattr(jobs.asyncio, "create_subprocess_exec", create)
    first = asyncio.create_task(jobs.start("kb-preview"))
    await entered.wait()
    second = asyncio.create_task(jobs.start("kb-preview"))
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)
    finished.set()
    await jobs._runs["kb-preview"].watcher
    assert len(calls) == 1
    assert sum(isinstance(r, RuntimeError) for r in results) == 1


async def test_windows_stop_reports_taskkill_failure_and_keeps_job_running(monkeypatch):
    """A denied tree termination must not be reported as a successfully stopped job."""
    proc = _FakeProcess(pid=6789)
    killer = _FakeProcess(returncode=5)

    async def fake_create(*args, **kwargs):
        return killer

    monkeypatch.setattr(jobs, "_is_windows", lambda: True)
    monkeypatch.setattr(jobs.asyncio, "create_subprocess_exec", fake_create)
    monkeypatch.setitem(jobs._runs, "kb-preview",
                        jobs.JobRun(status="running", pid=proc.pid, proc=proc))

    with pytest.raises(RuntimeError, match="taskkill"):
        await jobs.stop("kb-preview")
    assert jobs._runs["kb-preview"].status == "running"


@pytest.mark.skipif(os.name != "nt", reason="exercises Windows taskkill process-tree semantics")
async def test_windows_stop_terminates_parent_and_child_processes(tmp_path, monkeypatch):
    """Stopping a job must not leave the Python child spawned by its runner alive."""
    child_pid_file = tmp_path / "child.pid"
    parent_code = (
        "import subprocess,sys,time,pathlib; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        f"pathlib.Path({str(child_pid_file)!r}).write_text(str(p.pid)); "
        "time.sleep(60)"
    )
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", parent_code,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        for _ in range(100):
            if child_pid_file.exists():
                break
            await asyncio.sleep(0.02)
        child_pid = int(child_pid_file.read_text())
        monkeypatch.setitem(jobs._runs, "kb-preview",
                            jobs.JobRun(status="running", pid=proc.pid, proc=proc))

        await jobs.stop("kb-preview")

        assert not jobs._windows_pid_is_running(proc.pid)
        assert not jobs._windows_pid_is_running(child_pid)
    finally:
        if jobs._windows_pid_is_running(proc.pid):
            subprocess.run(("taskkill", "/PID", str(proc.pid), "/T", "/F"),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def test_classifier_stop_rejects_a_stale_or_reused_pid(tmp_path, monkeypatch):
    """A stale classifier PID file must never kill an unrelated process reusing that PID."""
    from scripts import windows_classifier

    state_path = tmp_path / "data" / "classifier-windows.json"
    state_path.parent.mkdir()
    state_path.write_text(
        '{"pid": 2468, "executable": "C:\\\\venv\\\\python.exe", "created": 123}',
        encoding="utf-8",
    )
    killed = []
    monkeypatch.setattr(
        windows_classifier,
        "process_identity",
        lambda pid: windows_classifier.ProcessIdentity(
            pid=pid, executable=Path(r"C:\venv\python.exe"), created=999
        ),
    )
    monkeypatch.setattr(windows_classifier, "kill_tree", lambda pid: killed.append(pid))

    assert windows_classifier.stop(tmp_path) == 0
    assert killed == []
    assert not state_path.exists()


@pytest.mark.parametrize("kill_rc", [5, 128])
def test_classifier_failed_stop_keeps_identity_for_retry(tmp_path, monkeypatch, capsys, kill_rc):
    import json
    from scripts import windows_classifier

    state_path = tmp_path / "data" / "classifier-windows.json"
    state_path.parent.mkdir()
    saved = {"pid": 2468, "executable": str(Path("python.exe").resolve()), "created": 123}
    original = json.dumps(saved)
    state_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(windows_classifier, "process_identity", lambda pid:
                        windows_classifier.ProcessIdentity(pid, Path(saved["executable"]), 123))
    monkeypatch.setattr(windows_classifier.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], kill_rc))

    assert windows_classifier.stop(tmp_path) != 0
    assert state_path.read_text(encoding="utf-8") == original
    assert "服务已停" not in capsys.readouterr().out


async def test_restart_during_stop_cannot_orphan_the_new_job(monkeypatch, tmp_path):
    finished = asyncio.Event()
    stopping = asyncio.Event()
    release_stop = asyncio.Event()
    calls = []

    class PendingProcess(_FakeProcess):
        async def wait(self):
            await finished.wait()
            return 1

    async def create(*args, **kwargs):
        calls.append(args)
        return PendingProcess(pid=4321 + len(calls))

    async def stop_tree(proc):
        stopping.set()
        await release_stop.wait()
        finished.set()
        await proc.wait()

    monkeypatch.setattr(jobs, "LOG_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_is_windows", lambda: True)
    monkeypatch.setattr(jobs.asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr(jobs, "_stop_windows_tree", stop_tree)
    run = await jobs.start("kb-preview")
    old_watcher = run.watcher
    stop_task = asyncio.create_task(jobs.stop("kb-preview"))
    await stopping.wait()
    try:
        with pytest.raises(RuntimeError, match="正在运行中"):
            await jobs.start("kb-preview")
    finally:
        release_stop.set()
        await stop_task
        await old_watcher
        if run.watcher is not old_watcher:
            await run.watcher
    assert len(calls) == 1
    assert run.status == "stopped"
    assert run.proc is None
