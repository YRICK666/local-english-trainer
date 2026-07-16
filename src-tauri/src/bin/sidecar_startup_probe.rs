use local_english_trainer_desktop::sidecar;
use std::{env, path::PathBuf, process::ExitCode};

fn main() -> ExitCode {
    match run() {
        Ok(()) => {
            eprintln!("LOCAL_ENGLISH_TRAINER_SIDECAR_STARTUP_PROBE_HEADLESS");
            eprintln!("LOCAL_ENGLISH_TRAINER_SIDECAR_STARTUP_PROBE success");
            ExitCode::SUCCESS
        }
        Err(message) => {
            eprintln!("LOCAL_ENGLISH_TRAINER_SIDECAR_STARTUP_PROBE failed: {message}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<(), &'static str> {
    sidecar::run_startup_probe(&parse_resource_root()?)
}

fn parse_resource_root() -> Result<PathBuf, &'static str> {
    let mut arguments = env::args_os();
    let _program = arguments.next();
    if arguments.next().as_deref() != Some(std::ffi::OsStr::new("--resource-root")) {
        return Err("headless probe requires --resource-root");
    }
    let supplied = arguments.next().ok_or("headless probe requires a resource root")?;
    if arguments.next().is_some() {
        return Err("headless probe received unexpected arguments");
    }
    let resource_root = std::fs::canonicalize(supplied).map_err(|_| "headless probe resource root is invalid")?;
    if !resource_root.is_dir() {
        return Err("headless probe resource root is not a directory");
    }
    let executable = env::current_exe().map_err(|_| "headless probe executable path is unavailable")?;
    let executable_root = executable.parent().ok_or("headless probe executable root is unavailable")?;
    let executable_root = std::fs::canonicalize(executable_root).map_err(|_| "headless probe executable root is invalid")?;
    if resource_root != executable_root {
        return Err("headless probe resource root does not match the executable root");
    }
    Ok(resource_root)
}