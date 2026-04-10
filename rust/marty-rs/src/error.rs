use thiserror::Error;

#[derive(Error, Debug)]
pub enum MartyError {
    #[error("Status list error: {0}")]
    StatusList(String),

    #[error("Encoding error: {0}")]
    Encoding(String),

    #[error("Index out of bounds: {index} >= {size}")]
    IndexOutOfBounds { index: usize, size: usize },

    #[error("Crypto error: {0}")]
    Crypto(String),

    #[error("Serialization error: {0}")]
    Serialization(String),

    #[error("Invalid argument: {0}")]
    InvalidArgument(String),
}

impl From<MartyError> for pyo3::PyErr {
    fn from(err: MartyError) -> pyo3::PyErr {
        pyo3::exceptions::PyRuntimeError::new_err(err.to_string())
    }
}
