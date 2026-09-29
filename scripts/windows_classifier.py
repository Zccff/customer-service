"""Own the Windows classifier service by executable and process creation time."""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
import urllib.request
from ctypes import wintypes
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    executable: Path
    created: int


class _FileTime(ctypes.Structure):
    _fields_ = (("low", wintypes.DWORD), ("high", wintypes.DWORD))

    def as_int(self) -> int:
        return (self.high << 32) | self.low


def process_identity(pid: int) -> ProcessIdentity | None:
    if os.name != "nt":
        return None
    kernel32 = ctypes.windll.kernel32
    # HANDLE is pointer-sized; ctypes otherwise assumes a 32-bit integer return.
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel32.GetProcessTimes.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(_FileTime), ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime), ctypes.POINTER(_FileTime))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        created, exited, kernel, user = _FileTime(), _FileTime(), _FileTime(), _FileTime()
        if not kernel32.GetProcessTimes(
            handle, ctypes.byref(created), ctypes.byref(exited),
            ctypes.byref(kernel), ctypes.byref(user)
        ):
            return None
        return ProcessIdentity(pid=pid, executable=Path(buffer.value), created=created.as_int())
    finally:
        kernel32.CloseHandle(handle)


def _state_path(repo_root: Path) -> Path:
    return repo_root / "data" / "classifier-windows.json"


def _same_process(saved: dict, current: ProcessIdentity | None) -> bool:
    if current is None:
        return False
    try:
        return (
            int(saved["pid"]) == current.pid
            and int(saved["created"]) == current.created
            and os.path.normcase(os.path.abspath(saved["executable"]))
            == os.path.normcase(os.path.abspath(current.executable))
        )
    except (KeyError, TypeError, ValueError):
        return False


def _load_state(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _healthy(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8110/healthz", timeout=timeout) as response:
            return response.status == 200
    except OSError:
        return False


def kill_tree(pid: int) -> None:
    completed = subprocess.run(
        ("taskkill", "/PID", str(pid), "/T", "/F"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"taskkill failed (pid {pid}, rc {completed.returncode})")


def start(repo_root: Path, python: Path, env: dict[str, str]) -> int:
    state_path = _state_path(repo_root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    saved = _load_state(state_path)
    if saved and _same_process(saved, process_identity(int(saved.get("pid", 0)))):
        print(f"分类器服务已在运行(pid {saved['pid']})")
        return 0
    state_path.unlink(missing_ok=True)
    if _healthy():
        print("端口 8110 已被未登记进程占用，拒绝覆盖")
        return 1

    log_path = repo_root / "log" / "classifier.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab", buffering=0) as log:
        proc = subprocess.Popen(
            (str(python), str(repo_root / "scripts" / "ch10" / "serve.py")),
            cwd=repo_root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
                           | getattr(subprocess, "DETACHED_PROCESS", 0x8)),
            close_fds=True,
        )
    identity = process_identity(proc.pid)
    if identity is None:
        print("分类器进程启动后立即退出，请查看 log/classifier.log")
        return 1
    state_path.write_text(
        json.dumps({**asdict(identity), "executable": str(identity.executable)}, ensure_ascii=False),
        encoding="utf-8",
    )
    for _ in range(30):
        if _healthy():
            print(f"分类器服务已拉起: :8110(pid {proc.pid})")
            return 0
        if process_identity(proc.pid) is None:
            break
        time.sleep(1)
    if _same_process(_load_state(state_path) or {}, process_identity(proc.pid)):
        try:
            kill_tree(proc.pid)
        except (OSError, RuntimeError) as exc:
            print(f"Classifier cleanup failed; identity retained for retry: {exc}")
            return 1
    state_path.unlink(missing_ok=True)
    print("分类器服务未就绪，请查看 log/classifier.log")
    return 1


def stop(repo_root: Path) -> int:
    state_path = _state_path(repo_root)
    saved = _load_state(state_path)
    if saved:
        try:
            pid = int(saved.get("pid", 0))
        except (TypeError, ValueError):
            pid = 0
        current = process_identity(pid) if pid > 0 else None
        if _same_process(saved, current):
            try:
                kill_tree(pid)
            except (OSError, RuntimeError) as exc:
                print(f"Classifier stop failed; identity retained for retry: {exc}")
                return 1
            print("分类器服务已停")
        else:
            print("分类器 PID 记录已失效；未终止任何进程")
    else:
        print("分类器服务未登记")
    state_path.unlink(missing_ok=True)
    return 0
