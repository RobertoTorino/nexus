// SPDX-License-Identifier: AGPL-3.0-only
//! Forward error correction of the video frames: a Cauchy Reed-Solomon
//! code over GF(2^8) with the primitive polynomial 0x11d, its coding matrix Jerasure's
//! cauchy_original_coding_matrix (row i, column j: 1 / (i ^ (m + j))). A frame has k source units and m FEC units
//! of the same size; any k of them give back the source units. The tests decode frames recorded by the reference
//! (tests/fec_vectors.json of the app, from its test/fec_test_cases.inl).

pub const WORD_SIZE: u32 = 8;
const POLYNOMIAL: u16 = 0x11d;

const fn tables() -> ([u8; 512], [u8; 256]) {
    let mut exp = [0u8; 512];
    let mut log = [0u8; 256];
    let mut x: u16 = 1;
    let mut i = 0;
    while i < 255 {
        exp[i] = x as u8;
        exp[i + 255] = x as u8;
        log[x as usize] = i as u8;
        x <<= 1;
        if x & 0x100 != 0 {
            x ^= POLYNOMIAL;
        }
        i += 1;
    }
    (exp, log)
}

const TABLES: ([u8; 512], [u8; 256]) = tables();

pub fn mul(a: u8, b: u8) -> u8 {
    if a == 0 || b == 0 {
        return 0;
    }
    let (exp, log) = &TABLES;
    exp[log[a as usize] as usize + log[b as usize] as usize]
}

pub fn inverse(a: u8) -> u8 {
    assert!(a != 0, "zero has no inverse");
    let (exp, log) = &TABLES;
    exp[255 - log[a as usize] as usize]
}

#[derive(Debug, PartialEq, Eq)]
pub enum FecError {
    /// More units missing than there are FEC units.
    TooManyErasures,
    /// k + m larger than the field allows, or a unit outside the buffer.
    InvalidData,
    /// The units left do not determine the missing ones (not for a Cauchy matrix, but checked).
    Singular,
}

/// The m × k coding matrix, row by row.
pub fn coding_matrix(k: usize, m: usize) -> Result<Vec<u8>, FecError> {
    if k == 0 || k + m > 1 << WORD_SIZE {
        return Err(FecError::InvalidData);
    }
    let mut matrix = Vec::with_capacity(k * m);
    for i in 0..m {
        for j in 0..k {
            matrix.push(inverse((i ^ (m + j)) as u8));
        }
    }
    Ok(matrix)
}

/// Adds coefficient × src to dst, byte by byte.
fn add_scaled(dst: &mut [u8], src: &[u8], coefficient: u8) {
    if coefficient == 0 {
        return;
    }
    let mut row = [0u8; 256];
    for (value, entry) in row.iter_mut().enumerate() {
        *entry = mul(value as u8, coefficient);
    }
    for (d, s) in dst.iter_mut().zip(src) {
        *d ^= row[*s as usize];
    }
}

/// Inverts a size × size matrix by Gauss-Jordan elimination.
fn invert(mut matrix: Vec<u8>, size: usize) -> Result<Vec<u8>, FecError> {
    let mut inverse_matrix = vec![0u8; size * size];
    for i in 0..size {
        inverse_matrix[i * size + i] = 1;
    }
    for col in 0..size {
        let pivot = (col..size).find(|&row| matrix[row * size + col] != 0).ok_or(FecError::Singular)?;
        if pivot != col {
            for c in 0..size {
                matrix.swap(pivot * size + c, col * size + c);
                inverse_matrix.swap(pivot * size + c, col * size + c);
            }
        }
        let scale = inverse(matrix[col * size + col]);
        for c in 0..size {
            matrix[col * size + c] = mul(matrix[col * size + c], scale);
            inverse_matrix[col * size + c] = mul(inverse_matrix[col * size + c], scale);
        }
        for row in 0..size {
            let factor = matrix[row * size + col];
            if row == col || factor == 0 {
                continue;
            }
            for c in 0..size {
                matrix[row * size + c] ^= mul(factor, matrix[col * size + c]);
                inverse_matrix[row * size + c] ^= mul(factor, inverse_matrix[col * size + c]);
            }
        }
    }
    Ok(inverse_matrix)
}

fn check_buffer(buf: &[u8], unit_size: usize, stride: usize, units: usize) -> Result<(), FecError> {
    if stride < unit_size || units.checked_mul(stride).is_none_or(|size| size > buf.len()) {
        return Err(FecError::InvalidData);
    }
    Ok(())
}

/// Rebuilds the erased source units of a frame buffer: unit i at i × stride, unit_size bytes, the k source units
/// first, then the m FEC units. As in Jerasure, the units used are the source units still there, and for each
/// missing one the next FEC unit still there; erased FEC units are not rebuilt (the frame does not need them).
pub fn decode(buf: &mut [u8], unit_size: usize, stride: usize, k: usize, m: usize, erasures: &[usize])
    -> Result<(), FecError> {
    let matrix = coding_matrix(k, m)?;
    check_buffer(buf, unit_size, stride, k + m)?;
    let mut erased = vec![false; k + m];
    for &e in erasures {
        *erased.get_mut(e).ok_or(FecError::InvalidData)? = true;
    }
    if erased.iter().filter(|&&e| e).count() > m {
        return Err(FecError::TooManyErasures);
    }
    if !erased[..k].iter().any(|&e| e) {
        return Ok(());
    }

    let mut sources = Vec::with_capacity(k);
    let mut next_fec = k;
    for (i, &gone) in erased[..k].iter().enumerate() {
        if !gone {
            sources.push(i);
        } else {
            while erased[next_fec] {
                next_fec += 1;
            }
            sources.push(next_fec);
            next_fec += 1;
        }
    }
    let mut rows = vec![0u8; k * k];
    for (i, &source) in sources.iter().enumerate() {
        if source < k {
            rows[i * k + source] = 1;
        } else {
            rows[i * k..(i + 1) * k].copy_from_slice(&matrix[(source - k) * k..(source - k + 1) * k]);
        }
    }
    let decoding = invert(rows, k)?;

    for i in (0..k).filter(|&i| erased[i]) {
        let mut unit = vec![0u8; unit_size];
        for (j, &source) in sources.iter().enumerate() {
            add_scaled(&mut unit, &buf[source * stride..source * stride + unit_size], decoding[i * k + j]);
        }
        buf[i * stride..i * stride + unit_size].copy_from_slice(&unit);
    }
    Ok(())
}

/// Computes the m FEC units from the k source units, in the same buffer layout: what the console does, for the
/// tests and the fake console.
pub fn encode(buf: &mut [u8], unit_size: usize, stride: usize, k: usize, m: usize) -> Result<(), FecError> {
    let matrix = coding_matrix(k, m)?;
    check_buffer(buf, unit_size, stride, k + m)?;
    for i in 0..m {
        let mut unit = vec![0u8; unit_size];
        for j in 0..k {
            add_scaled(&mut unit, &buf[j * stride..j * stride + unit_size], matrix[i * k + j]);
        }
        buf[(k + i) * stride..(k + i) * stride + unit_size].copy_from_slice(&unit);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::vectors::base64;

    #[test]
    fn field_arithmetic() {
        assert_eq!(mul(0x80, 2), 0x1d);
        for a in 1..=255u8 {
            assert_eq!(mul(a, inverse(a)), 1);
        }
    }

    #[test]
    fn recorded_frames_decode_as_in_the_reference() {
        let cases: serde_json::Value =
            serde_json::from_str(include_str!("../../tests/fec_vectors.json")).expect("valid vectors");
        for case in cases["cases"].as_array().unwrap() {
            let k = case["k"].as_u64().unwrap() as usize;
            let m = case["m"].as_u64().unwrap() as usize;
            let unit_size = case["unit_size"].as_u64().unwrap() as usize;
            let erasures: Vec<usize> =
                case["erasures"].as_array().unwrap().iter().map(|e| e.as_u64().unwrap() as usize).collect();
            let reference = base64(case["frame"].as_str().unwrap());
            assert_eq!(reference.len(), unit_size * (k + m));

            let stride = unit_size.div_ceil(16) * 16;
            let mut buf = vec![0u8; stride * (k + m)];
            for i in 0..k + m {
                let unit = if erasures.contains(&i) { vec![0x42; unit_size] }
                           else { reference[i * unit_size..(i + 1) * unit_size].to_vec() };
                buf[i * stride..i * stride + unit_size].copy_from_slice(&unit);
            }
            decode(&mut buf, unit_size, stride, k, m, &erasures).unwrap();
            for i in 0..k {
                assert_eq!(&buf[i * stride..i * stride + unit_size], &reference[i * unit_size..(i + 1) * unit_size],
                           "k {k}, m {m}, erasures {erasures:?}, unit {i}");
            }

            // The console's FEC units are what our encoder computes (an erased one holds other bytes).
            let mut encoded = buf.clone();
            encode(&mut encoded, unit_size, stride, k, m).unwrap();
            for i in (k..k + m).filter(|i| !erasures.contains(i)) {
                assert_eq!(&encoded[i * stride..i * stride + unit_size],
                           &reference[i * unit_size..(i + 1) * unit_size]);
            }
        }
    }

    #[test]
    fn too_many_erasures_fail() {
        let mut buf = vec![7u8; 16 * 5];
        encode(&mut buf, 16, 16, 3, 2).unwrap();
        assert_eq!(decode(&mut buf, 16, 16, 3, 2, &[0, 1, 2]), Err(FecError::TooManyErasures));
        assert_eq!(decode(&mut buf, 16, 16, 3, 2, &[5]), Err(FecError::InvalidData));
        assert_eq!(decode(&mut buf, 32, 16, 3, 2, &[0]), Err(FecError::InvalidData));
    }
}
