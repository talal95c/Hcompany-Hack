fn main() {
    println!("cargo:rerun-if-changed=native/macos.swift");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        let output =
            std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap()).join("native-macos");
        let status = std::process::Command::new("xcrun")
            .args([
                "swiftc",
                "-parse-as-library",
                "native/macos.swift",
                "-Xlinker",
                "-sectcreate",
                "-Xlinker",
                "__TEXT",
                "-Xlinker",
                "__info_plist",
                "-Xlinker",
                "Info.plist",
                "-o",
            ])
            .arg(output)
            .status()
            .expect("Swift compiler required for ScreenCaptureKit backend");
        assert!(status.success(), "macOS native backend compilation failed");
    }
    tauri_build::build()
}
