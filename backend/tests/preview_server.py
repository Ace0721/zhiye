"""浏览器人工验收用服务，所有 AI 请求均在本机模拟，不连接云端。"""

import os
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from smoke_http import MockHandler


def main() -> None:
    mock = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    thread = threading.Thread(target=mock.serve_forever, daemon=True)
    thread.start()
    with tempfile.TemporaryDirectory(prefix="zhiye-ui-qa-") as directory:
        os.environ.update(ZHIYE_DATA_DIR=directory, ZHIYE_AI_API_KEY="ui-test-placeholder",
                          ZHIYE_AI_BASE_URL=f"http://127.0.0.1:{mock.server_port}/v1", ZHIYE_AI_MODEL="smoke-model")
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from test_parser import make_pdf
        path = Path(directory) / "sample-20-pages.pdf"
        make_pdf(path)
        print(f"QA PDF: {path}", flush=True)
        import uvicorn
        from app.main import app
        try:
            uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
        finally:
            mock.shutdown()
            mock.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
