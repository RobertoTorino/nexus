// SPDX-License-Identifier: AGPL-3.0-only
//! The controller's orientation from its gyro and accelerometer (the reference's orientation.c): Madgwick's IMU
//! filter, a strong correction towards gravity for the first 30 samples and a weak one after, and a filter that
//! holds the result still against small jitter, as the kernel's input fuzz does. The console gets the orientation as
//! a quaternion in its FEEDBACK_STATE (feedback.rs).
//!
//! The arithmetic is the reference's float arithmetic, with the double steps where its C has them (1 / sqrt and the
//! final rotation), so the results are the same bits (tests/orientation_vectors.json, printed by the reference's own
//! code).

// The reference's constants: its cosines are 1/√2, its sines written one digit shorter, one step lower as a double.
#[allow(clippy::excessive_precision, clippy::approx_constant)]
const SIN_1_4_PI: f64 = 0.7071067811865475;
#[allow(clippy::excessive_precision, clippy::approx_constant)]
const SIN_NEG_1_4_PI: f64 = -0.7071067811865475;
const COS_1_4_PI: f64 = std::f64::consts::FRAC_1_SQRT_2;
const COS_NEG_1_4_PI: f64 = std::f64::consts::FRAC_1_SQRT_2;

const WARMUP_SAMPLES_COUNT: u64 = 30;
const BETA_WARMUP: f32 = 20.0;
const BETA_DEFAULT: f32 = 0.05;

const ORIENT_FUZZ: f32 = 0.0007;
const FUZZ_FILTER_PREV_WEIGHT: f32 = 0.75;
const FUZZ_FILTER_PREV_WEIGHT_2X: f32 = 0.6;

/// A quaternion (x, y, z, w).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Orientation {
    pub x: f32,
    pub y: f32,
    pub z: f32,
    pub w: f32,
}

impl Default for Orientation {
    /// A 90° rotation around x, Madgwick's frame for a controller lying flat.
    fn default() -> Self {
        Orientation { x: SIN_1_4_PI as f32, y: 0.0, z: 0.0, w: COS_1_4_PI as f32 }
    }
}

fn inv_sqrt(x: f32) -> f32 {
    (1.0 / (x as f64).sqrt()) as f32
}

/// The input fuzz filter: within half the fuzz the previous value stays, within the fuzz and twice it the new one is
/// mixed in, beyond that it is taken.
fn fuzz(cur: f32, prev: &mut f32, fuzz: f32, wprev: f32, wprev2x: f32) {
    if cur < *prev + fuzz / 2.0 && cur > *prev - fuzz / 2.0 {
        return;
    }
    if cur < *prev + fuzz && cur > *prev - fuzz {
        *prev = wprev * *prev + (1.0 - wprev) * cur;
        return;
    }
    if cur < *prev + fuzz * 2.0 && cur > *prev - fuzz * 2.0 {
        *prev = wprev2x * *prev + (1.0 - wprev2x) * cur;
        return;
    }
    *prev = cur;
}

impl Orientation {
    /// One step of Madgwick's IMU algorithm: gyro in rad/s, accelerometer in g (all zero: gyro only).
    #[allow(clippy::too_many_arguments)]
    pub fn update(&mut self, gx: f32, gy: f32, gz: f32, mut ax: f32, mut ay: f32, mut az: f32, beta: f32,
                  time_step_sec: f32) {
        let (mut q0, mut q1, mut q2, mut q3) = (self.w, self.x, self.y, self.z);

        // Rate of change of the quaternion from the gyroscope.
        let mut q_dot1 = 0.5 * (-q1 * gx - q2 * gy - q3 * gz);
        let mut q_dot2 = 0.5 * (q0 * gx + q2 * gz - q3 * gy);
        let mut q_dot3 = 0.5 * (q0 * gy - q1 * gz + q3 * gx);
        let mut q_dot4 = 0.5 * (q0 * gz + q1 * gy - q2 * gx);

        if !(ax == 0.0 && ay == 0.0 && az == 0.0) {
            let recip_norm = inv_sqrt(ax * ax + ay * ay + az * az);
            ax *= recip_norm;
            ay *= recip_norm;
            az *= recip_norm;

            let (_2q0, _2q1, _2q2, _2q3) = (2.0 * q0, 2.0 * q1, 2.0 * q2, 2.0 * q3);
            let (_4q0, _4q1, _4q2) = (4.0 * q0, 4.0 * q1, 4.0 * q2);
            let (_8q1, _8q2) = (8.0 * q1, 8.0 * q2);
            let (q0q0, q1q1, q2q2, q3q3) = (q0 * q0, q1 * q1, q2 * q2, q3 * q3);

            // The gradient descent's corrective step.
            let mut s0 = _4q0 * q2q2 + _2q2 * ax + _4q0 * q1q1 - _2q1 * ay;
            let mut s1 = _4q1 * q3q3 - _2q3 * ax + 4.0 * q0q0 * q1 - _2q0 * ay - _4q1 + _8q1 * q1q1 + _8q1 * q2q2
                + _4q1 * az;
            let mut s2 = 4.0 * q0q0 * q2 + _2q0 * ax + _4q2 * q3q3 - _2q3 * ay - _4q2 + _8q2 * q1q1 + _8q2 * q2q2
                + _4q2 * az;
            let mut s3 = 4.0 * q1q1 * q3 - _2q1 * ax + 4.0 * q2q2 * q3 - _2q2 * ay;
            let norm = s0 * s0 + s1 * s1 + s2 * s2 + s3 * s3;
            // Nothing to correct when the orientation is already right (or exactly upside down).
            if norm > 0.000001 {
                let recip_norm = inv_sqrt(norm);
                s0 *= recip_norm;
                s1 *= recip_norm;
                s2 *= recip_norm;
                s3 *= recip_norm;
                q_dot1 -= beta * s0;
                q_dot2 -= beta * s1;
                q_dot3 -= beta * s2;
                q_dot4 -= beta * s3;
            }
        }

        q0 += q_dot1 * time_step_sec;
        q1 += q_dot2 * time_step_sec;
        q2 += q_dot3 * time_step_sec;
        q3 += q_dot4 * time_step_sec;

        let recip_norm = inv_sqrt(q0 * q0 + q1 * q1 + q2 * q2 + q3 * q3);
        q0 *= recip_norm;
        q1 *= recip_norm;
        q2 *= recip_norm;
        q3 *= recip_norm;

        fuzz(q0, &mut self.w, ORIENT_FUZZ, FUZZ_FILTER_PREV_WEIGHT, FUZZ_FILTER_PREV_WEIGHT_2X);
        fuzz(q1, &mut self.x, ORIENT_FUZZ, FUZZ_FILTER_PREV_WEIGHT, FUZZ_FILTER_PREV_WEIGHT_2X);
        fuzz(q2, &mut self.y, ORIENT_FUZZ, FUZZ_FILTER_PREV_WEIGHT, FUZZ_FILTER_PREV_WEIGHT_2X);
        fuzz(q3, &mut self.z, ORIENT_FUZZ, FUZZ_FILTER_PREV_WEIGHT, FUZZ_FILTER_PREV_WEIGHT_2X);
    }
}

/// One controller's motion: the last gyro and accelerometer values and the orientation they lead to.
#[derive(Debug, Clone, PartialEq)]
pub struct Tracker {
    pub gyro: [f32; 3],
    pub accel: [f32; 3],
    pub orient: Orientation,
    timestamp: u32,
    sample_index: u64,
}

impl Default for Tracker {
    fn default() -> Self {
        Tracker { gyro: [0.0; 3], accel: [0.0, 1.0, 0.0], orient: Orientation::default(), timestamp: 0, sample_index: 0 }
    }
}

impl Tracker {
    /// A sample: gyro in rad/s, accelerometer in g, at timestamp_us (a 32-bit microsecond clock that may wrap).
    /// Unless accel_zero_applied, accel_zero is taken off the accelerometer first (the reference's motion reset;
    /// zero when there was none). The first sample only sets the clock.
    pub fn update(&mut self, gyro: [f32; 3], accel: [f32; 3], accel_zero: [f32; 3], accel_zero_applied: bool,
                  timestamp_us: u32) {
        self.gyro = gyro;
        let mut accel = accel;
        if !accel_zero_applied {
            for (value, zero) in accel.iter_mut().zip(accel_zero) {
                *value -= zero;
            }
        }
        self.accel = accel;
        self.sample_index += 1;
        if self.sample_index <= 1 {
            self.timestamp = timestamp_us;
            return;
        }
        let mut delta_us = timestamp_us as u64;
        if delta_us < self.timestamp as u64 {
            delta_us += 1 << 32;
        }
        delta_us -= self.timestamp as u64;
        self.timestamp = timestamp_us;
        let beta = if self.sample_index < WARMUP_SAMPLES_COUNT { BETA_WARMUP } else { BETA_DEFAULT };
        self.orient.update(gyro[0], gyro[1], gyro[2], accel[0], accel[1], accel[2], beta,
                           delta_us as f32 / 1000000.0);
    }

    /// The orientation as the console expects it (x, y, z, w): Madgwick's frame turned back by 90° around x.
    pub fn console_orientation(&self) -> [f32; 4] {
        let o = &self.orient;
        let (w, x, y, z) = (o.w as f64, o.x as f64, o.y as f64, o.z as f64);
        [
            (COS_NEG_1_4_PI * x + SIN_NEG_1_4_PI * w) as f32,
            (COS_NEG_1_4_PI * y - SIN_NEG_1_4_PI * z) as f32,
            (COS_NEG_1_4_PI * z + SIN_NEG_1_4_PI * y) as f32,
            (COS_NEG_1_4_PI * w - SIN_NEG_1_4_PI * x) as f32,
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn load() -> serde_json::Value {
        serde_json::from_str(include_str!("../../tests/orientation_vectors.json")).expect("valid vectors")
    }

    fn floats(v: &serde_json::Value) -> Vec<f32> {
        v.as_array().unwrap().iter().map(|x| x.as_f64().unwrap() as f32).collect()
    }

    #[test]
    fn tracker_matches_reference() {
        let mut tracker = Tracker::default();
        for (i, sample) in load()["samples"].as_array().unwrap().iter().enumerate() {
            let data: [f32; 3] = floats(&sample["data"]).try_into().unwrap();
            let timestamp = sample["timestamp"].as_u64().unwrap() as u32;
            // As the reference's GUI feeds it: a gyro sample with the last accelerometer values, already zeroed,
            // and the other way round.
            if sample["gyro"].as_bool().unwrap() {
                let accel = tracker.accel;
                tracker.update(data, accel, [0.0; 3], true, timestamp);
            } else {
                let gyro = tracker.gyro;
                tracker.update(gyro, data, [0.0; 3], false, timestamp);
            }
            assert_eq!(tracker.gyro.to_vec(), floats(&sample["state_gyro"]), "sample {i}");
            assert_eq!(tracker.accel.to_vec(), floats(&sample["state_accel"]), "sample {i}");
            assert_eq!(tracker.console_orientation().to_vec(), floats(&sample["orient"]), "sample {i}");
        }
    }

    #[test]
    fn accel_zero_matches_reference() {
        let v = &load()["zero"];
        let zero: [f32; 3] = floats(&v["zero"]).try_into().unwrap();
        let mut tracker = Tracker::default();
        tracker.update([0.0; 3], [0.3, 1.2, 0.1], zero, false, 1000);
        tracker.update([0.5, 0.0, 0.0], [0.3, 1.2, 0.1], zero, false, 5000);
        assert_eq!(tracker.accel.to_vec(), floats(&v["accel"]));
        assert_eq!(tracker.console_orientation().to_vec(), floats(&v["orient"]));
    }

    #[test]
    fn lying_still_is_the_idle_orientation() {
        let tracker = Tracker::default();
        let [x, y, z, w] = tracker.console_orientation();
        assert!(x.abs() < 1e-7 && y == 0.0 && z == 0.0 && w == 1.0);
    }
}
