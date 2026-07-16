use crate::sidecar::{SidecarManager, SidecarState};
use std::{
    io::Write,
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant},
};
use tauri::AppHandle;

const SUPERVISOR_INTERVAL: Duration = Duration::from_millis(200);
const STARTUP_SHUTDOWN_WAIT: Duration = Duration::from_secs(20);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FaultMode {
    None,
    TerminateChildAfterReady,
    ForceShutdownTimeout,
}

impl FaultMode {
    fn parse(value: &str) -> Self {
        match value {
            "terminate-child-after-ready" => Self::TerminateChildAfterReady,
            "force-shutdown-timeout" => Self::ForceShutdownTimeout,
            "none" | _ => Self::None,
        }
    }

    fn from_probe_environment(enabled: bool) -> Self {
        if !enabled {
            return Self::None;
        }
        std::env::var("LOCAL_ENGLISH_TRAINER_LIFECYCLE_FAULT")
            .map(|value| Self::parse(&value))
            .unwrap_or(Self::None)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CloseDecision {
    Allow,
    PreventAndShutdown,
    PreventAlreadyShuttingDown,
}

impl CloseDecision {
    pub fn must_prevent_close(self) -> bool {
        !matches!(self, Self::Allow)
    }
}

struct LifecycleInner {
    state: SidecarState,
    manager: Option<SidecarManager>,
}

pub struct AppSidecarLifecycle {
    enabled: bool,
    fault_mode: FaultMode,
    startup_started: AtomicBool,
    shutdown_started: AtomicBool,
    shutdown_worker_started: AtomicBool,
    supervisor_stop: AtomicBool,
    exit_permitted: AtomicBool,
    inner: Mutex<LifecycleInner>,
    last_safe_error: Mutex<Option<&'static str>>,
}

impl AppSidecarLifecycle {
    pub fn new(enabled: bool) -> Arc<Self> {
        Arc::new(Self {
            enabled,
            fault_mode: FaultMode::from_probe_environment(enabled),
            startup_started: AtomicBool::new(false),
            shutdown_started: AtomicBool::new(false),
            shutdown_worker_started: AtomicBool::new(false),
            supervisor_stop: AtomicBool::new(false),
            exit_permitted: AtomicBool::new(false),
            inner: Mutex::new(LifecycleInner {
                state: SidecarState::NotStarted,
                manager: None,
            }),
            last_safe_error: Mutex::new(None),
        })
    }

    pub fn enabled(&self) -> bool {
        self.enabled
    }

    pub fn fault_mode(&self) -> FaultMode {
        self.fault_mode
    }

    pub fn start_background(self: &Arc<Self>, resource_dir: PathBuf) {
        if !self.enabled || self.startup_started.swap(true, Ordering::AcqRel) {
            return;
        }
        self.set_state(SidecarState::Starting);
        let lifecycle = Arc::clone(self);
        thread::spawn(move || {
            let mut manager = SidecarManager::default();
            match manager.start_lifecycle(&resource_dir) {
                Ok(()) => lifecycle.store_ready_manager(manager),
                Err(error) => {
                    let _ = manager.force_cleanup();
                    lifecycle.record_failure(error);
                    emit_marker("LET_LIFECYCLE_START_FAILED");
                }
            }
        });
    }

    pub fn request_close(&self) -> CloseDecision {
        if !self.enabled || self.exit_permitted.load(Ordering::Acquire) {
            return CloseDecision::Allow;
        }
        self.supervisor_stop.store(true, Ordering::Release);
        if self.shutdown_started.swap(true, Ordering::AcqRel) {
            CloseDecision::PreventAlreadyShuttingDown
        } else {
            CloseDecision::PreventAndShutdown
        }
    }

    pub fn start_shutdown_background(self: &Arc<Self>, app_handle: AppHandle) {
        if !self.enabled || !self.shutdown_started.load(Ordering::Acquire) {
            return;
        }
        if self.shutdown_worker_started.swap(true, Ordering::AcqRel) {
            return;
        }
        let lifecycle = Arc::clone(self);
        thread::spawn(move || lifecycle.shutdown_worker(app_handle));
    }

    fn store_ready_manager(self: &Arc<Self>, manager: SidecarManager) {
        let shutdown_requested = self.shutdown_started.load(Ordering::Acquire);
        {
            let mut inner = self.inner.lock().expect("lifecycle state mutex poisoned");
            inner.manager = Some(manager);
            inner.state = if shutdown_requested {
                SidecarState::Stopping
            } else {
                SidecarState::Ready
            };
        }
        emit_marker("LET_LIFECYCLE_READY");
        if self.fault_mode == FaultMode::TerminateChildAfterReady {
            let fault_result = self
                .inner
                .lock()
                .expect("lifecycle state mutex poisoned")
                .manager
                .as_mut()
                .ok_or("sidecar manager is unavailable for fault injection")
                .and_then(SidecarManager::terminate_child_for_fault);
            if fault_result.is_err() {
                self.record_failure("sidecar fault termination failed");
                emit_marker("LET_LIFECYCLE_START_FAILED");
                return;
            }
        }
        if !shutdown_requested {
            self.start_supervisor();
        }
    }

    fn start_supervisor(self: &Arc<Self>) {
        let lifecycle = Arc::clone(self);
        thread::spawn(move || loop {
            thread::sleep(SUPERVISOR_INTERVAL);
            if lifecycle.supervisor_stop.load(Ordering::Acquire)
                || lifecycle.shutdown_started.load(Ordering::Acquire)
            {
                return;
            }

            let exited_manager = {
                let mut inner = lifecycle.inner.lock().expect("lifecycle state mutex poisoned");
                if inner.state != SidecarState::Ready {
                    return;
                }
                let exited = inner
                    .manager
                    .as_mut()
                    .map(|manager| manager.poll_for_exit())
                    .transpose();
                match exited {
                    Ok(Some(true)) => {
                        inner.state = SidecarState::Failed;
                        inner.manager.take()
                    }
                    Ok(Some(false)) => None,
                    Ok(None) | Err(_) => {
                        inner.state = SidecarState::Failed;
                        inner.manager.take()
                    }
                }
            };

            if let Some(mut manager) = exited_manager {
                let _ = manager.force_cleanup();
                lifecycle.record_failure("sidecar exited unexpectedly");
                emit_marker("LET_LIFECYCLE_CHILD_EXITED_UNEXPECTEDLY");
            }
        });
    }

    fn shutdown_worker(&self, app_handle: AppHandle) {
        emit_marker("LET_LIFECYCLE_SHUTDOWN_WORKER_STARTED");
        let deadline = Instant::now() + STARTUP_SHUTDOWN_WAIT;
        let mut manager = loop {
            let selection = {
                let mut inner = self.inner.lock().expect("lifecycle state mutex poisoned");
                match inner.state {
                    SidecarState::Ready | SidecarState::Stopping => {
                        inner.state = SidecarState::Stopping;
                        Some(inner.manager.take())
                    }
                    SidecarState::Failed | SidecarState::Stopped | SidecarState::NotStarted => Some(None),
                    SidecarState::Starting => None,
                }
            };
            if let Some(manager) = selection {
                break manager;
            }
            if Instant::now() >= deadline {
                self.record_failure("sidecar startup did not finish before shutdown");
                break None;
            }
            thread::sleep(Duration::from_millis(50));
        };

        let graceful = self.fault_mode != FaultMode::ForceShutdownTimeout
            && match manager.as_mut() {
                Some(manager) => manager.shutdown_gracefully().is_ok(),
                None => false,
            };
        if graceful {
            emit_marker("LET_LIFECYCLE_GRACEFUL_SHUTDOWN_OK");
        } else if let Some(manager) = manager.as_mut() {
            let _ = manager.force_cleanup();
            emit_marker("LET_LIFECYCLE_FORCED_CLEANUP_OK");
        }

        self.finish_shutdown();
        emit_marker("LET_LIFECYCLE_EXIT_REQUESTED");
        app_handle.exit(0);
    }

    fn set_state(&self, next: SidecarState) {
        let mut inner = self.inner.lock().expect("lifecycle state mutex poisoned");
        if transition_is_valid(inner.state, next) {
            inner.state = next;
        }
    }

    fn record_failure(&self, error: &'static str) {
        let mut inner = self.inner.lock().expect("lifecycle state mutex poisoned");
        inner.state = SidecarState::Failed;
        drop(inner);
        *self.last_safe_error.lock().expect("lifecycle error mutex poisoned") = Some(error);
    }

    fn finish_shutdown(&self) {
        self.supervisor_stop.store(true, Ordering::Release);
        let mut inner = self.inner.lock().expect("lifecycle state mutex poisoned");
        inner.manager = None;
        inner.state = SidecarState::Stopped;
        drop(inner);
        self.exit_permitted.store(true, Ordering::Release);
    }

    #[cfg(test)]
    fn state(&self) -> SidecarState {
        self.inner.lock().expect("lifecycle state mutex poisoned").state
    }

    #[cfg(test)]
    fn set_state_for_test(&self, state: SidecarState) {
        self.inner.lock().expect("lifecycle state mutex poisoned").state = state;
    }

    #[cfg(test)]
    fn supervisor_should_stop(&self) -> bool {
        self.supervisor_stop.load(Ordering::Acquire)
            || self.shutdown_started.load(Ordering::Acquire)
    }


}

fn transition_is_valid(from: SidecarState, to: SidecarState) -> bool {
    matches!(
        (from, to),
        (SidecarState::NotStarted, SidecarState::Starting | SidecarState::Stopped)
            | (SidecarState::Starting, SidecarState::Ready | SidecarState::Failed | SidecarState::Stopping)
            | (SidecarState::Ready, SidecarState::Stopping | SidecarState::Failed)
            | (SidecarState::Failed, SidecarState::Stopped)
            | (SidecarState::Stopping, SidecarState::Stopped | SidecarState::Failed)
            | (SidecarState::Stopped, SidecarState::Stopped)
    )
}

fn emit_marker(marker: &str) {
    eprintln!("{marker}");
    let _ = std::io::stderr().flush();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn disabled_mode_does_not_mark_startup_or_intercept_close() {
        let state = AppSidecarLifecycle::new(false);
        assert!(!state.enabled());
        assert!(!state.startup_started.load(Ordering::Acquire));
        assert_eq!(state.request_close(), CloseDecision::Allow);
    }

    #[test]
    fn close_is_idempotent_and_stops_the_supervisor() {
        let state = AppSidecarLifecycle::new(true);
        state.set_state_for_test(SidecarState::Ready);
        assert_eq!(state.request_close(), CloseDecision::PreventAndShutdown);
        assert_eq!(state.request_close(), CloseDecision::PreventAlreadyShuttingDown);
        assert!(state.supervisor_should_stop());
        assert_eq!(state.state(), SidecarState::Ready);
    }

    #[test]
    fn permitted_exit_is_not_intercepted() {
        let state = AppSidecarLifecycle::new(true);
        state.exit_permitted.store(true, Ordering::Release);
        assert_eq!(state.request_close(), CloseDecision::Allow);
    }
    #[test]
    fn failed_lifecycle_close_still_permits_one_safe_cleanup_worker() {
        let state = AppSidecarLifecycle::new(true);
        state.set_state_for_test(SidecarState::Failed);
        assert_eq!(state.request_close(), CloseDecision::PreventAndShutdown);
        assert_eq!(state.state(), SidecarState::Failed);
        assert_eq!(state.request_close(), CloseDecision::PreventAlreadyShuttingDown);
    }

    #[test]
    fn lifecycle_transitions_reject_ready_to_starting() {
        assert!(transition_is_valid(SidecarState::NotStarted, SidecarState::Starting));
        assert!(transition_is_valid(SidecarState::Ready, SidecarState::Stopping));
        assert!(transition_is_valid(SidecarState::Failed, SidecarState::Stopped));
        assert!(!transition_is_valid(SidecarState::Ready, SidecarState::Starting));
        assert!(!transition_is_valid(SidecarState::Stopped, SidecarState::Starting));
    }

    #[test]
    fn fault_mode_parser_is_safe_and_probe_scoped() {
        assert_eq!(FaultMode::parse("none"), FaultMode::None);
        assert_eq!(FaultMode::parse("terminate-child-after-ready"), FaultMode::TerminateChildAfterReady);
        assert_eq!(FaultMode::parse("force-shutdown-timeout"), FaultMode::ForceShutdownTimeout);
        assert_eq!(FaultMode::parse("unknown"), FaultMode::None);
        assert_eq!(AppSidecarLifecycle::new(false).fault_mode(), FaultMode::None);
    }
}