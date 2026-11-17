from __future__ import annotations

from copy import deepcopy
from datetime import date
import unicodedata
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


CANTEIRO_DEFAULTS: dict[str, dict[str, Any]] = {
    "energia": {
        "tap_descricao": (
            "Tap 1 – 13.800 V; Tap 2 – 13.200 V; Tap 3 – 12.600 V; "
            "Tap 4 – 12.000 V; Tap 5 – 11.400 V."
        ),
        "tensao_secundaria": "380 V entre fases e 220 V entre fases e neutro",
    },
    "aterramento": {"tipo_sistema": "TN-S"},
    "mt": {"tensao_kv": 13.8},
}
QUADRO_DESCRICOES_CONHECIDAS: dict[str, str] = {
    "QGBT": "Concentra todos os demais quadros e equipamentos específicos de maior potência.",
    "QDLTTORRE": "Circuitos de iluminação e tomadas para uso durante a execução da obra.",
    "QDAPOIO": "Circuitos de luz, TUGs e TUEs de dormitórios, vestiários e refeitórios.",
    "QDSTAND": "Circuitos de luz, TUGs e TUEs do stand de vendas e escritório.",
    "QDMOVEL": "Equipamentos móveis, como guinchos e vibradores.",
}


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
    if gerador.get("tem_gerador") is None:
        qtd = gerador.get("qtd")
        if isinstance(qtd, int) and not isinstance(qtd, bool) and qtd > 0:
            gerador["tem_gerador"] = True
        else:
            gerador["tem_gerador"] = False
    if gerador.get("tem_gerador") is False:
        gerador["qtd"] = 0
        gerador["potencia_kva"] = 0
        if gerador.get("tipo_atendimento") is None:
            gerador["tipo_atendimento"] = "condominio"
    if gerador.get("tipo_atendimento") != "parcial":
        gerador["circuitos_atendidos"] = None
    context["gerador"] = gerador

    energia = _ensure_dict(context, "energia")
    if energia.get("tem_subestacao") is False:
        for field_name in NULLABLE_ENERGIA_KEYS:
            energia.setdefault(field_name, None)
    context["energia"] = energia

    mt = _ensure_dict(context, "mt")
    context["mt"] = mt

    return context


def normalize_quadro_key(nome: Any) -> str:
    text = unicodedata.normalize("NFKD", str(nome or ""))
    text = text.encode("ascii", "ignore").decode("ascii").upper()
    return "".join(ch for ch in text if ch.isalnum())


def _format_carga_w(carga_w: Any) -> str | None:
    if isinstance(carga_w, bool) or not isinstance(carga_w, (int, float)):
        return None
    return f"{int(round(carga_w)):,} W".replace(",", ".")


def build_memorial_eletrico_canteiro_v1_context(
    input_payload: dict[str, Any],
) -> dict[str, Any]:
    context = deepcopy(input_payload)

    documento = _ensure_dict(context, "documento")
    documento.setdefault("data_atual", date.today().strftime("%d/%m/%Y"))
    context["documento"] = documento

    obra = _ensure_dict(context, "obra")
    obra.setdefault("porcentagem_entre_trafos", PORCENTAGEM_ENTRE_TRAFOS)
    obra.setdefault("porcentagem_entre_quadros", PORCENTAGEM_ENTRE_QUADROS)
    context["obra"] = obra

    for section_name, defaults in CANTEIRO_DEFAULTS.items():
        section = _ensure_dict(context, section_name)
        for key, value in defaults.items():
            if section.get(key) is None:
                section[key] = deepcopy(value)
        context[section_name] = section

    energia = context["energia"]
    if energia.get("tem_subestacao") is False:
        for field_name in NULLABLE_ENERGIA_KEYS:
            energia[field_name] = None

    quadros = context.get("quadros")
    if isinstance(quadros, list):
        for quadro in quadros:
            if not isinstance(quadro, dict):
                continue
            carga_formatada = _format_carga_w(quadro.get("carga_w"))
            if carga_formatada is not None:
                quadro["carga_formatada"] = carga_formatada
            if quadro.get("descricao") is None:
                quadro["descricao"] = QUADRO_DESCRICOES_CONHECIDAS.get(
                    normalize_quadro_key(quadro.get("nome"))
                )

    return context


def build_memorial_telecom_v1_context(input_payload: dict[str, Any]) -> dict[str, Any]:
    context = deepcopy(input_payload)

    documento = _ensure_dict(context, "documento")
    documento.setdefault("data_atual", date.today().strftime("%d/%m/%Y"))
    context["documento"] = documento

    obra = _ensure_dict(context, "obra")
    context["obra"] = obra

    return context


def build_memorial_gas_natural_v1_context(input_payload: dict[str, Any]) -> dict[str, Any]:
    context = deepcopy(input_payload)

    documento = _ensure_dict(context, "documento")
    documento.setdefault("data_atual", date.today().strftime("%d/%m/%Y"))
    context["documento"] = documento

    return context


def build_memorial_glp_v1_context(input_payload: dict[str, Any]) -> dict[str, Any]:
    context = deepcopy(input_payload)

    documento = _ensure_dict(context, "documento")
    documento.setdefault("data_atual", date.today().strftime("%d/%m/%Y"))
    context["documento"] = documento

    return context


def build_memorial_glp_v2_context(input_payload: dict[str, Any]) -> dict[str, Any]:
    context = deepcopy(input_payload)

    documento = _ensure_dict(context, "documento")
    documento.setdefault("data_atual", date.today().strftime("%d/%m/%Y"))
    context["documento"] = documento

    context.setdefault("context_version", "glp_v2")
    context.setdefault("template_version", "glp_v2")

    return context
