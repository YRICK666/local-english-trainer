#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;

mod resource_probe;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            if std::env::var("LOCAL_ENGLISH_TRAINER_RESOURCE_PROBE").as_deref() == Ok("1") {
                let resource_dir = app.path().resource_dir().map_err(|error| {
                    std::io::Error::other(format!(
                        "resource probe could not resolve Tauri resource_dir: {error}"
                    ))
                })?;
                resource_probe::verify_resource_dir(&resource_dir).map_err(std::io::Error::other)?;
                eprintln!(
                    "LOCAL_ENGLISH_TRAINER_RESOURCE_PROBE success: {}",
                    resource_probe::sidecar_resource_dir(&resource_dir).display()
                );
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Local English Trainer");
}