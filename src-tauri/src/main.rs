#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use local_english_trainer_desktop::{app_lifecycle::AppSidecarLifecycle, resource_probe};
use std::sync::Arc;
use tauri::{Manager, WindowEvent};

fn main() {
    let lifecycle_enabled = std::env::var("LOCAL_ENGLISH_TRAINER_SIDECAR_LIFECYCLE_PROBE").as_deref() == Ok("1");
    let lifecycle = AppSidecarLifecycle::new(lifecycle_enabled);

    let lifecycle_for_setup = Arc::clone(&lifecycle);

    tauri::Builder::default()
        .manage(Arc::clone(&lifecycle))
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