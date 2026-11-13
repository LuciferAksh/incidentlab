"""Bootstrap pinned Python and Node dependencies on Windows, macOS, and Linux."""

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    if sys.version_info < (3, 12):  # noqa: UP036 - this bootstrap runs before package installation
        raise SystemExit("IncidentLab requires Python 3.12 or newer.")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise SystemExit("Install Node.js 22.12+ or 24 LTS (including npm), then run setup again.")
    os.chdir(ROOT)
    location = ROOT / ".venv"
    if not location.exists():
        venv.EnvBuilder(with_pip=True).create(location)
    python = location / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([str(python), "-m", "pip", "install", "-r", "requirements.lock"], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "--no-deps", "-e", ".[dev]"], check=True)
    subprocess.run([npm, "ci"], check=True)
    subprocess.run([npm, "run", "build"], check=True)
    print("\nReady. Start the lab with: python scripts/dev.py --no-build")


if __name__ == "__main__":
    main()
