//! marty-rs — Rust FFI for Marty credential operations
//!
//! Exposes to Python via PyO3:
//! - BitstringStatusList (W3C Bitstring Status List v1.0)
//! - TokenStatusList (IETF Token Status List)
//! - Credential status entry helpers

use pyo3::prelude::*;

pub mod error;
pub mod status_list;
pub mod mdoc;

/// Python module `_marty_rs`
#[pymodule]
fn _marty_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Status list types and functions
    status_list::register_status_list_module(m)?;

    Ok(())
}
