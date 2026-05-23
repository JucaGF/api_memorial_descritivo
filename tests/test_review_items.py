from __future__ import annotations

import unittest

from app.services.review_items import build_review_items


class ReviewItemsTests(unittest.TestCase):
    def test_build_review_items_flags_missing_default_low_confidence_and_conflict(self) -> None:
        final_context = {
            "obra": {"nome": "Residencial Aurora", "qtd_apartamentos": 29},
            "mt": {"tensao_kv": 13.8},
            "ramal": {"primario_diametro": "1 1/4"},
        }
        extraction_report = {
            "missing": ["obra.localizacao"],
            "pending": ["ramal.primario_material"],
            "evidence": {
                "mt.tensao_kv": {
                    "value": 13.8,
                    "rule": "eletrico_mt_tensao_default",
                    "evidence": "valor padrão MT-13.8kV",
                    "confidence": "low",
                },
                "ramal.primario_diametro": {
                    "value": "1 1/4",
                    "rule": "gas_natural_primary_branch_diameter_regex",
                    "evidence": "Tubulação em Aço Carbono SCH 40 ⌀1 1/4\"",
                    "confidence": "medium",
                },
                "obra.nome": {
                    "value": "Residencial Aurora",
                    "rule": "carimbo_line_before_company",
                    "evidence": "Residencial Aurora",
                    "confidence": "high",
                },
            },
            "cross_validation": {
                "quantitative_conflicts": [
                    {
                        "field_path": "pontos_utilizacao.total",
                        "tipo": "glp_v2_points_total_mismatch",
                        "status": "unresolved",
                        "valores_observados": [35, 34],
                    }
                ]
            },
        }

        items = build_review_items(final_context, extraction_report)

        by_path = {item["field_path"]: item for item in items}
        self.assertEqual(by_path["obra.localizacao"]["category"], "missing")
        self.assertEqual(by_path["ramal.primario_material"]["category"], "missing")
        self.assertEqual(by_path["mt.tensao_kv"]["category"], "default")
        self.assertEqual(by_path["mt.tensao_kv"]["current_value"], 13.8)
        self.assertEqual(by_path["mt.tensao_kv"]["editable_type"], "number")
        self.assertEqual(by_path["ramal.primario_diametro"]["category"], "low_confidence")
        self.assertEqual(by_path["pontos_utilizacao.total"]["category"], "conflict")
        self.assertIn("Tubulação", by_path["ramal.primario_diametro"]["evidence"])
        self.assertIn(
            "Valores encontrados: 35 e 34.",
            by_path["pontos_utilizacao.total"]["evidence"],
        )
        self.assertNotIn("{'status'", by_path["pontos_utilizacao.total"]["evidence"])

    def test_build_review_items_hides_fields_already_corrected_by_user(self) -> None:
        extraction_report = {
            "missing": ["obra.localizacao"],
            "evidence": {
                "obra.qtd_apartamentos": {
                    "value": 30,
                    "rule": "apartment_visual_labels",
                    "evidence": "APTO 001...801",
                    "confidence": "low",
                }
            },
            "user_corrections": {
                "obra.localizacao": "Rua das Flores",
                "obra.qtd_apartamentos": 29,
            },
        }

        items = build_review_items({"obra": {"qtd_apartamentos": 29}}, extraction_report)

        self.assertEqual(items, [])

    def test_build_review_items_infers_number_type_for_missing_numeric_fields(self) -> None:
        extraction_report = {
            "missing": [
                "mt.secao_cabo_mm2",
                "mt.tensao_kv",
                "mt.diametro_eletroduto_pol",
                "energia.tipo_subestacao",
                "gerador.tem_gerador",
            ]
        }

        items = build_review_items({"mt": {}, "energia": {}, "gerador": {}}, extraction_report)

        by_path = {item["field_path"]: item for item in items}
        self.assertEqual(by_path["mt.secao_cabo_mm2"]["editable_type"], "number")
        self.assertEqual(by_path["mt.tensao_kv"]["editable_type"], "number")
        self.assertEqual(by_path["mt.diametro_eletroduto_pol"]["editable_type"], "number")
        self.assertEqual(by_path["energia.tipo_subestacao"]["editable_type"], "text")
        self.assertEqual(by_path["gerador.tem_gerador"]["editable_type"], "boolean")

    def test_build_review_items_explains_unresolved_candidate_conflicts_for_engineers(self) -> None:
        extraction_report = {
            "cross_validation": {
                "conflicts": [
                    {
                        "field_path": "gerador.circuitos_atendidos",
                        "status": "unresolved",
                        "selected_value": None,
                        "candidates": [
                            {
                                "value": "bombas de recalque",
                                "occurrence_count": 1,
                                "files": ["planta-a.pdf"],
                            },
                            {
                                "value": "elevadores e iluminação de emergência",
                                "occurrence_count": 1,
                                "files": ["planta-b.pdf"],
                            },
                        ],
                    }
                ]
            }
        }

        items = build_review_items({"gerador": {}}, extraction_report)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["category"], "conflict")
        self.assertEqual(
            items[0]["reason"],
            "Foram encontrados valores diferentes para este campo e não houve critério seguro para escolher automaticamente. Informe o valor correto conforme o projeto.",
        )
        self.assertIn(
            "bombas de recalque (1 ocorrência, planta-a.pdf)",
            items[0]["evidence"],
        )
        self.assertIn(
            "elevadores e iluminação de emergência (1 ocorrência, planta-b.pdf)",
            items[0]["evidence"],
        )
        self.assertNotIn("{", items[0]["evidence"])


if __name__ == "__main__":
    unittest.main()
