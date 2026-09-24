"""Exercise real local HTTP plus the CLI, without pretending to test LLM quality."""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from academic_pdf_translator.pir.serializer import load_document


def test_cli_real_http_translation_and_explanation(sample_pdf, tmp_path):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, payload))
            data = json.loads(payload["messages"][1]["content"])
            if "plain_explanation" in payload["messages"][0]["content"]:
                content = json.dumps(
                    {
                        "plain_explanation": "协议测试用解释。",
                        "role_in_paper": "协议测试用作用。",
                        "key_terms": [],
                    }
                )
            else:
                content = "协议测试回显：" + data["current_text"]
            response = json.dumps(
                {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = {
        **os.environ,
        "APT_API_KEY": "local-test-only",
        "APT_MODEL": "protocol-fixture",
        "APT_API_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
        "APT_CACHE_DIR": str(tmp_path / "cache"),
        "NO_PROXY": "127.0.0.1",
        "PYTHONIOENCODING": "utf-8",
    }
    root = Path(__file__).resolve().parents[1]
    try:
        output = tmp_path / "translated"
        run = subprocess.run(
            [sys.executable, "cli.py", str(sample_pdf), "--output", str(output)],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert run.returncode == 0, run.stderr
        doc = load_document(output / "document.json")
        assert doc.status == "completed" and doc.mode == "live"
        assert all(path == "/v1/chat/completions" for path, _ in calls)
        assert all(b.explanation is None for b in doc.blocks)
        translation_call_count = len(calls)

        cached_output = tmp_path / "cached"
        run = subprocess.run(
            [sys.executable, "cli.py", str(sample_pdf), "--output", str(cached_output)],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert run.returncode == 0, run.stderr
        cached = load_document(cached_output / "document.json")
        assert len(calls) == translation_call_count
        assert cached.processing.provider_calls == 0
        assert cached.processing.cache_hits > 0
        selected = next(b for b in doc.blocks if b.text.startswith("Domain alignment"))
        run = subprocess.run(
            [
                sys.executable,
                "cli.py",
                "--pir",
                str(output / "document.json"),
                "--explain",
                selected.block_id,
                "--output",
                str(output),
            ],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert run.returncode == 0, run.stderr
        updated = load_document(output / "document.json")
        assert updated.block(selected.block_id).explanation is not None
        assert "local-test-only" not in (output / "document.json").read_text(encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
