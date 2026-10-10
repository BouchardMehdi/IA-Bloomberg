"""Windows portable controller: own processes only, no Docker or installed Python."""
import argparse
import asyncio
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

import httpx
import psutil

from app.worker.main import api_url, serve

MODEL = "qwen3:4b-instruct"
PORT = 11435


class UserError(ValueError):
    """Safe, deliberately written message; never provider/configuration input."""


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    for attempt in range(20):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.02)


def read_json(path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def configuration(root):
    data = read_json(root / "config/worker.json")
    if not data:
        raise UserError("Lancez Configurer-IA.bat une fois avant de demarrer.")
    if not isinstance(data, dict) or not isinstance(data.get("site_url"), str) or not isinstance(data.get("token"), str):
        raise UserError("Configuration du worker invalide.")
    api_url(data["site_url"])
    if len(data["token"]) < 32 or data.get("model") != MODEL:
        raise UserError("Configuration du worker invalide ou modele incompatible.")
    return data


def configure(root, site=None):
    path = root / "config/worker.json"
    if path.exists():
        data = configuration(root)
        print("Configuration existante conservee :", data["site_url"])
        print("Aucun nouveau jeton genere. Vous pouvez changer de PC avec ce dossier.")
        return
    site = (site or input("Adresse HTTPS du site VPS : ")).strip().rstrip("/")
    api_url(site)
    token = secrets.token_hex(32)
    write_json(path, {"site_url": site, "token": token, "model": MODEL})
    digest = hashlib.sha256(token.encode()).hexdigest()
    (root / "config/vps-worker.txt").write_text(
        "# Empreinte a reporter dans private-data/vps.env sur le VPS, puis relancer ses services.\n"
        f"AI_WORKER_TOKEN_SHA256={digest}\nOLLAMA_MODEL={MODEL}\n", encoding="utf-8")
    print("Configuration enregistree. Aucun secret affiche.")
    print("Reportez config/vps-worker.txt dans la configuration du VPS.")
    print("Gardez config/worker.json prive. Ne le transmettez pas au VPS.")


def current_process(state, root):
    """A copied state or reused PID must never authorize killing another process."""
    if not isinstance(state, dict) or not isinstance(state.get("boot_time"), (float, int)) or abs(state["boot_time"] - psutil.boot_time()) > 2:
        return None
    run_id = state.get("run_id", "")
    if not isinstance(run_id, str) or len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
        return None
    try:
        process = psutil.Process(state["pid"])
        expected = (root / "runtime/worker/market-ai-worker.exe").resolve()
        if (Path(process.exe()).resolve() != expected or
                process.create_time() != state["created_at"] or
                "_run" not in process.cmdline() or state["run_id"] not in process.cmdline()):
            return None
        return process if process.is_running() else None
    except (psutil.Error, KeyError, OSError):
        return None


def check_port():
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", PORT))
        except OSError:
            raise UserError(f"Le port local {PORT} est deja utilise. Aucun autre Ollama ne sera arrete.") from None


def environment(root):
    env = dict(os.environ)
    env.update(OLLAMA_HOST=f"127.0.0.1:{PORT}", OLLAMA_MODELS=str(root / "data/models"),
        OLLAMA_NO_CLOUD="1", OLLAMA_NOHISTORY="1", OLLAMA_DEBUG="-1",
        OLLAMA_DEBUG_LOG_REQUESTS="0", OLLAMA_KEEP_ALIVE="60s",
        OLLAMA_NUM_PARALLEL="1", OLLAMA_MAX_LOADED_MODELS="1")
    # Explicitly discard worker credentials possibly inherited from another launch.
    env.pop("AI_WORKER_TOKEN", None)
    return env


class WindowsJob:
    """Close this Windows job to stop only Ollama and its inference subprocesses."""
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [("ProcessTime", ctypes.c_int64), ("JobTime", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD), ("MinWorkingSet", ctypes.c_size_t),
                ("MaxWorkingSet", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]
        class Io(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]
        class Extended(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("Io", Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError("Impossible de creer le groupe de processus Windows")
        info = Extended()
        info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise OSError("Impossible de proteger l'arret des processus Ollama")

    def attach(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            process.terminate()
            process.wait(timeout=10)
            raise OSError("Impossible d'associer Ollama au groupe de processus")

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def rotate_ollama_logs(directory):
    path = directory / "ollama.log"
    if path.exists() and path.stat().st_size > 2_000_000:
        path.replace(directory / "ollama.previous.log")


async def run(root, run_id, mode):
    import msvcrt
    state_path = root / "data/state.json"
    stop_path = root / f"data/stop-{run_id}"
    root.joinpath("data/logs").mkdir(parents=True, exist_ok=True)
    root.joinpath("data/models").mkdir(parents=True, exist_ok=True)
    # OS lock is released on crash. Competing starts cannot overwrite active state.
    with (root / "data/run.lock").open("a+b") as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return
        state = {"pid": os.getpid(), "created_at": psutil.Process().create_time(),
            "boot_time": psutil.boot_time(), "run_id": run_id, "phase": "starting"}
        write_json(state_path, state)
        job, ollama = None, None
        try:
            check_port()
            rotate_ollama_logs(root / "data/logs")
            job = WindowsJob()
            with (root / "data/logs/ollama.log").open("ab") as log:
                ollama = subprocess.Popen([str(root / "runtime/ollama/ollama.exe"), "serve"],
                    cwd=root, env=environment(root), stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                job.attach(ollama)
                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{PORT}", timeout=5, trust_env=False) as http:
                    async def workload():
                        for _ in range(90):
                            if ollama.poll() is not None:
                                raise RuntimeError("ollama_start_failed")
                            try:
                                response = await http.get("/api/tags")
                                response.raise_for_status()
                                break
                            except httpx.HTTPError:
                                await asyncio.sleep(1)
                        else:
                            raise RuntimeError("ollama_start_timeout")
                        response = await http.post("/api/show", json={"model": MODEL})
                        if response.status_code == 404:
                            state["phase"] = "downloading_model"
                            write_json(state_path, state)
                            async with http.stream("POST", "/api/pull", json={"model": MODEL, "stream": True}, timeout=1800) as stream:
                                stream.raise_for_status()
                                async for line in stream.aiter_lines():
                                    if line:
                                        progress = json.loads(line)
                                        if "error" in progress:
                                            raise RuntimeError("model_download_failed")
                                        state["download_completed"] = progress.get("completed")
                                        state["download_total"] = progress.get("total")
                                        state["download_status"] = progress.get("status", "")[:150]
                                        write_json(state_path, state)
                            response = await http.post("/api/show", json={"model": MODEL})
                        response.raise_for_status()
                        if mode == "prepare":
                            state["phase"] = "model_ready"
                            return
                        data = configuration(root)
                        os.environ.update(AI_SITE_URL=data["site_url"], AI_WORKER_TOKEN=data["token"],
                            OLLAMA_MODEL=MODEL, OLLAMA_BASE_URL=f"http://127.0.0.1:{PORT}")
                        state["phase"] = "ready"
                        write_json(state_path, state)
                        await serve()
                    task = asyncio.create_task(workload())
                    try:
                        while not task.done() and not stop_path.exists():
                            if ollama.poll() is not None:
                                raise RuntimeError("ollama_interrupted")
                            await asyncio.sleep(0.5)
                        if task.done():
                            await task
                        else:
                            state["phase"] = "stopped"
                    finally:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
        except Exception:
            # Do not print exception messages that might include credentials or source text.
            logging.error("Portable AI failed during phase %s; check the local Ollama log.", state["phase"])
            state["phase"] = "error"
        finally:
            if job:
                job.close()
            if ollama:
                try:
                    ollama.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    ollama.kill()
                    ollama.wait(timeout=10)
            stop_path.unlink(missing_ok=True)
            write_json(state_path, state)


def start(root, mode):
    state = read_json(root / "data/state.json")
    if current_process(state, root):
        print("IA deja lancee dans ce dossier. Etat :", state["phase"])
        return
    for binary in ("runtime/worker/market-ai-worker.exe", "runtime/ollama/ollama.exe"):
        if not (root / binary).is_file():
            raise UserError("Dossier portable incomplet. Relancez Preparer-Cle-USB.bat sur le PC personnel.")
    if mode == "worker":
        configuration(root)
    check_port()
    root.joinpath("data/logs").mkdir(parents=True, exist_ok=True)
    run_id = secrets.token_hex(16)
    process = subprocess.Popen([str(root / "runtime/worker/market-ai-worker.exe"), "_run", "--run-id", run_id,
        "--mode", mode], cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = read_json(root / "data/state.json")
        if state and state.get("run_id") == run_id:
            if state["phase"] == "error":
                raise UserError("Demarrage impossible. Consultez Etat-IA.bat et data/logs/ollama.log.")
            if state["phase"] != "starting":
                break
        if process.poll() is not None:
            raise UserError("Le worker n'a pas pu demarrer. Consultez Etat-IA.bat.")
        time.sleep(0.2)
    else:
        print("Demarrage en cours ; consultez Etat-IA.bat.")
    if mode == "prepare":
        print("Preparation du modele. Vous pouvez l'arreter avec Arreter-IA.bat.")
        while process.poll() is None:
            state = read_json(root / "data/state.json") or {}
            print("Modele :", state.get("phase", "starting"), state.get("download_status", ""), flush=True)
            time.sleep(10)
        state = read_json(root / "data/state.json") or {}
        if state.get("phase") != "model_ready":
            raise UserError("Preparation du modele interrompue ou echouee. Relancez Preparer-Modele.bat.")
        print("Modele pret dans data/models. Vous pouvez copier le dossier sur la cle USB.")
    else:
        print("IA lancee en arriere-plan. Etat-IA.bat indique sa progression.")


def stop(root):
    state = read_json(root / "data/state.json")
    if not current_process(state, root):
        print("Aucune IA de ce dossier en cours. Aucun autre processus arrete.")
        return
    (root / f"data/stop-{state['run_id']}").touch()
    deadline = time.monotonic() + 25
    while current_process(state, root) and time.monotonic() < deadline:
        time.sleep(0.2)
    if current_process(state, root):
        raise UserError("Arret toujours en cours. Gardez le dossier branche et relancez Etat-IA.bat.")
    print("IA arretee. Modeles conserves ; le site VPS reste disponible.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["configure", "start", "stop", "status", "prepare-model", "self-test", "_run"])
    parser.add_argument("--site")
    parser.add_argument("--run-id")
    parser.add_argument("--mode", choices=["prepare", "worker"], default="worker")
    args = parser.parse_args()
    root = Path(sys.executable).resolve().parents[2] if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[3] / "out/Market-AI-Portable"
    try:
        if args.action == "self-test":
            from app.schemas.semantic_analysis import PassageExtraction
            from app.semantic.prompt import PROMPT_VERSION
            PassageExtraction.model_validate({"events": []})
            print("Worker autonome valide :", PROMPT_VERSION)
        elif args.action == "configure":
            configure(root, args.site)
        elif args.action in ("start", "prepare-model"):
            start(root, "prepare" if args.action == "prepare-model" else "worker")
        elif args.action == "stop":
            stop(root)
        elif args.action == "status":
            state = read_json(root / "data/state.json")
            print("Processus :", "actif" if current_process(state, root) else "arrete ou etat d'un autre PC")
            print("Phase :", state.get("phase", "inconnue") if state else "pas encore lance")
            print("Journaux :", root / "data/logs")
            path = root / "data/logs/worker.log"
            if path.exists():
                print("".join(path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)[-10:]))
        else:
            if not args.run_id or len(args.run_id) != 32 or any(c not in "0123456789abcdef" for c in args.run_id):
                raise UserError("Identifiant de lancement invalide")
            root.joinpath("data/logs").mkdir(parents=True, exist_ok=True)
            logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(
                root / "data/logs/worker.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")])
            logging.getLogger("httpx").setLevel(logging.WARNING)
            asyncio.run(run(root, args.run_id, args.mode))
    except UserError as error:
        print(str(error))
        return 1
    except (ValueError, OSError, KeyError):
        # Configuration can contain a secret; never echo validation input/errors.
        print("Operation impossible : configuration, fichiers ou port indisponibles. Consultez LIRE-MOI.txt et data/logs.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
