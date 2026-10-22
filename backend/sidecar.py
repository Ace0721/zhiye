"""PyInstaller 单文件入口，仅监听回环地址；环境在进程启动前由 Tauri 注入。"""

import multiprocessing


def main() -> None:
    multiprocessing.freeze_support()
    import uvicorn
    from app.config import settings
    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=settings.port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
