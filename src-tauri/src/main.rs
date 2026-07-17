#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use local_english_trainer_desktop::{
    app_lifecycle::AppSidecarLifecycle,
    learning_proxy::ReadingPackSummary,
    resource_probe,
};
use std::{
    io::Write,
    sync::Arc,
    thread,
    time::{Duration, Instant},
};
use tauri::{Manager, State, WindowEvent};

const PROXY_PROBE_TIMEOUT: Duration = Duration::from_secs(20);

#[tauri::command]
fn list_reading_packs(
    lifecycle: State<'_, Arc<AppSidecarLifecycle>>,
) -> Result<Vec<ReadingPackSummary>, String> {
    lifecycle.list_reading_packs_command()
}

fn proxy_probe_enabled(lifecycle_enabled: bool) -> bool {
    lifecycle_enabled
        && std::env::var("LOCAL_ENGLISH_TRAINER_PROXY_PROBE").as_deref() == Ok("1")
}

fn start_proxy_probe(lifecycle: Arc<AppSidecarLifecycle>, app_handle: tauri::AppHandle) {
    thread::spawn(move || {
        let deadline = Instant::now() + PROXY_PROBE_TIMEOUT;
        let result = loop {
            match lifecycle.list_reading_packs_command() {
                Ok(packs) => break Ok(packs.len()),
                Err(_) if Instant::now() < deadline => thread::sleep(Duration::from_millis(100)),
                Err(_) => break Err(()),
            }
        };
        match result {
            Ok(count) => {
                eprintln!("LET_PROXY_READING_PACKS_OK count={count}");
                let _ = std::io::stderr().flush();
            }
            Err(()) => {
                eprintln!("LET_PROXY_READING_PACKS_FAILED");
                let _ = std::io::stderr().flush();
            }
        }
        if lifecycle.request_close().must_prevent_close() {
            lifecycle.start_shutdown_background(app_handle);
        } else {
            app_handle.exit(1);
        }
    });
}

fn main() {
    let lifecycle_enabled = std::env::var("LOCAL_ENGLISH_TRAINER_SIDECAR_LIFECYCLE_PROBE").as_deref() == Ok("1");
    let lifecycle = AppSidecarLifecycle::new(lifecycle_enabled);

    let lifecycle_for_setup = Arc::clone(&lifecycle);
    let lifecycle_for_proxy_probe = Arc::clone(&lifecycle);
    let proxy_probe = proxy_probe_enabled(lifecycle_enabled);

    tauri::Builder::default()
        .manage(Arc::clone(&lifecycle))
        .invoke_handler(tauri::generate_handler![list_reading_packs])
        .setup(move |app| {
            if std::env::var("LOCAL_ENGLISH_TRAINER_RESOURCE_PROBE").as_deref() == Ok("1") {
                let resource_dir = app.path().resource_dir().map_err(|_| std::io::Error::other("resource probe could not resolve resource_dir"))?;
                resource_probe::verify_resource_dir(&resource_dir).map_err(std::io::Error::other)?;
                eprintln!("LOCAL_ENGLISH_TRAINER_RESOURCE_PROBE success");
            }
            if lifecycle_for_setup.enabled() {
                let resource_dir = app.path().resource_dir().map_err(|_| std::io::Error::other("lifecycle probe could not resolve resource_dir"))?;
                lifecycle_for_setup.start_background(resource_dir);
            }
            if proxy_probe {
                start_proxy_probe(Arc::clone(&lifecycle_for_proxy_probe), app.handle().clone());
            }
            Ok(())
        })
        .on_window_event(move |window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                if lifecycle.request_close().must_prevent_close() {
                    api.prevent_close();
                    lifecycle.start_shutdown_background(window.app_handle().clone());
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Local English Trainer");
}