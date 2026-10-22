# 验收记录

日期：2026-10-22。已完成的检查与仍未验证的目标分别列出，模拟 AI 不代表真实云端性能。

| 范围 | 结果 | 证据与限制 |
| --- | --- | --- |
| 后端自动化 | 通过 | Python 3.11.17，pytest 64 项，新增考前救命包 Word 下载、错题排序/跨课件隔离、零错题速记与特殊字符；其余覆盖独立 AI 整理、缓存、并发、重试和任务恢复 |
| 前端工具函数 | 通过 | Vitest 3 项，包含上传限制、进度文字、导出文件名 |
| 前端生产构建 | 通过 | TypeScript 严格检查 + Vite build |
| 前端依赖检查 | 通过 | npm audit 报告 0 项漏洞；这是本次检查结果，不代表永久保证 |
| 浏览器学习闭环 | 通过 | 上传 20 页合成 PDF → 进度 1% 解析 → 出卡 → 答错记录 → 队尾回炉 → 完成 → Markdown 下载 |
| 设置界面 | 通过 | 本地模拟 API 测试连接成功、保存反馈正常、密钥输入为空不回显 |
| 复习工作台 | 通过 | 浏览器检查知识点展开、搜索后仅显示匹配节点、详情切换、资料预览及 Word 下载反馈；复用生成的知识点，本地整理不再次调用 AI |
| Word 文档结构 | 通过 | 导出后用 python-docx 重新打开，校验标题、重点速记、简明解释和个人错题补充；当前环境未安装 Word/LibreOffice，尚未验证真实 Office 打印分页 |
| v0.2.0 Windows 包 | 通过 | 从 GitHub Actions 获取 MSI 构建产物，ZIP SHA256 与 GitHub artifact digest 一致；解包成功，使用包内单文件后端运行 20 页合成课件完整 HTTP 流程，包含复习资料 JSON 和 Word 下载后重新打开校验；主程序原生 Word 保存对话框仍需安装后实测 |
| v0.3.0 独立整理 | 通过模拟验证 | 20页合成课件通过独立提纲与导图生成接口、进度轮询、缓存、Word下载及重新打开；使用模拟API验证调用链，不作为真实模型的归纳质量证据 |
| v0.3.0 界面 | 通过 | 使用人工构造的结构化示例检查两侧导图、展开、按关系搜索自动展开父路径、精简提纲预览与下载；[导图截图](screenshots/semantic-map.png)、[提纲截图](screenshots/ai-notes.png)是界面验收数据，不是一次真实AI输出 |
| v0.3.0 发布 | 通过 | [Release v0.3.0](https://github.com/Ace0721/zhiye/releases/tag/v0.3.0) 的 Windows x64 MSI 与两种 macOS DMG 均已公开发布；下载的 Windows 构建 ZIP、MSI 的 SHA256 分别与 GitHub artifact digest、Release asset digest 一致，MSI 解包成功 |
| v0.3.0 包内后端 | 通过 | 使用发布 MSI 中的 zhiye-backend.exe，通过20页合成课件上传、两次独立复习生成、真实进度查询及 Word 下载/重新打开；云端由本地模拟接口替代，真实模型的内容质量尚待课件实测 |
| v0.3.1 救命包 Word | 通过源码验证 | 页面已移除 Markdown 下载/复制，改为结构化预览和 `.docx` 下载；浏览器点击下载正常，文档重新打开后包含按错题次数排序的重点、正确答案和补充解释，无错题时含全课重点速记，不调用 AI |
| 手机宽度 | 通过 | 390 × 844，知识卡可滚动、按钮可见，documentWidth = viewport = 390，无横向溢出 |
| 断线提示 | 通过 | 停止本地后端后刷新刷卡页，显示“连接中断，请检查网络和后端服务，然后重试”，保留重试和返回入口，无白屏 |
| Docker 构建 | 通过 | Python 3.11 / Node 22 / Nginx 多阶段镜像构建成功；初次 Docker Hub 不可达后，通过官方镜像缓存预拉取 |
| Docker 启动与接口 | 通过 | Compose up --wait、健康检查、Nginx 同源代理、设置测试、上传、卡片、答题和导出通过；本机默认 8080 被其他服务占用，验收使用空闲临时端口 |
| Docker 持久化 | 通过 | 重启 backend 后，错题、卡片及配置仍可查询；测试数据使用独立目录，测试容器已停止清理 |
| Windows 单文件后端 | 通过 | PyInstaller --onefile 构建；直接运行 EXE，通过 20 页合成 PDF 的真实 HTTP/curl 闭环，不调用本机 Python 作为服务器 |
| Windows MSI | 构建及启动通过 | GitHub runner 已生成 MSI；本机校验构建 ZIP 的 SHA256 后解包，启动桌面主程序成功，随附后端动态端口健康检查成功，AppData 数据库存在，初始 API Key 为空 |
| macOS DMG | 构建通过 | GitHub macos-14 ARM64 与 macos-15-intel runner 均已生成 DMG；本机为 Windows，尚未在真实 Mac 上安装体验 |
| 安装后端到端 | 部分验证 | Windows 包已解包启动，内含主程序与单文件后端；尚未在无 Python/Node 的全新系统执行完整安装向导与真实 AI 学习流程 |
| GitHub Release | 已发布 | [v0.1.0](https://github.com/Ace0721/zhiye/releases/tag/v0.1.0) 已公开发布，包含 Windows x64 MSI、Apple Silicon DMG 和 Intel Mac DMG；三个构建任务及发布任务均成功 |
| 真实厂商连接 | 未验证 | 没有用户提供的有效 API Key，未请求 DeepSeek / Kimi / 通义 / OpenAI 真实服务 |
| 20 页一分钟目标 | 未验证 | 本地模拟 API 的数秒耗时不作为真实云端性能证据；还需真实课件与有效 API 配置 |

## 复现

后端：`cd backend` 后运行 `.venv/Scripts/python.exe -m pytest -q`。

前端：`cd frontend` 后运行 `npm ci`、`npm test`、`npm run build`、`npm audit`。

HTTP：从 backend 运行 `.venv/Scripts/python.exe tests/smoke_http.py`。

单文件后端：从 backend 运行 `.venv/Scripts/python.exe tests/smoke_http.py --binary dist/zhiye-backend.exe`。脚本使用本地模拟 API，并清理整个测试进程树。

Docker：`docker compose up --build -d`，在设置页配置 AI；按 README 修改占用端口。测试停止使用 `docker compose down`，不删除数据。

截图：[首页](screenshots/home.png)、[手机刷卡](screenshots/mobile-swipe.png)、[救命包](screenshots/summary.png)。

桌面：[Tauri / Electron 保底对比](desktop-fallback.md)。
