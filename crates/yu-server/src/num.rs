//! Saturating float-to-integer conversions.
//!
//! Rust's `as` from a float already saturates -- negative goes to 0, values
//! past the maximum go to the maximum, and NaN goes to 0 -- but the sign loss
//! is invisible at the call site, which is what `clippy::cast_sign_loss` is
//! pointing at. These helpers do exactly what `as` does, with the behaviour
//! named and pinned by tests instead of left implicit at 23 separate sites.
//!
//! The equivalence to `as` is not asserted in prose: `helper_matches_the_cast_
//! it_replaces` compares the two over the interesting values, so a future
//! change to either side has to keep them in step.

/// `value as u8`, saturating. NaN yields 0.
#[allow(clippy::cast_sign_loss, clippy::cast_possible_truncation)]
#[inline]
pub(crate) fn sat_u8(value: f64) -> u8 {
    value as u8
}

/// `value as u16`, saturating. NaN yields 0.
#[allow(clippy::cast_sign_loss, clippy::cast_possible_truncation)]
#[inline]
pub(crate) fn sat_u16(value: f64) -> u16 {
    value as u16
}

/// `value as u32`, saturating. NaN yields 0.
#[allow(clippy::cast_sign_loss, clippy::cast_possible_truncation)]
#[inline]
pub(crate) fn sat_u32(value: f64) -> u32 {
    value as u32
}

/// `value as u64`, saturating. NaN yields 0.
#[allow(clippy::cast_sign_loss, clippy::cast_possible_truncation)]
#[inline]
pub(crate) fn sat_u64(value: f64) -> u64 {
    value as u64
}

/// `value as usize`, saturating. NaN yields 0.
#[allow(clippy::cast_sign_loss, clippy::cast_possible_truncation)]
#[inline]
pub(crate) fn sat_usize(value: f64) -> usize {
    value as usize
}

/// `value as i32`, saturating. NaN yields 0.
#[allow(clippy::cast_possible_truncation)]
#[inline]
pub(crate) fn sat_i32(value: f64) -> i32 {
    value as i32
}

/// `value as i64`, saturating. NaN yields 0.
#[allow(clippy::cast_possible_truncation)]
#[inline]
pub(crate) fn sat_i64(value: f64) -> i64 {
    value as i64
}

/// `value as f32`. Values past f32's range become an infinity, and precision
/// past ~7 significant digits is lost -- both are what the bare cast did.
#[allow(clippy::cast_possible_truncation)]
#[inline]
pub(crate) fn narrow_f32(value: f64) -> f32 {
    value as f32
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The values worth checking: the negative half these helpers exist to
    /// name, the overflow edge, NaN, and an ordinary fractional value.
    const CASES: &[f64] = &[
        -1.0,
        -0.5,
        -1e30,
        f64::NEG_INFINITY,
        0.0,
        0.4,
        0.5,
        1.9,
        255.0,
        256.0,
        65_535.0,
        65_536.0,
        1e30,
        f64::INFINITY,
        f64::NAN,
    ];

    /// The paired measurement. These helpers replaced 23 bare `as` casts, so
    /// the thing that must hold is that they behave identically -- not that
    /// they behave "sensibly". Anything else is a silent behaviour change in
    /// image-processing code where nobody would notice.
    #[test]
    #[allow(clippy::cast_sign_loss, clippy::cast_possible_truncation)]
    fn helper_matches_the_cast_it_replaces() {
        for &value in CASES {
            assert_eq!(sat_u8(value), value as u8, "u8 diverged at {value}");
            assert_eq!(sat_u16(value), value as u16, "u16 diverged at {value}");
            assert_eq!(sat_u32(value), value as u32, "u32 diverged at {value}");
            assert_eq!(sat_u64(value), value as u64, "u64 diverged at {value}");
            assert_eq!(sat_i32(value), value as i32, "i32 diverged at {value}");
            assert_eq!(sat_i64(value), value as i64, "i64 diverged at {value}");
            let narrowed = narrow_f32(value);
            let cast = value as f32;
            assert!(
                (narrowed == cast) || (narrowed.is_nan() && cast.is_nan()),
                "f32 diverged at {value}"
            );
            assert_eq!(
                sat_usize(value),
                value as usize,
                "usize diverged at {value}"
            );
        }
    }

    /// Spelling out the three properties the name promises, so a reader does
    /// not have to know that Rust's float casts saturate.
    #[test]
    fn negatives_and_nan_become_zero_and_the_top_end_clamps() {
        assert_eq!(sat_u32(-1.0), 0);
        assert_eq!(sat_u32(f64::NEG_INFINITY), 0);
        assert_eq!(sat_u32(f64::NAN), 0);
        assert_eq!(sat_u8(300.0), u8::MAX);
        assert_eq!(sat_u32(f64::INFINITY), u32::MAX);
        // Truncation, not rounding -- callers that want rounding call
        // `.round()` first, and several do.
        assert_eq!(sat_u32(1.9), 1);
    }

    /// The signed helpers saturate at BOTH ends, unlike the unsigned ones
    /// which floor at zero -- the difference a caller has to know about.
    #[test]
    fn the_signed_helpers_keep_the_negative_half() {
        assert_eq!(sat_i32(-1.0), -1);
        assert_eq!(sat_i64(-1.9), -1, "truncation is toward zero, not down");
        assert_eq!(sat_i32(f64::NEG_INFINITY), i32::MIN);
        assert_eq!(sat_i32(f64::INFINITY), i32::MAX);
        assert_eq!(sat_i32(f64::NAN), 0);
    }

    #[test]
    fn narrowing_to_f32_overflows_to_infinity_rather_than_wrapping() {
        assert_eq!(narrow_f32(0.5), 0.5_f32);
        assert!(narrow_f32(1e300).is_infinite());
        assert!(narrow_f32(f64::NAN).is_nan());
    }
}
