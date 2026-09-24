"""Launch the local Streamlit UI using the active Python interpreter."""

import subprocess
import sys
from pathlib import Path

import academic_pdf_translator

if __name__ == "__main__":
    ui = Path(academic_pdf_translator.__file__).parent / "ui.py"
    raise SystemExit(
        subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ui),
                "--server.address=127.0.0.1",
                "--server.headless=true",
                "--browser.gatherUsageStats=false",
                *sys.argv[1:],
            ]
        )
    )
