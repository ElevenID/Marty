# Inspection System

## Overview

The Inspection System is responsible for verifying ePassports. It reads MRZ, derives access keys, accesses and parses chip data, validates signatures against trusted CSCA certificates, and checks revocation status.

## Features

- Reading and parsing Machine Readable Zone (MRZ).
- Derivation of access keys for ePassport chips.
- Validation of chip data signatures against CSCA certificates.
- Revocation status checks using CRLs.

## Directory Structure

- `config/`: Configuration files for the service.
- `src/`: Source code for the service.
- `tests/`: Unit and integration tests for the service.
