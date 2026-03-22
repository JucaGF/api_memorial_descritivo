from __future__ import annotations

import unittest

from app.services.extraction_mapper import map_extraction_to_partial_context
from app.services.project_extractor import ExtractedSourceFile, ProjectExtractionResult


def build_extraction_result(raw_text: str) -> ProjectExtractionResult:
    return ProjectExtractionResult(
        raw_text=raw_text,
        source_files=[
            ExtractedSourceFile(
                original_filename="projeto.pdf",
                stored_filename="01_projeto.pdf",
                extension=".pdf",
                saved_path="/tmp/01_projeto.pdf",
                extracted_text=raw_text,
            )
        ],
        signals={
            "total_files": 1,
            "file_types": [".pdf"],
            "has_pdf": True,
            "has_docx": False,
            "total_characters": len(raw_text),
        },
    )


class ExtractionMapperTests(unittest.TestCase):
    def test_map_extraction_to_partial_context_extracts_detectable_fields(self) -> None:
        raw_text = """
        CONSTRUTORA: MGA Construções e Incorporações LTDA
        NOME DA OBRA: Edifício Makai
        LOCALIZAÇÃO: Avenida Max Zagel, Cabedelo - PB
        Alimentação em média tensão 15 kV.
        Subestação abrigada abaixadora com medição em MT.
        Sistema de aterramento TN-S.
        Seção do cabo de média tensão: 35 mm2.
        """

        context = map_extraction_to_partial_context(build_extraction_result(raw_text))

        self.assertEqual(
            context["obra"]["construtora"],
            "MGA Construções e Incorporações LTDA",
        )
        self.assertEqual(context["obra"]["nome"], "Edifício Makai")
        self.assertEqual(
            context["obra"]["localizacao"],
            "Avenida Max Zagel, Cabedelo - PB",
        )
        self.assertTrue(context["energia"]["tem_subestacao"])
        self.assertEqual(
            context["energia"]["tipo_subestacao"],
            "Subestação abrigada abaixadora com medição em MT",
        )
        self.assertEqual(context["aterramento"]["tipo_sistema"], "TN-S")
        self.assertEqual(context["mt"]["tensao_kv"], 15)
        self.assertEqual(context["mt"]["secao_cabo_mm2"], 35)

    def test_map_extraction_to_partial_context_handles_missing_fields_without_error(self) -> None:
        raw_text = """
        Planta baixa do pavimento tipo.
        Diagramas unifilares e detalhes de iluminação.
        """

        context = map_extraction_to_partial_context(build_extraction_result(raw_text))

        self.assertIsNone(context["obra"]["construtora"])
        self.assertIsNone(context["obra"]["nome"])
        self.assertIsNone(context["obra"]["localizacao"])
        self.assertIsNone(context["energia"]["tem_subestacao"])
        self.assertIsNone(context["energia"]["tipo_subestacao"])
        self.assertIsNone(context["aterramento"]["tipo_sistema"])
        self.assertIsNone(context["mt"]["tensao_kv"])
        self.assertIsNone(context["mt"]["secao_cabo_mm2"])

    def test_map_extraction_to_partial_context_detects_sem_subestacao(self) -> None:
        raw_text = """
        EMPREENDIMENTO: Residencial Horizonte
        Endereço: João Pessoa - PB
        O projeto não possui subestação e será alimentado em baixa tensão.
        """

        context = map_extraction_to_partial_context(build_extraction_result(raw_text))

        self.assertEqual(context["obra"]["nome"], "Residencial Horizonte")
        self.assertEqual(context["obra"]["localizacao"], "João Pessoa - PB")
        self.assertFalse(context["energia"]["tem_subestacao"])
        self.assertIsNone(context["energia"]["tipo_subestacao"])


if __name__ == "__main__":
    unittest.main()
