"""Roda o evalset com o AgentEvaluator do ADK (precisa de GOOGLE_API_KEY ou modo enterprise).

    uv run pytest eval -s
ou  (com PYTHONPATH=.) uv run adk eval copiloto_fatura eval/copiloto_fatura.evalset.json --config_file_path eval/test_config.json

Cada pasta tem seu test_config.json. Gasta tokens; fica fora do `uv run pytest` padrão (testpaths = tests).
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from google.adk.evaluation.agent_evaluator import AgentEvaluator

RAIZ = Path(__file__).resolve().parents[1]
load_dotenv(RAIZ / ".env")

pytestmark = pytest.mark.skipif(
    not (os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_GENAI_USE_ENTERPRISE") == "1"),
    reason="sem credencial Gemini (GOOGLE_API_KEY ou GOOGLE_GENAI_USE_ENTERPRISE=1)",
)


async def test_evalset_copiloto():
    await AgentEvaluator.evaluate(
        agent_module="copiloto_fatura",
        eval_dataset_file_path_or_dir=str(RAIZ / "eval" / "copiloto_fatura.evalset.json"),
        num_runs=1,
    )


async def test_evalset_acoes():
    """Ações pausam para aprovação: só a trajetória conta (ver eval/acoes/test_config.json)."""
    await AgentEvaluator.evaluate(
        agent_module="copiloto_fatura",
        eval_dataset_file_path_or_dir=str(RAIZ / "eval" / "acoes" / "acoes.evalset.json"),
        num_runs=1,
    )
