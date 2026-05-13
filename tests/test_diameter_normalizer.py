from __future__ import annotations

import unittest
from decimal import Decimal

from app.services.diameter_normalizer import NormalizedDiameter, normalize_diameter


class DiameterNormalizerTests(unittest.TestCase):
    """Bug 5 — pipe diameter rendered as 1.25mm when source was 1 1/4".

    Tests cover all formats listed in the brief plus edge cases.
    """

    def assertDiameter(
        self,
        text: str,
        *,
        valor: Decimal,
        unidade: str,
        valor_formatado: str,
    ) -> None:
        result = normalize_diameter(text)
        self.assertIsNotNone(result, f"Failed to parse: {text!r}")
        assert isinstance(result, NormalizedDiameter)
        self.assertEqual(result.valor, valor, f"Wrong valor for {text!r}")
        self.assertEqual(result.unidade, unidade, f"Wrong unidade for {text!r}")
        self.assertEqual(
            result.valor_formatado,
            valor_formatado,
            f"Wrong valor_formatado for {text!r}",
        )

    def test_one_and_quarter_inch_space_quote(self) -> None:
        self.assertDiameter(
            '1 1/4"',
            valor=Decimal("1.25"),
            unidade="in",
            valor_formatado='1 1/4"',
        )

    def test_one_and_quarter_inch_dot(self) -> None:
        self.assertDiameter(
            '1.1/4"',
            valor=Decimal("1.25"),
            unidade="in",
            valor_formatado='1 1/4"',
        )

    def test_one_and_quarter_inch_hyphen(self) -> None:
        self.assertDiameter(
            '1-1/4"',
            valor=Decimal("1.25"),
            unidade="in",
            valor_formatado='1 1/4"',
        )

    def test_one_and_quarter_pol(self) -> None:
        self.assertDiameter(
            "1 1/4 pol",
            valor=Decimal("1.25"),
            unidade="in",
            valor_formatado='1 1/4"',
        )

    def test_one_and_quarter_polegadas(self) -> None:
        self.assertDiameter(
            "1 1/4 polegadas",
            valor=Decimal("1.25"),
            unidade="in",
            valor_formatado='1 1/4"',
        )

    def test_three_quarters_inch(self) -> None:
        self.assertDiameter(
            '3/4"',
            valor=Decimal("0.75"),
            unidade="in",
            valor_formatado='3/4"',
        )

    def test_half_inch(self) -> None:
        self.assertDiameter(
            '1/2"',
            valor=Decimal("0.5"),
            unidade="in",
            valor_formatado='1/2"',
        )

    def test_twenty_five_mm_with_space(self) -> None:
        self.assertDiameter(
            "25 mm",
            valor=Decimal("25"),
            unidade="mm",
            valor_formatado="25 mm",
        )

    def test_thirty_two_mm_no_space(self) -> None:
        self.assertDiameter(
            "32mm",
            valor=Decimal("32"),
            unidade="mm",
            valor_formatado="32 mm",
        )

    def test_brazilian_decimal_comma_in_mm(self) -> None:
        self.assertDiameter(
            "25,4 mm",
            valor=Decimal("25.4"),
            unidade="mm",
            valor_formatado="25.4 mm",
        )

    def test_does_not_convert_inch_to_mm_automatically(self) -> None:
        """Critical: 1 1/4" must NOT become anything in mm without explicit conversion."""
        result = normalize_diameter('1 1/4"')
        self.assertIsNotNone(result)
        assert isinstance(result, NormalizedDiameter)
        self.assertEqual(result.unidade, "in")
        self.assertNotIn("mm", result.valor_formatado)

    def test_does_not_convert_mm_to_inch_automatically(self) -> None:
        result = normalize_diameter("25 mm")
        self.assertIsNotNone(result)
        assert isinstance(result, NormalizedDiameter)
        self.assertEqual(result.unidade, "mm")
        self.assertNotIn('"', result.valor_formatado)
        self.assertNotIn("pol", result.valor_formatado.lower())

    def test_decimal_inch_value(self) -> None:
        self.assertDiameter(
            '1.5"',
            valor=Decimal("1.5"),
            unidade="in",
            valor_formatado='1.5"',
        )

    def test_extract_from_surrounding_text(self) -> None:
        result = normalize_diameter("Diâmetro do ramal primário: 1 1/4\" em aço carbono")
        self.assertIsNotNone(result)
        assert isinstance(result, NormalizedDiameter)
        self.assertEqual(result.valor, Decimal("1.25"))
        self.assertEqual(result.unidade, "in")

    def test_returns_none_for_empty_input(self) -> None:
        self.assertIsNone(normalize_diameter(""))
        self.assertIsNone(normalize_diameter("   "))
        self.assertIsNone(normalize_diameter(None))

    def test_returns_none_for_unparseable_input(self) -> None:
        self.assertIsNone(normalize_diameter("aço carbono"))
        self.assertIsNone(normalize_diameter("32"))  # bare number, unit unknown

    def test_returns_none_for_zero_denominator(self) -> None:
        self.assertIsNone(normalize_diameter('1 1/0"'))

    def test_inches_double_quote_apostrophes_form(self) -> None:
        self.assertDiameter(
            "3/4''",
            valor=Decimal("0.75"),
            unidade="in",
            valor_formatado='3/4"',
        )

    def test_valor_original_preserves_source_substring(self) -> None:
        result = normalize_diameter("Ø32mm  PEAD")
        self.assertIsNotNone(result)
        assert isinstance(result, NormalizedDiameter)
        self.assertEqual(result.valor_original, "32mm")


if __name__ == "__main__":
    unittest.main()
