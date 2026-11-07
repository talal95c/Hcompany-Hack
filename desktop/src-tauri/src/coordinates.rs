use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Rect {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
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
    pub fn valid(&self) -> bool {
        [self.x, self.y, self.width, self.height]
            .iter()
            .all(|v| v.is_finite())
            && self.width >= 1.0
            && self.height >= 1.0
    }
}

impl Monitor {
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
    }
}
