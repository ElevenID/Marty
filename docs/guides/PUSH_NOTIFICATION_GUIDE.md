# Push notification implementation ownership

The former Python notification package and its unpublished `/api/*` routers
are retired. They were not mounted by the released Marty plugin and have no
current ElevenID source consumer.

Supported notification behavior now belongs to shared Rust implementations:

- `mmf-push` owns channel-neutral messages, FCM, SSE, webhooks, token
  lifecycle, routing, failure handling, and test adapters. Its language-neutral
  behavior contract is `contracts/push-behavior.json` in the canonical
  `marty-microservices-framework` repository.
- `marty-ui/rust/services/notification` owns notification and webhook HTTP and
  gRPC services, persistence, outbox delivery, tenant boundaries, secret
  handling, and failure behavior. Its contract is
  `marty-ui/contracts/notification_behavior.json`.
- `marty-ui/rust/services/device-registration` owns device registration,
  challenge issuance and validation, replay protection, and key rotation. Its
  contract is `marty-ui/contracts/device-registration-service-behavior.json`.

Historical Python examples can be recovered from Git history. New code must
use the Rust services and crates above rather than restoring the retired
Python package.
