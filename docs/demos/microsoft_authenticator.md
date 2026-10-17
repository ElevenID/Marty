# Microsoft Authenticator interoperability follow-up

The historical Python demo and its Compose/Kubernetes resources were retired.
The remaining demo launchers, tunnel helpers and completion notes at checkpoint
`3b28fef` are now retired too: they referenced absent resources and do not qualify
Microsoft Authenticator support. No current device interoperability result is
claimed by this cleanup.

Keep the following requirements open with the current issuer, verifier and
integration owners:

- Confirm the actual wallet/protocol versions and advertised credential formats
  supported by the device. Do not infer compatibility from the old demo's
  OID4VCI/OID4VP labels or hardcoded endpoint shapes.
- Use governed HTTPS endpoints, correct issuer/verifier metadata and DID/web
  identity resolution where required by the selected wallet profile. Exercise
  offer, authorization/token and credential issuance, followed by presentation
  request, wallet response and verifier result through the public gateway.
- Use real issuer signatures, holder proofs/binding, trusted certificate or DID
  resolution and applicable revocation/status policy. Reject tampered/expired
  proofs, replay, bad issuer or audience, invalid state and cross-tenant requests.
- Run the real QR/deep-link/mobile acceptance journey with current canonical
  service owners and retained positive/negative tests. A tunnel, health response
  or sample JSON alone is not device qualification. Historical latency figures
  are not measured acceptance thresholds.

Supported deployment procedures belong to
[the UI stack](https://github.com/ElevenID/marty-ui/blob/main/DEVELOPMENT_SETUP.md).
Fresh, source-bound interoperability runs belong to
[the integration repository](https://github.com/ElevenID/marty-integration-tests).
Keep the wallet-specific feature gap visible until those owners provide actual
device and protocol evidence; do not restore a parallel Python demo stack just
to satisfy an old tutorial.
