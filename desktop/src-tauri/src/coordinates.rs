use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Rect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ScreenRect {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
}
impl ScreenRect {
    pub fn rect(self) -> Rect {
        Rect {
            x: self.x,
            y: self.y,
            width: self.w,
            height: self.h,
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Monitor {
    pub id: String,
    pub physical: Rect,
    pub logical_x: f64,
    pub logical_y: f64,
    pub scale: f64,
}

impl Rect {
    pub fn screen(self) -> ScreenRect {
        ScreenRect {
            x: self.x,
            y: self.y,
            w: self.width,
            h: self.height,
        }
    }
    pub fn logical_to_physical(self, scale: f64) -> Option<Self> {
        if !scale.is_finite() || scale <= 0.0 || !self.valid() {
            return None;
        }
        let rect = Self {
            x: self.x * scale,
            y: self.y * scale,
            width: self.width * scale,
            height: self.height * scale,
        };
        rect.valid().then_some(rect)
    }

    pub fn atspi_screen(x: i32, y: i32, width: i32, height: i32) -> Option<Self> {
        if x == i32::MIN || y == i32::MIN {
            return None;
        }
        let rect = Self {
            x: x.into(),
            y: y.into(),
            width: width.into(),
            height: height.into(),
        };
        rect.logical_to_physical(1.0)
    }

    pub fn valid(&self) -> bool {
        [self.x, self.y, self.width, self.height]
            .iter()
            .all(|v| v.is_finite())
            && self.width >= 1.0
            && self.height >= 1.0
    }
}

impl Monitor {
    pub fn overlay_rect(&self, rect: Rect) -> Result<Rect, String> {
        if !self.contains(rect) {
            return Err("Zone hors moniteur".into());
        }
        Ok(Rect {
            x: (rect.x - self.physical.x) / self.scale,
            y: (rect.y - self.physical.y) / self.scale,
            width: rect.width / self.scale,
            height: rect.height / self.scale,
        })
    }

    pub fn contains(&self, crop: Rect) -> bool {
        let p = self.physical;
        p.valid()
            && crop.valid()
            && self.scale.is_finite()
            && self.scale > 0.0
            && self.logical_x.is_finite()
            && self.logical_y.is_finite()
            && crop.x >= p.x
            && crop.y >= p.y
            && crop.x + crop.width <= p.x + p.width
            && crop.y + crop.height <= p.y + p.height
    }

    pub fn point(&self, crop: Rect, u: f64, v: f64) -> Result<(f64, f64), String> {
        if !self.contains(crop)
            || !u.is_finite()
            || !v.is_finite()
            || !(0.0..=1000.0).contains(&u)
            || !(0.0..=1000.0).contains(&v)
        {
            return Err("invalid coordinates or cross-monitor crop".into());
        }
        let px = crop.x + (u * crop.width / 1000.0).min(crop.width - 1.0);
        let py = crop.y + (v * crop.height / 1000.0).min(crop.height - 1.0);
        Ok((
            self.logical_x + (px - self.physical.x) / self.scale,
            self.logical_y + (py - self.physical.y) / self.scale,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn accessibility_coordinates() {
        assert!(Rect::atspi_screen(i32::MIN, 0, 10, 10).is_none());
        assert!(Rect::atspi_screen(0, 0, 0, 10).is_none());
        let r = Rect::atspi_screen(-100, 20, 50, 30).unwrap();
        assert_eq!(r.x, -100.);
        let p = r.logical_to_physical(2.).unwrap();
        assert_eq!((p.x, p.y, p.width, p.height), (-200., 40., 100., 60.));
        assert!(r.logical_to_physical(f64::NAN).is_none());
        assert!(r.logical_to_physical(0.).is_none());
    }

    #[test]
    fn retina_negative_origin() {
        let m = Monitor {
            id: "left".into(),
            physical: Rect {
                x: -2880.,
                y: 0.,
                width: 2880.,
                height: 1800.,
            },
            logical_x: -1440.,
            logical_y: 0.,
            scale: 2.,
        };
        let crop = Rect {
            x: -2680.,
            y: 200.,
            width: 400.,
            height: 200.,
        };
        assert_eq!(m.point(crop, 500., 500.).unwrap(), (-1240., 150.));
        assert_eq!(m.point(crop, 1000., 1000.).unwrap(), (-1140.5, 199.5));
        assert!(m.point(crop, f64::NAN, 0.).is_err());
        assert!(m.point(Rect { x: -10., ..crop }, 0., 0.).is_err());
        assert!(m.point(crop, -1., 0.).is_err());
        let css = m.overlay_rect(crop).unwrap();
        assert_eq!(
            (css.x, css.y, css.width, css.height),
            (100., 100., 200., 100.)
        );
        assert!(m.overlay_rect(Rect { x: -10., ..crop }).is_err());
    }
}
