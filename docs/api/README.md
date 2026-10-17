# Marty Platform API Documentation

The checked-in HTML and specifications in this directory describe historical
Python service interfaces. They are retained for reference and do not establish
that retired PKD, document-processing or UI application endpoints are deployed.

Current REST documentation and the machine-readable OpenAPI location are owned
by [marty-docs](https://github.com/ElevenID/marty-docs/blob/main/src/content/docs/api/overview.md)
and the [marty-ui service stack](https://github.com/ElevenID/marty-ui).
Use those owners for the current public surface and release qualification.

## Historical Generated Documentation

### 📖 View Documentation

- **[Complete Platform Documentation](index.html)** - Main documentation page with links to all services
- **[Combined API Documentation](static/marty_platform_docs.html)** - All services in one interactive document

### Individual Service Documentation

- **[PKD Service](static/pkd_service_docs.html)** - ICAO PKD API for Public Key Directory management
- **[Document Processing](static/document_processing_docs.html)** - Document Processing MRZ API for verification  
- **[UI Application](static/ui_app_docs.html)** - Marty Platform Web UI and operator interface

### OpenAPI Specifications

The `openapi/` directory contains machine-readable API specifications:

- `marty_platform_combined_openapi.json` - Combined specification for all services
- `pkd_service_openapi.json` - PKD Service specification
- `document_processing_openapi.json` - Document Processing specification
- `ui_app_openapi.json` - UI Application specification

## Regenerating Documentation

The old `generate_docs.sh` wrapper is retired because it installed a development
dependency and called a nonexistent generator. The historical `make docs`,
`make docs-serve` and `generate_simple_docs.py` instructions do not provide a
working regeneration path here. The remaining legacy API generator also targets
retired Python app paths; reconcile its public documentation ownership before
replacing or removing the generated specifications. A release-bound API export,
complete service coverage, schema validation and reproducible documentation
remain requirements; this cleanup does not claim they are implemented here.

## Serving Documentation Locally

To inspect the retained files locally from the repository root:

```bash
python -m http.server 8000 --directory docs/api
```

Serving these static files does not start or qualify a service.

## Files Structure

```
docs/api/
├── index.html                          # Main documentation page
├── openapi/                           # OpenAPI specifications
│   ├── marty_platform_combined_openapi.json
│   ├── pkd_service_openapi.json
│   ├── document_processing_openapi.json
│   └── ui_app_openapi.json
└── static/                            # Interactive HTML documentation
    ├── marty_platform_docs.html
    ├── pkd_service_docs.html
    ├── document_processing_docs.html
    └── ui_app_docs.html
```

---

*Historical generated artifacts retained for reference.*
