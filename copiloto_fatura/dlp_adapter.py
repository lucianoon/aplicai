"""Adaptador para Google Cloud Sensitive Data Protection (Cloud DLP / Model Armor).

Permite inspecionar e redigir dados pessoais sensíveis (PII) usando as APIs
gerenciadas da Google Cloud quando COPILOTO_USE_CLOUD_DLP=1.

Se a variável estiver desligada ou ocorrer falha de conectividade / credenciais,
o sistema executa fallback gracioso e transparente para o redator determinístico local
(regex), garantindo resiliência total mesmo em modo offline ou sem internet.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

INFOTYPES_PADRAO = [
    {"name": "BRAZIL_CPF_NUMBER"},
    {"name": "CREDIT_CARD_NUMBER"},
    {"name": "EMAIL_ADDRESS"},
    {"name": "PHONE_NUMBER"},
    {"name": "STREET_ADDRESS"},
    {"name": "PERSON_NAME"},
]


def dlp_ativo() -> bool:
    """Retorna True se a integração com Cloud DLP estiver explicitamente habilitada."""
    return os.getenv("COPILOTO_USE_CLOUD_DLP", "0").strip() in {"1", "true", "True"}


def redigir_com_dlp(texto: str, project_id: str | None = None) -> tuple[str, dict[str, int]] | None:
    """Redige PII usando Google Cloud DLP API.

    Retorna (texto_redigido, contagem) ou None se desativado/falha.
    """
    if not dlp_ativo():
        return None

    projeto = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not projeto:
        logger.warning("COPILOTO_USE_CLOUD_DLP=1, mas GOOGLE_CLOUD_PROJECT não foi informado.")
        return None

    try:
        from google.cloud import dlp_v2

        cliente = dlp_v2.DlpServiceClient()
        parent = f"projects/{projeto}/locations/global"

        item = {"value": texto}
        inspect_config = {
            "info_types": INFOTYPES_PADRAO,
            "min_likelihood": dlp_v2.Likelihood.POSSIBLE,
            "include_quote": False,
        }

        # Configuração de transformação: substitui pelo nome do tipo identificado
        deidentify_config = {
            "info_type_transformations": {
                "transformations": [
                    {
                        "primitive_transformation": {
                            "replace_with_info_type_config": {}
                        }
                    }
                ]
            }
        }

        resposta = cliente.deidentify_content(
            request={
                "parent": parent,
                "deidentify_config": deidentify_config,
                "inspect_config": inspect_config,
                "item": item,
            }
        )

        texto_redigido = resposta.item.value
        # Coleta contagem a partir do overview de transformações
        contagem: dict[str, int] = {}
        if hasattr(resposta, "overview") and hasattr(resposta.overview, "transformation_summaries"):
            for summary in resposta.overview.transformation_summaries:
                info_name = summary.info_type.name if summary.info_type else "PII"
                contagem[info_name] = summary.transformed_bytes or 1

        return texto_redigido, contagem
    except Exception as exc:
        logger.warning("Falha ao invocar Cloud DLP: %s. Aplicando fallback para regex.", exc)
        return None
