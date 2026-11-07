//! Screen capture of the primary monitor, encoded for the Holo API.

use base64::{engine::general_purpose::STANDARD, Engine};
use image::{imageops::FilterType, DynamicImage, GrayImage};
use std::io::Cursor;

/// Screenshots sent to Holo are capped at this width (`HOLO_SCREENSHOT_WIDTH`).
/// Benchmarked on 66 recorded click steps: 1600 px puts 79% of clicks within
/// 30 pt of the target vs 70% at 1280 px, for only ~0.2 s of extra latency
/// (Holo costs about width x height / 1024 tokens per image).
fn max_width() -> u32 {
    std::env::var("HOLO_SCREENSHOT_WIDTH")
        .ok()
        .and_then(|v| v.parse().ok())
        .filter(|w| (640..=1920).contains(w))
        .unwrap_or(1600)
}

pub struct Shot {
    /// `data:image/jpeg;base64,...`, ready for an `image_url` content part.
    pub data_uri: String,
    /// Tiny grayscale thumbnail used to detect "nothing changed" without an API call.
    pub thumb: GrayImage,
}

pub fn capture_primary() -> Result<Shot, String> {
    static LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());
    let _lock = LOCK.lock().map_err(|_| "Verrou de capture indisponible")?;
    let _mask = crate::autopilot::mask_capture()?;
    let monitors = xcap::Monitor::all().map_err(|e| format!("Screen capture failed: {e}"))?;
    let monitor = monitors
        .iter()
        .find(|m| m.is_primary().unwrap_or(false))
        .or(monitors.first())
        .ok_or("No display found")?;

    let rgba = monitor.capture_image().map_err(|e| {
        format!("Screen capture failed ({e}). Allow Screen Recording in System Settings › Privacy & Security.")
    })?;

    let img = DynamicImage::ImageRgba8(
        image::RgbaImage::from_raw(rgba.width(), rgba.height(), rgba.into_raw())
            .ok_or("Invalid capture image")?,
    );
    let max = max_width();
    let img = if img.width() > max {
        let h = img.height() * max / img.width();
        img.resize_exact(max, h, FilterType::Triangle)
    } else {
        img
    };

    let thumb = img.resize_exact(96, 54, FilterType::Triangle).to_luma8();

    let mut buf = Cursor::new(Vec::new());
    let encoder = image::codecs::jpeg::JpegEncoder::new_with_quality(&mut buf, 82);
    img.to_rgb8()
        .write_with_encoder(encoder)
        .map_err(|e| format!("JPEG encoding failed: {e}"))?;

    Ok(Shot {
        data_uri: format!("data:image/jpeg;base64,{}", STANDARD.encode(buf.into_inner())),
        thumb,
    })
}

/// Just the tiny grayscale thumbnail of the primary display, for watching
/// the screen for changes several times a second without any encoding.
pub fn capture_thumb() -> Result<GrayImage, String> {
    let monitors = xcap::Monitor::all().map_err(|e| format!("Screen capture failed: {e}"))?;
    let monitor = monitors
        .iter()
        .find(|m| m.is_primary().unwrap_or(false))
        .or(monitors.first())
        .ok_or("No display found")?;
    let rgba = monitor.capture_image().map_err(|e| format!("Screen capture failed: {e}"))?;
    let img = DynamicImage::ImageRgba8(
        image::RgbaImage::from_raw(rgba.width(), rgba.height(), rgba.into_raw()).ok_or("Invalid capture image")?,
    );
    // Same pipeline as `capture_primary` so thumbnails are comparable.
    let max = max_width();
    let img = if img.width() > max {
        let h = img.height() * max / img.width();
        img.resize_exact(max, h, FilterType::Nearest)
    } else {
        img
    };
    Ok(img.resize_exact(96, 54, FilterType::Triangle).to_luma8())
}

/// Mean absolute difference between two thumbnails, 0.0 (identical) to 255.0.
pub fn thumb_diff(a: &GrayImage, b: &GrayImage) -> f32 {
    if a.dimensions() != b.dimensions() {
        return 255.0;
    }
    let sum: u64 = a
        .pixels()
        .zip(b.pixels())
        .map(|(p, q)| p.0[0].abs_diff(q.0[0]) as u64)
        .sum();
    sum as f32 / (a.width() * a.height()) as f32
}
