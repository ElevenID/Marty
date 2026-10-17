# API documentation ownership

[openapi.yaml](openapi.yaml) is a retained historical interface description,
not a current release contract. The retired generator referenced missing Python
applications and produced fallback route stubs; its generated HTML and JSON
have been removed.

Current REST documentation and machine-readable OpenAPI locations belong to
[marty-docs](https://github.com/ElevenID/marty-docs/blob/main/src/content/docs/api/overview.md)
and the [marty-ui service stack](https://github.com/ElevenID/marty-ui).
Release qualification still needs an export from the running supported
services, complete endpoint/schema coverage, schema validation and reproducible
documentation generation. Removing the obsolete export does not complete
those requirements.
