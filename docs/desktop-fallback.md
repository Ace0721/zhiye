# 桌面保底方案：Tauri 与 Electron

## 本次状态

Windows PyInstaller 单文件后端已构建成功，真实 HTTP 冒烟测试覆盖 PDF 解析、云端兼容 SDK 的本地模拟请求、任务进度、答题、导出和设置，全部通过。

本机 Tauri 安装包构建尝试了两轮：第一轮 Cargo 拉取 crates.io 索引时出现 HTTP/2 流重置；第二轮关闭 HTTP/2 多路复用、缩短网络超时后仍停留在依赖解析。随后停止本地重试。

2026-10-22 后续验证：GitHub Actions 已成功构建 Windows MSI、macOS ARM64 和 Intel DMG，证明本次本机阻断来自下载环境，已无需切换框架。Windows MSI 在本机解包后，主程序与随附后端能正常启动，数据写入 AppData、端口动态分配、初始 API Key 为空。以下保留方案对比作为工程参考。

## 对比

| 项目 | 保留 Tauri 2 + PyInstaller | Electron + PyInstaller 保底 |
| --- | --- | --- |
| 现有工作 | 桌面入口、动态端口、AppData、进程组回收、导出对话框及 CI 已提供 | 可复用 React、FastAPI、SQLite、Prompt 与已验证 sidecar |
| UI 运行时 | 使用系统 WebView | 随应用分发 Chromium 与 Node.js |
| 构建依赖 | Rust、系统 C++ 工具、PyInstaller | Node、Electron 打包工具、PyInstaller |
| 本地后端 | Rust shell 插件启动进程组 | 主进程使用 child_process 启动 sidecar |
| 安装体积 | 不额外分发 Chromium，通常更小 | 增加 Chromium/Node，通常明显更大，需实测 |
| 端口与目录 | invoke 获取端口，app_data_dir 获取目录 | preload IPC 暴露端口，app.getPath('userData') 获取目录 |
| 导出 | 原生保存对话框，自定义 Rust 命令写文件 | 主进程保存对话框和文件写入 |
| 安全边界 | 本地窗口仅可调用限定命令 | 需开启 contextIsolation、禁用 renderer 的 nodeIntegration、仅暴露必要 IPC |
| 安装包 | 当前目标 MSI / DMG | 可选 electron-builder 的 MSI / DMG，需新增并验证构建配置 |
| 当前网络问题 | crates.io 下载阻断了本机验证 | 换框架仍需下载 Electron、打包工具；不能保证解决当前网络问题 |

## 本次采用的处理

保留用户指定的 Tauri 默认技术栈和已验证的 PyInstaller 后端。GitHub Actions 的 Windows、macOS ARM64、macOS Intel 构建矩阵均已产出安装包。仓库地址为 https://github.com/Ace0721/zhiye，安装包由 Releases 提供。

Electron 目前是保底设计对比，没有自动替换技术栈或生成未经验证的第二套桌面应用。如果后续采用它，最小迁移应只增加 main/preload、动态端口启动与退出回收、保存对话框及 electron-builder 配置，业务后端和 React 页面继续复用。PyInstaller onefile 的父子进程必须整体终止，不能只 kill 引导父进程。

参考：[Tauri sidecar](https://v2.tauri.app/develop/sidecar/)、[Electron 进程模型](https://www.electronjs.org/docs/latest/tutorial/process-model)、[Electron 安全建议](https://www.electronjs.org/docs/latest/tutorial/security)、[Electron 分发](https://www.electronjs.org/docs/latest/tutorial/application-distribution)。
