from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any


PORCENTAGEM_ENTRE_TRAFOS = "2%"
PORCENTAGEM_ENTRE_QUADROS = "3%"


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


def merge_context(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Deep merge: overrides take precedence over base at every nesting level."""
    result = deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_context(result[key], value)
        else:
            result[key] = value
    return result


def _ensure_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    section = payload.get(key)
    if isinstance(section, dict):
        return section
    return {}


def build_memorial_eletrico_v1_context(input_payload: dict[str, Any]) -> dict[str, Any]:
    context = deepcopy(input_payload)

    documento = _ensure_dict(context, "documento")
    documento.setdefault("data_atual", date.today().strftime("%d/%m/%Y"))
    context["documento"] = documento

    obra = _ensure_dict(context, "obra")
    obra.setdefault("porcentagem_entre_trafos", PORCENTAGEM_ENTRE_TRAFOS)
    obra.setdefault("porcentagem_entre_quadros", PORCENTAGEM_ENTRE_QUADROS)
    context["obra"] = obra

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
