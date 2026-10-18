# Managed key-vault migration

File-backed private-key custody is retired in all environments. Selecting
`provider=file` rejects before directory creation or key-file access. The old
`FileKeyVaultClient` import remains as a constructor that rejects immediately;
its PEM writer, reader and local signer are removed. Existing files are not
deleted or migrated automatically.

The factory requires an explicit provider. Development, testing and production
configuration no longer default to a file provider or the unimplemented `hsm`
adapter. Select `vault` or `hashicorp` only for a qualified deployment; configure
`vault_addr`/`VAULT_ADDR`, authentication method, role and Transit mount as needed.
The retained `file_path` and `hsm_config_path` configuration fields do not enable
file custody or implement an HSM adapter.

The existing Vault Transit client, remote signing/public-material protocol and
public configuration interfaces remain. Transit private-key import/export still
rejects. This retirement does not qualify the provider's tenant/purpose binding,
algorithm mapping, version/lifecycle policy, error handling, network trust or
authentication. Those need the Rust managed-KMS owner and real provider tests.
Mocked response forwarding is not custody or deployment acceptance.

Document-signer certificate creation still requests private PEM through the
legacy protocol and therefore cannot work with non-exportable Transit keys.
Preserve issuer/subject, policy, validity, public-key binding, trust-chain,
renewal/status and error requirements with Rust signing-keys and the document
signing owner. Implement canonical certificate preparation and managed signing
there before claiming parity; do not restore file keys to make the legacy helper
work. Retiring the file provider does not remove certificate/public metadata,
non-key configuration, existing key data or unfinished certificate intent.
