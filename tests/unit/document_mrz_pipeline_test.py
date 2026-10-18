"""The active API keeps real image extraction and Rust checksum validation."""

import asyncio
import base64
import importlib
from io import BytesIO

import pytest
from PIL import Image

from tests.unit.pretravel_wallet_offer_test import modules as modules

TD3 = [
    "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
    "L898902C36UTO7408122F1204159ZE184226B<<<<<10",
]
TD2 = ["I<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<", "D231458907UTO7408122F1204159<<<<<<<6"]
TD1 = [
    "I<UTOD231458907<<<<<<<<<<<<<<<",
    "7408122F1204159UTO<<<<<<<<<<<6",
    "ERIKSSON<<ANNA<MARIA<<<<<<<<<<",
]


@pytest.mark.parametrize("lines", [TD1, TD2, TD3], ids=["TD1", "TD2", "TD3"])
def test_retained_parser_uses_native_checks_and_no_fabricated_measurements(
    modules, lines
):
    mrz = importlib.import_module("app.services.mrz_service")
    result = mrz.MRZProcessingService()._process_mrz_lines(lines)
    assert result.overallValid and result.surname == "ERIKSSON"
    assert result.dateOfBirth == "740812" and result.sex == "F"
    assert all(
        field.confidence is None
        and field.line is None
        and field.start is None
        and field.length is None
        for field in result.fields
    )
    altered = [line.replace("7408122", "7408123") for line in lines]
    assert mrz.MRZProcessingService()._process_mrz_lines(altered) is None
    client = importlib.import_module(
        "app.services.service_clients"
    ).GrpcInspectionSystemClient()
    invalid = asyncio.run(client.validate_mrz({"mrzLines": altered}))
    assert invalid["valid"] is False and invalid["checksums_valid"] is False


@pytest.mark.parametrize("outcome", ["valid", "empty", "error", "tampered"])
def test_process_route_keeps_pipeline_and_never_invents_ocr_evidence(
    modules, monkeypatch, outcome
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mrz = importlib.import_module("app.services.mrz_service")
    endpoints = importlib.import_module("app.api.endpoints")
    deps = importlib.import_module("app.api.deps")
    clients = importlib.import_module("app.services.service_clients")
    monkeypatch.setattr(deps.settings, "USE_API_KEY", False)
    monkeypatch.setattr(clients.service_factory, "use_real_services", True)
    sizes = []

    def ocr(image, *, config, lang):
        sizes.append(image.size)
        assert lang == "eng" and "tessedit_char_whitelist=" in config
        if outcome == "error":
            raise RuntimeError("OCR unavailable")
        if outcome == "empty":
            return "  \n"
        text = "\n".join(TD3)
        return text.replace("7408122", "7408123") if outcome == "tampered" else text

    monkeypatch.setattr(mrz.pytesseract, "image_to_string", ocr)
    buffer = BytesIO()
    Image.new("RGB", (800, 400), "white").save(buffer, format="PNG")
    payload = {
        "processParam": {"scenario": "Mrz"},
        "images": [{"ImageData": base64.b64encode(buffer.getvalue()).decode()}],
    }
    app = FastAPI()
    app.include_router(endpoints.router)
    with TestClient(app) as client:
        response = client.post("/api/process", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert (
        result["ContainerList"]["Count"] == 1
        and result["TransactionInfo"]["TransactionID"]
    )
    container = result["ContainerList"]["List"][0]
    assert sizes[0] == (
        800,
        100,
    )  # Actual layout crop, not a substituted document pipeline.
    if outcome == "valid":
        assert container["mrzResult"]["documentNumber"] == "L898902C3"
        assert container["Status"]["overallStatus"] == 1
        assert container["mrzResult"]["overallValid"] is True
    else:
        assert container["mrzResult"] is None
        assert container["Status"]["overallStatus"] == 0
        if outcome != "tampered":
            assert sizes == [(800, 100), (800, 400)]


def test_region_empty_falls_back_to_real_full_image_ocr_and_honors_language(
    modules, monkeypatch
):
    mrz = importlib.import_module("app.services.mrz_service")
    coordinator = importlib.import_module("app.services.coordinator_service")
    monkeypatch.setattr(mrz.ImageProcessor, "tess_lang", "ocrb")
    sizes = []

    def ocr(image, *, config, lang):
        assert lang == "ocrb"
        sizes.append(image.size)
        return "" if len(sizes) == 1 else "\n".join(TD3)

    monkeypatch.setattr(mrz.pytesseract, "image_to_string", ocr)
    buffer = BytesIO()
    Image.new("RGB", (800, 400), "white").save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    result = asyncio.run(
        coordinator.DocumentProcessingCoordinator()._extract_mrz_generic(
            encoded, Image.new("RGB", (800, 100))
        )
    )
    assert result.overallValid and sizes == [(800, 100), (800, 400)]
