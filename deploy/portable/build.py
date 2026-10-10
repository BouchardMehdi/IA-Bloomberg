"""Prepare once on a personal Windows PC; distribute ONLY the output folder."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
from urllib.request import Request, urlopen
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "out/Market-AI-Portable"


def download(url, path, digest):
    if path.exists() and sha256(path) == digest:
        return
    partial = path.with_suffix(".part")
    last = time.monotonic()
    request = Request(url, headers={"User-Agent": "MarketAI-portable-builder/1.0"})
    with urlopen(request, timeout=120) as response, partial.open("wb") as output:
        copied = 0
        while chunk := response.read(4 * 1024 * 1024):
            output.write(chunk)
            copied += len(chunk)
            if time.monotonic() - last > 5:
                print(f"Archive Ollama : {copied / 1024**2:.0f} Mo recus", flush=True)
                last = time.monotonic()
    if sha256(partial) != digest:
        raise ValueError("Archive Ollama refusee : empreinte SHA-256 incorrecte")
    partial.replace(path)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_extract(archive, destination):
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            target = (destination / item.filename).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("Unsafe archive member")
        bundle.extractall(destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-model", action="store_true", help="Download the model later with Preparer-Modele.bat")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if sys.platform != "win32" or struct.calcsize("P") != 8 or sys.version_info < (3, 12):
        raise SystemExit("Preparation requise sur Windows x64, avec Python 3.12+ (PC personnel seulement).")
    destination = args.output.resolve()
    if destination.exists():
        raise SystemExit("Dossier de sortie existant conserve. Choisir --output avec un nouveau dossier.")
    if destination == ROOT or ROOT.is_relative_to(destination):
        raise SystemExit("La sortie doit etre un nouveau sous-dossier, pas le depot ou un de ses parents.")
    cache = ROOT / "private-data/portable-build"
    cache.mkdir(parents=True, exist_ok=True)
    release = json.loads((ROOT / "deploy/portable/ollama-release.json").read_text())
    archive = cache / f"ollama-{release['version']}-windows-amd64.zip"
    print("Telechargement officiel Ollama et verification SHA-256.", flush=True)
    download(release["url"], archive, release["sha256"])
    environment = cache / "venv"
    if not (environment / "Scripts/python.exe").exists():
        venv.create(environment, with_pip=True)
    python = environment / "Scripts/python.exe"
    build_env = dict(os.environ)
    # Retain valid corporate CA configuration; discard only broken file paths.
    # pip then uses its normal verified certificate store, never --trusted-host.
    for name in ("PIP_CERT", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_CERT_FILE"):
        if build_env.get(name) and not Path(build_env[name]).is_file():
            build_env.pop(name)
    subprocess.run([python, "-m", "pip", "install", "-r", ROOT / "deploy/portable/requirements-build.txt"], check=True, env=build_env)
    # Fixed allow-list: neither .env, database backups, WLS exports nor existing
    # worker credentials are traversed or copied into the distribution.
    destination.mkdir(parents=True)
    subprocess.run([python, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--name", "market-ai-worker", "--paths", ROOT / "backend",
        "--distpath", destination / "runtime", "--workpath", cache / "work",
        "--specpath", cache, ROOT / "deploy/portable/worker_entry.py"], check=True)
    shutil.move(str(destination / "runtime/market-ai-worker"), destination / "runtime/worker")
    safe_extract(archive, destination / "runtime/ollama")
    for name in ("Configurer-IA.bat", "Demarrer-IA.bat", "Arreter-IA.bat", "Etat-IA.bat", "Preparer-Modele.bat"):
        shutil.copy2(ROOT / name, destination / name)
    shutil.copy2(ROOT / "deploy/portable/LIRE-MOI.txt", destination / "LIRE-MOI.txt")
    for name in ("config", "data/models", "data/logs"):
        (destination / name).mkdir(parents=True, exist_ok=True)
    write_manifest = {"ollama": release, "prompt_version": None, "worker_sha256": None,
        "target": "Windows x64", "configuration_included": False}
    executable = destination / "runtime/worker/market-ai-worker.exe"
    subprocess.run([executable, "self-test"], check=True)
    tree = ast.parse((ROOT / "backend/app/semantic/prompt.py").read_text(encoding="utf-8"))
    version = next(node.value.value for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "PROMPT_VERSION" for target in node.targets))
    write_manifest["prompt_version"] = version
    write_manifest["worker_sha256"] = sha256(executable)
    (destination / "versions.json").write_text(json.dumps(write_manifest, indent=2), encoding="utf-8")
    if not args.skip_model:
        subprocess.run([executable, "prepare-model"], check=True)
    print("Dossier transportable prepare :", destination, flush=True)
    print("Copier ce dossier ENTIER sur la cle USB, puis sur l'autre PC.")


if __name__ == "__main__":
    main()
