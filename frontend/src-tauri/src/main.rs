#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{io::{Read, Write}, net::{TcpListener, TcpStream}, sync::Mutex, time::{Duration, Instant}};
use tauri::{Manager, State};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

struct BackendState {
    port: u16,
    child: Mutex<Option<CommandChild>>,
}

#[tauri::command]
fn get_api_port(state: State<'_, BackendState>) -> u16 { state.port }

#[tauri::command]
async fn save_study_docx(filename: String, content: Vec<u8>) -> Result<Option<String>, String> {
    if content.len() > 20 * 1024 * 1024 || !content.starts_with(b"PK") {
        return Err("Word 文件无效或超过 20MB".to_string());
    }
    let name = std::path::Path::new(&filename).file_name().and_then(|name| name.to_str()).unwrap_or("zhiye-review.docx").to_string();
    tauri::async_runtime::spawn_blocking(move || {
        let selected = rfd::FileDialog::new().add_filter("Word 文档", &["docx"]).set_file_name(name).save_file();
        match selected {
            Some(path) => {
                std::fs::write(&path, content).map_err(|_| "保存失败，请检查目录权限和磁盘空间".to_string())?;
                Ok(Some(path.to_string_lossy().to_string()))
            }
            None => Ok(None),
        }
    }).await.map_err(|_| "导出操作未完成".to_string())?
}

fn wait_ready(port: u16) -> bool {
    let deadline = Instant::now() + Duration::from_secs(45);
    while Instant::now() < deadline {
        if let Ok(mut stream) = TcpStream::connect_timeout(&([127, 0, 0, 1], port).into(), Duration::from_millis(300)) {
            let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
            let _ = stream.write_all(b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n");
            let mut response = [0u8; 512];
            if let Ok(count) = stream.read(&mut response) {
                if String::from_utf8_lossy(&response[..count]).starts_with("HTTP/1.1 200") { return true; }
            }
        }
        std::thread::sleep(Duration::from_millis(150));
    }
    false
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") { let _ = window.set_focus(); }
        }))
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![get_api_port, save_study_docx])
        .setup(|app| {
            let data_dir = app.path().app_data_dir()?;
            std::fs::create_dir_all(&data_dir)?;
            let listener = TcpListener::bind("127.0.0.1:0")?;
            let port = listener.local_addr()?.port();
            drop(listener);
            let (mut events, child) = app.shell().sidecar("zhiye-backend")?
                .env("ZHIYE_PORT", port.to_string())
                .env("ZHIYE_DATA_DIR", data_dir.as_os_str())
                .env("ZHIYE_HOST", "127.0.0.1")
                // 桌面安装版始终要求用户自己填写，不继承启动终端中的云端密钥。
                .env("ZHIYE_AI_API_KEY", "")
                .env("SHUAKE_AI_API_KEY", "")
                .set_process_group(true)
                .spawn()?;
            // 丢弃后端输出，防止课件内容或第三方错误被转发到桌面日志。
            tauri::async_runtime::spawn(async move { while events.recv().await.is_some() {} });
            if !wait_ready(port) {
                let _ = child.kill();
                return Err("本地后端启动失败，请检查数据目录权限后重新打开应用".into());
            }
            app.manage(BackendState { port, child: Mutex::new(Some(child)) });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("无法启动 Zhiye");
    app.run(|handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            if let Some(state) = handle.try_state::<BackendState>() {
                if let Ok(mut child) = state.child.lock() {
                    if let Some(child) = child.take() { let _ = child.kill(); }
                }
            }
        }
    });
}
