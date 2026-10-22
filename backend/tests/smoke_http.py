"""真实 HTTP 冒烟：独立后端进程 + 本地模拟 API + curl，不访问云端。"""

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from reportlab.pdfgen import canvas
from docx import Document


class TemporaryWorkspace(tempfile.TemporaryDirectory):
    def cleanup(self) -> None:
        # Windows 在终止进程树后可能稍晚才释放 SQLite 文件句柄。
        for attempt in range(30):
            try:
                super().cleanup()
                return
            except PermissionError:
                if attempt == 29:
                    raise
                time.sleep(0.1)


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_POST(self) -> None:
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.path == "/v1/chat/completions"
        assert request["model"] == "smoke-model"
        time.sleep(0.1)
        card = {
            "title": "牛顿第二定律", "plain_explanation": "力越大，加速度越大。质量越大，越难加速。",
            "key_point": "合力等于质量乘加速度", "question": "质量一定时合力加倍，加速度如何变化？",
            "options": ["加倍", "减半", "不变", "变为四倍"], "correct_index": 0,
            "reexplain": "推同一辆车，用两倍合力就获得两倍加速度。",
        }
        data = json.dumps({
            "id": "smoke", "object": "chat.completion", "created": 0, "model": "smoke-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps([card], ensure_ascii=False)},
                         "finish_reason": "stop"}],
        }, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    """临时目录和进程均由脚本回收，真实密钥不参与测试。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path)
    args = parser.parse_args()
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if curl is None:
        raise RuntimeError("此验收脚本需要 curl")
    backend_port = free_port()
    mock = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    thread = threading.Thread(target=mock.serve_forever, daemon=True)
    thread.start()
    try:
        with TemporaryWorkspace(prefix="zhiye-smoke-") as temporary:
            root = Path(temporary)
            path = root / "20-pages.pdf"
            document = canvas.Canvas(str(path))
            for page in range(1, 21):
                for line in range(15):
                    document.drawString(40, 780 - line * 25, f"Page {page}, topic {line}: Newton second law F = ma; force equals mass times acceleration.")
                document.showPage()
            document.save()
            env = os.environ.copy()
            env.update(ZHIYE_PORT=str(backend_port), ZHIYE_DATA_DIR=str(root / "data"),
                       ZHIYE_AI_BASE_URL=f"http://127.0.0.1:{mock.server_port}/v1",
                       ZHIYE_AI_API_KEY="smoke-test-placeholder", ZHIYE_AI_MODEL="smoke-model",
                       ZHIYE_AI_TIMEOUT="10", ZHIYE_AI_CONCURRENCY="3", ZHIYE_TASK_TIMEOUT="30")
            command = [str(args.binary.resolve())] if args.binary else [sys.executable, "-m", "app.main"]
            process = subprocess.Popen(command,
                                       cwd=Path(__file__).resolve().parents[1], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                       start_new_session=os.name != "nt")

            def request(endpoint: str, *arguments: str) -> Any:
                result = subprocess.run([curl, "--fail-with-body", "--silent", "--show-error", "--max-time", "5",
                                         *arguments, f"http://127.0.0.1:{backend_port}{endpoint}"],
                                        capture_output=True, check=True)
                return json.loads(result.stdout)

            try:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("后端进程启动失败")
                    try:
                        request("/api/health")
                        break
                    except subprocess.CalledProcessError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError("后端健康检查超时")
                started = time.monotonic()
                uploaded = request("/api/upload", "-F", f"file=@{path}")
                states = []
                for _ in range(150):
                    state = request(f"/api/tasks/{uploaded['task_id']}")
                    states.append((state["status"], state["progress"], state["done_blocks"]))
                    if state["status"] in {"completed", "failed"}:
                        break
                    time.sleep(0.1)
                assert state["status"] == "completed", state
                cards = request(f"/api/decks/{state['deck_id']}/cards")
                assert state["done_blocks"] == state["total_blocks"] >= 3
                assert len(cards) == state["card_count"] > 0
                assert all(card["correct_index"] == 0 for card in cards)
                answer = request(f"/api/cards/{cards[0]['id']}/answer", "-H", "Content-Type: application/json", "-d", '{"selected_index":1}')
                assert answer["is_correct"] is False
                wrong = request(f"/api/decks/{state['deck_id']}/wrong")
                assert len(wrong) == 1
                summary = request(f"/api/decks/{state['deck_id']}/summary")
                assert "考前救命包" in summary["markdown"]
                assert summary["wrong_count"] == 1
                material = request(f"/api/decks/{state['deck_id']}/study")
                assert material["points"]
                exported = subprocess.run([curl, "--fail-with-body", "--silent", "--max-time", "10",
                                           f"http://127.0.0.1:{backend_port}/api/decks/{state['deck_id']}/study.docx"],
                                          capture_output=True, check=True)
                word = Document(BytesIO(exported.stdout))
                assert any(paragraph.text == "重点速记" for paragraph in word.paragraphs)
                settings = request("/api/settings")
                assert settings["api_key_configured"] and "api_key" not in settings
                assert request("/api/settings/test", "-X", "POST")["success"]
                print(json.dumps({"result": "PASS", "pages": 20, "blocks": state["total_blocks"],
                                  "cards": len(cards), "states": states,
                                  "frozen_binary": bool(args.binary), "review_export_settings": "PASS", "study_word": "PASS",
                                  "elapsed_seconds": round(time.monotonic() - started, 2),
                                  "api": "local mock; no cloud performance claim"}))
            finally:
                # 单文件引导程序会再拉起子进程，必须清理整棵测试进程树。
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                elif process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)
    finally:
        mock.shutdown()
        mock.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
