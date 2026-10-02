"""Explicit pinned source builds. All upstream files/tools/caches remain gitignored inside this repo."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "examples/open-source/real-app-suite"
PINS = {
    "it-tools": ("https://github.com/CorentinTh/it-tools.git", "d505845f918e946ec300af7b36efc107e2f66e9e"),
    "memos": ("https://github.com/usememos/memos.git", "e17cd163c6c37726f8397c8f426d585b540c9562"),
}
GO_ARCHIVE = "go1.27.1.darwin-arm64.tar.gz"
GO_SHA256 = "ee215d57e0ec269c60cc9ceca68e6bda321ba9ee5afe24f4b0988703c2d87d12"


def build_environment():
    env = dict(os.environ)
    for key, directory in {
        "GOPATH": "toolchain/gopath", "GOMODCACHE": "go-mod", "GOCACHE": "go-build",
        "GOTMPDIR": "tmp", "TMPDIR": "tmp", "npm_config_cache": "npm-cache",
        "XDG_CACHE_HOME": "cache", "XDG_DATA_HOME": "data", "XDG_CONFIG_HOME": "config",
        "TEST_TELEMETRY_DIR": "config/go-telemetry",
    }.items():
        env[key] = str(WORKSPACE / directory)
    env.update(GOTOOLCHAIN="local", GOENV="off", CI="true", npm_config_update_notifier="false")
    return env


def run(command, cwd=None, log="prepare.log"):
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    with (WORKSPACE / log).open("a") as stream:
        subprocess.run([str(arg) for arg in command], cwd=cwd, env=build_environment(),
                       stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=1800)


def ensure_repository(directory, upstream, commit):
    if not directory.exists():
        run(["git", "clone", "--no-checkout", "--filter=blob:none", upstream, directory])
        run(["git", "-C", directory, "checkout", "--detach", commit])
    actual = subprocess.check_output(["git", "-C", str(directory), "rev-parse", "HEAD"], text=True).strip()
    if actual != commit:
        raise ValueError(f"Unexpected upstream revision in {directory}; do not reset existing checkout")


def prepare(install=False):
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    env = build_environment()
    for key in ("GOPATH", "GOMODCACHE", "GOCACHE", "GOTMPDIR", "TMPDIR", "npm_config_cache",
                "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "TEST_TELEMETRY_DIR"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    for name, (upstream, commit) in PINS.items():
        ensure_repository(WORKSPACE / name, upstream, commit)
    if install:
        tools = WORKSPACE / "toolchain"
        run(["npm", "install", "--prefix", tools, "--cache", WORKSPACE / "npm-cache",
             "--no-audit", "--no-fund", "pnpm@9.11.0"], log="pnpm-prepare.log")
        pnpm = tools / "node_modules/.bin/pnpm"
        for name, app in [("it-tools", WORKSPACE / "it-tools"), ("memos", WORKSPACE / "memos/web")]:
            run([pnpm, "--dir", app, "install", "--frozen-lockfile", "--store-dir", WORKSPACE / "pnpm-store"],
                log=f"{name}-install.log")
            run([pnpm, "--dir", app, "run", "build" if name == "it-tools" else "release"], log=f"{name}-web-build.log")
        go = tools / "go/bin/go"
        if not go.is_file():
            if (platform.system(), platform.machine()) != ("Darwin", "arm64"):
                raise ValueError("Bundled toolchain preparation verified only for macOS arm64")
            archive = tools / GO_ARCHIVE
            run(["curl", "-fL", "--max-time", "300", "https://go.dev/dl/" + GO_ARCHIVE, "-o", archive], log="go-download.log")
            if hashlib.sha256(archive.read_bytes()).hexdigest() != GO_SHA256:
                raise ValueError("Official Go archive checksum mismatch")
            with tarfile.open(archive) as source:
                source.extractall(tools, filter="data")
        run([go, "build", "-o", WORKSPACE / "memos-server", "./cmd/memos"],
            cwd=WORKSPACE / "memos", log="memos-go-build.log")
    for output in (WORKSPACE / "it-tools/dist/index.html", WORKSPACE / "memos-server"):
        if not output.is_file():
            raise ValueError("Sample not built; explicitly run with --install: " + str(output))
    return {name: {"upstream": upstream, "commit": commit} for name, (upstream, commit) in PINS.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    print(json.dumps(prepare(parser.parse_args().install), indent=2))
