from __future__ import annotations

from copy import deepcopy
from typing import Any


NAO_INCLUSOS_ITEM_KEYS = (
    "cpct",
    "cftv",
    "alarme_patrimonial",
    "sonorizacao",
    "alarme_incendio",
    "automacao",
)
NULLABLE_ENERGIA_KEYS = (
    "tipo_subestacao",
    "potencia_transformador_kva",
    "tap_descricao",
    "tensao_secundaria",
)


def _ensure_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    section = payload.get(key)
    if isinstance(section, dict):
        return section
    return {}


def build_memorial_eletrico_v1_context(input_payload: dict[str, Any]) -> dict[str, Any]:
    context = deepcopy(input_payload)

    nao_inclusos = _ensure_dict(context, "nao_inclusos")
    nao_inclusos["tem_itens"] = any(
        bool(nao_inclusos.get(item_key, False)) for item_key in NAO_INCLUSOS_ITEM_KEYS
    )
    context["nao_inclusos"] = nao_inclusos

    gerador = _ensure_dict(context, "gerador")
    if gerador.get("tipo_atendimento") != "parcial":
        gerador["circuitos_atendidos"] = None
    context["gerador"] = gerador

    energia = _ensure_dict(context, "energia")
    if energia.get("tem_subestacao") is False:
        for field_name in NULLABLE_ENERGIA_KEYS:
            energia.setdefault(field_name, None)
    context["energia"] = energia

    return context
