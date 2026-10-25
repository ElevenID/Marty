"""Legacy field/output compatibility, separate from ICAO qualification."""

from datetime import date
from types import SimpleNamespace

import pytest

from marty_plugin.shared.utils.mrz_standardized import MRZStandardizedUtils
from marty_plugin.shared.utils.td2_mrz import TD2MRZGenerator
from marty_plugin.shared.utils.visa_mrz import MRZGenerator


@pytest.fixture(params=[TD2MRZGenerator, MRZGenerator])
def generator(request):
    return request.param


@pytest.mark.parametrize(
    "text,width,filler,expected",
    [
        ("", 5, "<", "<<<<<"),
        ("a b", 7, "<", "A<B<<<<"),
        ("äéß", 8, "<", "<SS<<<<<"),
        (" A---B<<<", 6, "<", "<A<B<<"),
        ("a b", 6, "_", "A<B___"),
        ("abcdef", 3, "<", "ABC"),
        ("abc", 0, "<", ""),
        ("abcde", -2, "<", "ABC"),
        ("", 2, "ab", "abab"),
    ],
)
def test_field_compatibility(generator, text, width, filler, expected):
    assert generator.sanitize_for_mrz(text, width, filler) == expected


def test_invalid_padding_filler_is_not_silently_accepted(generator):
    with pytest.raises(TypeError):
        generator.sanitize_for_mrz("a", 3, "ab")


def test_date_format_and_strict_missing_date(generator):
    assert generator.format_date_for_mrz(date(2000, 2, 29)) == "000229"
    with pytest.raises(AttributeError):
        generator.format_date_for_mrz(None)


def test_standardized_missing_date_keeps_its_distinct_behavior():
    assert MRZStandardizedUtils.format_date_for_mrz(None) == "000000"


def test_legacy_document_lines_and_rust_check_digits():
    # These fixed outputs characterize existing format owners, not conformance.
    document = SimpleNamespace(
        personal_data=SimpleNamespace(
            primary_identifier="Eriksson", secondary_identifier="Anna Maria",
            surname="Eriksson", given_names="Anna Maria", nationality="UTO",
            date_of_birth=date(1974, 8, 12), gender=SimpleNamespace(value="F"),
        ),
        document_data=SimpleNamespace(
            document_type=SimpleNamespace(value="I"), issuing_state="UTO",
            document_number="L898902C3", date_of_expiry=date(2030, 4, 15),
            visa_category=SimpleNamespace(value="B1/B2"),
        ),
    )
    td2 = TD2MRZGenerator.generate_td2_mrz(document)
    a1, a2, visa_a = MRZGenerator.generate_type_a_mrz(document)
    b1, b2, b3, visa_b = MRZGenerator.generate_type_b_mrz(document)
    assert (td2.line1, td2.line2) == (
        "I<UTOL898902C367408122F3004157UTO<<4",
        "ERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<",
    )
    assert (a1, a2) == (
        "VUTOL898902C36UTOB1<B2<<<<<<<<<<<<<<<<<<<<<<",
        "7408122F3004157UTO<<<<<<<<<<<<<<<<<<<<<<<<<4",
    )
    assert (b1, b2, b3) == (
        "VUTO<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<",
        "L898902C36UTO7408122F3004157<<<<<<<<",
        "B1<B2<<<<<<<<<<ERIKSSON<<ANNA<MARIA4",
    )
    for output in (td2, visa_a, visa_b):
        assert (
            output.check_digit_document, output.check_digit_dob,
            output.check_digit_expiry, output.check_digit_composite,
        ) == ("6", "2", "7", "4")
