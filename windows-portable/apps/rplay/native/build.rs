// SPDX-License-Identifier: AGPL-3.0-or-later
// With the feature "decoder": compiles src/decoder.c and links FFmpeg statically, from RPLAY_FFMPEG_DIR or the
// folder ffmpeg/build.sh builds into (%LOCALAPPDATA%\windows-portable-suite\build\ffmpeg-<version>). Its pkg-config
// files name what else to link: Windows' own libraries (bcrypt, ole32, ...), dynamically. Without the feature there
// is nothing to do. Console Link's build.rs, for Windows: pkg-config and the C compiler are MSYS2's MINGW64 ones
// (C:\msys64\mingw64\bin on PATH), the same GCC that built FFmpeg, and cargo's toolchain the GNU one.

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    #[cfg(feature = "decoder")]
    decoder::build();
}

#[cfg(feature = "decoder")]
mod decoder {
    use std::env;
    use std::path::PathBuf;
    use std::process::Command;

    const FFMPEG_VERSION: &str = "7.1.2";      // as in ffmpeg/build.sh

    pub fn build() {
        println!("cargo:rerun-if-changed=src/decoder.c");
        println!("cargo:rerun-if-env-changed=RPLAY_FFMPEG_DIR");
        let dir = env::var_os("RPLAY_FFMPEG_DIR").map(PathBuf::from).unwrap_or_else(|| {
            PathBuf::from(env::var_os("LOCALAPPDATA").expect("LOCALAPPDATA"))
                .join("windows-portable-suite").join("build").join(format!("ffmpeg-{FFMPEG_VERSION}"))
        });
        let pkgconfig = dir.join("lib").join("pkgconfig");
        if !pkgconfig.join("libavcodec.pc").exists() {
            panic!("The feature \"decoder\" needs FFmpeg from ffmpeg/build.sh, not found in {}: run ffmpeg/build.sh, \
                    or set RPLAY_FFMPEG_DIR.", dir.display());
        }
        for lib in ["avcodec", "swresample", "avutil"] {         // FFmpeg built again: link it again
            println!("cargo:rerun-if-changed={}", dir.join("lib").join(format!("lib{lib}.a")).display());
        }

        let output = Command::new("pkg-config")
            .args(["--static", "--cflags", "--libs", "libavcodec", "libswresample", "libavutil"])
            .env("PKG_CONFIG_PATH", &pkgconfig)
            .env("PKG_CONFIG_ALLOW_SYSTEM_LIBS", "1")
            .output()
            .expect("pkg-config (MSYS2's MINGW64 one: C:\\msys64\\mingw64\\bin on PATH)");
        assert!(output.status.success(), "pkg-config: {}", String::from_utf8_lossy(&output.stderr));
        let flags = String::from_utf8(output.stdout).expect("pkg-config's output");

        // The shim first: a static library comes before the libraries it uses.
        let mut build = cc::Build::new();
        build.file("src/decoder.c").warnings(true);
        for flag in flags.split_whitespace() {
            if let Some(include) = flag.strip_prefix("-I") {
                build.include(include);
            }
        }
        build.compile("rplay_decoder");
        let own = dir.join("lib");
        for flag in flags.split_whitespace() {
            if let Some(path) = flag.strip_prefix("-L") {
                println!("cargo:rustc-link-search=native={path}");
            } else if let Some(lib) = flag.strip_prefix("-l") {
                // FFmpeg's own libraries statically; Windows' (bcrypt, ole32, user32) dynamically.
                let kind = if own.join(format!("lib{lib}.a")).exists() { "static" } else { "dylib" };
                println!("cargo:rustc-link-lib={kind}={lib}");
            }
        }
    }
}
