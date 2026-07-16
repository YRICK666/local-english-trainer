use std::path::Path;

const SIDECAR_RELATIVE_DIR: &str = "sidecar/local-english-trainer-api";

pub fn verify_resource_dir(resource_dir: &Path) -> Result<(), String> {
    let sidecar_dir = resource_dir.join(SIDECAR_RELATIVE_DIR);
    let required_paths = [
        sidecar_dir.join("local-english-trainer-api.exe"),
        sidecar_dir.join("_internal"),
        sidecar_dir.join("_internal/python311.dll"),
    ];

    for required_path in required_paths {
        if !required_path.exists() {
            return Err(format!(
                "resource probe failed: required staged resource is absent: {}",
                required_path.display()
            ));
        }
    }

    Ok(())
}


#[cfg(test)]
mod tests {
    use super::verify_resource_dir;
    use std::{
        fs,
        time::{SystemTime, UNIX_EPOCH},
    };

    #[test]
    fn verifies_the_expected_resource_tree_without_reading_files() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock before epoch")
            .as_nanos();
        let root = std::env::temp_dir().join(format!("local-english-trainer-resource-probe-{unique}"));
        let internal = root.join("sidecar/local-english-trainer-api/_internal");
        fs::create_dir_all(&internal).expect("create probe fixture");
        fs::write(
            root.join("sidecar/local-english-trainer-api/local-english-trainer-api.exe"),
            [],
        )
        .expect("create placeholder exe");
        fs::write(internal.join("python311.dll"), []).expect("create placeholder runtime");

        let result = verify_resource_dir(&root);
        let cleanup = fs::remove_dir_all(&root);
        assert!(cleanup.is_ok(), "remove only the test-created probe fixture");
        assert!(result.is_ok());
    }
}