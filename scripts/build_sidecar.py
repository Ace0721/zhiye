"""在当前平台构建单文件后端，并按 Tauri target triple 命名。"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def host_triple() -> str:
    try:
        output = subprocess.check_output(["rustc", "-vV"], text=True)
        return next(line.split(": ", 1)[1] for line in output.splitlines() if line.startswith("host: "))
    except (FileNotFoundError, subprocess.CalledProcessError):
        machine = platform.machine().lower()
        arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
        system = {"Windows": "pc-windows-msvc", "Darwin": "apple-darwin", "Linux": "unknown-linux-gnu"}[platform.system()]
        return f"{arch}-{system}"


def main() -> None:
    """不能跨操作系统打包；CI 在 Windows 和 macOS 分别执行。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default=host_triple())
    args = parser.parse_args()
    if args.target != host_triple():
        raise SystemExit("PyInstaller 不能跨平台构建，请使用目标系统和架构的 Python")
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
               "--name", "zhiye-backend", "--paths", str(backend),
               "--add-data", f"{backend / 'app' / 'prompts'}{os.pathsep}app/prompts",
               "--collect-all", "pdfplumber", "--collect-all", "pypdfium2",
               "--collect-all", "pptx", "--collect-all", "openai", "--collect-all", "docx",
               "--collect-all", "uvicorn", "--collect-all", "sqlalchemy",
               "--distpath", str(backend / "dist"), "--workpath", str(backend / "build"),
               "--specpath", str(backend / "build"), str(backend / "sidecar.py")]
    subprocess.run(command, cwd=backend, check=True)
    extension = ".exe" if platform.system() == "Windows" else ""
    directory = root / "frontend" / "src-tauri" / "binaries"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"zhiye-backend-{args.target}{extension}"
    shutil.copy2(backend / "dist" / f"zhiye-backend{extension}", target)
    target.chmod(target.stat().st_mode | 0o111)
    print(f"Sidecar: {target}")


if __name__ == "__main__":
    main()
