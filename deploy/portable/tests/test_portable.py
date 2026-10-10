import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from app.worker import portable


def test_configuration_survives_copy_and_does_not_generate_new_token(tmp_path, capsys):
    first = tmp_path / "first"
    portable.configure(first, "https://market.example.org")
    data = portable.configuration(first)
    assert len(data["token"]) == 64
    exported = (first / "config/vps-worker.txt").read_text()
    assert data["token"] not in exported
    assert hashlib.sha256(data["token"].encode()).hexdigest() in exported
    import shutil
    copied = tmp_path / "second with spaces"
    shutil.copytree(first, copied)
    portable.configure(copied, "https://different.example.org")
    assert portable.configuration(copied) == data
    assert data["token"] not in capsys.readouterr().out


@pytest.mark.parametrize("site", ["http://example.org", "https://user:password@example.org", "https://example.org/api", "https://example.org/?key=x"])
def test_configuration_rejects_unsafe_urls_without_writing_credentials(tmp_path, site):
    with pytest.raises(ValueError):
        portable.configure(tmp_path, site)
    assert not (tmp_path / "config/worker.json").exists()


@pytest.mark.parametrize("data", [{}, [], {"site_url":3}, {"site_url":"https://example.org","token":3},
    {"site_url":"https://example.org","token":"short","model":portable.MODEL}])
def test_invalid_configuration_is_not_started(tmp_path, data):
    portable.write_json(tmp_path / "config/worker.json", data)
    with pytest.raises(ValueError):
        portable.configuration(tmp_path)


def test_ollama_environment_is_local_and_does_not_change_user_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "0.0.0.0:11434")
    monkeypatch.setenv("AI_WORKER_TOKEN", "some-other-worker-token")
    result = portable.environment(tmp_path)
    assert result["OLLAMA_HOST"] == "127.0.0.1:11435"
    assert result["OLLAMA_MODELS"] == str(tmp_path / "data/models")
    assert result["OLLAMA_NO_CLOUD"] == "1"
    assert result["OLLAMA_DEBUG_LOG_REQUESTS"] == "0"
    assert result["OLLAMA_DEBUG"] == "-1"
    assert "AI_WORKER_TOKEN" not in result
    assert os.environ["OLLAMA_HOST"] == "0.0.0.0:11434"


def test_process_ownership_rejects_stale_copied_or_forged_state(tmp_path, monkeypatch):
    monkeypatch.setattr(portable.psutil, "boot_time", lambda:100)
    class Process:
        def __init__(self, pid): self.pid = pid
        def exe(self): return str(tmp_path / "runtime/worker/market-ai-worker.exe")
        def create_time(self): return 200
        def cmdline(self): return [self.exe(), "_run", "--run-id", "a" * 32]
        def is_running(self): return True
    monkeypatch.setattr(portable.psutil, "Process", Process)
    state = {"pid":1,"created_at":200,"boot_time":100,"run_id":"a" * 32}
    assert portable.current_process(state, tmp_path)
    for changes in ({"created_at":201}, {"boot_time":50}, {"run_id":"../escape"}, {"run_id":"b" * 32}):
        assert portable.current_process({**state, **changes}, tmp_path) is None
    assert portable.current_process(state, tmp_path / "another copy") is None
    assert portable.current_process(None, tmp_path) is None


def test_unknown_process_is_never_stopped(tmp_path, capsys):
    portable.write_json(tmp_path / "data/state.json", {"pid":os.getpid(),"boot_time":0,"run_id":"a"*32})
    portable.stop(tmp_path)
    assert not list((tmp_path / "data").glob("stop-*"))
    assert "Aucun autre processus" in capsys.readouterr().out


def test_port_collision_refuses_to_attach_to_existing_server(monkeypatch):
    import socket
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        monkeypatch.setattr(portable, "PORT", listener.getsockname()[1])
        with pytest.raises(ValueError, match="deja utilise"):
            portable.check_port()


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows process lifecycle")
def test_windows_job_stops_only_attached_process():
    flags = subprocess.CREATE_NO_WINDOW
    owned = subprocess.Popen([sys.executable,"-c","import time; time.sleep(120)"], creationflags=flags)
    unrelated = subprocess.Popen([sys.executable,"-c","import time; time.sleep(120)"], creationflags=flags)
    job = portable.WindowsJob()
    try:
        job.attach(owned)
        job.close()
        owned.wait(timeout=10)
        assert unrelated.poll() is None
    finally:
        job.close()
        for process in (owned, unrelated):
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)


def test_builder_rejects_archive_traversal(tmp_path):
    script = Path(__file__).resolve().parents[1] / "build.py"
    spec = importlib.util.spec_from_file_location("portable_build", script)
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.txt", "no")
    with pytest.raises(ValueError, match="Unsafe"):
        build.safe_extract(archive, tmp_path / "output")
    assert not (tmp_path / "outside.txt").exists()
