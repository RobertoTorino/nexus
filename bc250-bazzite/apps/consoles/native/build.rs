// SPDX-License-Identifier: AGPL-3.0-or-later
// With the feature "decoder": compiles src/decoder.c and links FFmpeg statically, from BC250_FFMPEG_DIR or the
// folder ffmpeg/build.sh builds into (~/.cache/bc250-console-link/ffmpeg-<version>). Its pkg-config files name
// what else to link: the system's libva and libva-drm, dynamically. Without the feature there is nothing to do.

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
        println!("cargo:rerun-if-env-changed=BC250_FFMPEG_DIR");
        let dir = env::var_os("BC250_FFMPEG_DIR").map(PathBuf::from).unwrap_or_else(|| {
            let cache = env::var_os("XDG_CACHE_HOME").map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from(env::var_os("HOME").expect("HOME")).join(".cache"));
            cache.join("bc250-console-link").join(format!("ffmpeg-{FFMPEG_VERSION}"))
        });
        let pkgconfig = dir.join("lib").join("pkgconfig");
        if !pkgconfig.join("libavcodec.pc").exists() {
            panic!("The feature \"decoder\" needs FFmpeg from ffmpeg/build.sh, not found in {}: run ffmpeg/build.sh, \
                    or set BC250_FFMPEG_DIR.", dir.display());
        }

        let output = Command::new("pkg-config")
            .args(["--static", "--cflags", "--libs", "libavcodec", "libswresample", "libavutil"])
            .env("PKG_CONFIG_PATH", &pkgconfig)
            .env("PKG_CONFIG_ALLOW_SYSTEM_LIBS", "1")
            .output()
            .expect("pkg-config");
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
        build.compile("bc250_decoder");
        let own = dir.join("lib");
        for flag in flags.split_whitespace() {
            if let Some(path) = flag.strip_prefix("-L") {
                println!("cargo:rustc-link-search=native={path}");
            } else if let Some(lib) = flag.strip_prefix("-l") {
                // FFmpeg's own libraries statically; the system's (libva, libm) dynamically.
                let kind = if own.join(format!("lib{lib}.a")).exists() { "static" } else { "dylib" };
                println!("cargo:rustc-link-lib={kind}={lib}");
            } else if flag == "-pthread" {
                println!("cargo:rustc-link-lib=dylib=pthread");
            }
        }
    }
}
