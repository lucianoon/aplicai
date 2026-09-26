"""Testes unitários dos adaptadores de serviços gerenciados Google Cloud Platform (GCP).

Garante que o comportamento em fallback (offline/desligado) e as proteções de erro
funcionem sem quebrar a execução local ou a suíte de testes.
"""

from unittest.mock import MagicMock, patch

from copiloto_fatura.dlp_adapter import dlp_ativo, redigir_com_dlp
from proativo.gcp_adapters import (
    bigquery_ativo,
    carregar_clientes_bigquery,
    exportar_para_bigquery,
    publicar_gatilhos_pubsub,
    pubsub_ativo,
)


def test_dlp_ativo_por_padrao_e_falso():
    assert not dlp_ativo()


def test_redigir_com_dlp_retorna_none_quando_desativado():
    assert redigir_com_dlp("meu cpf é 123.456.789-00") is None


def test_redigir_com_dlp_com_mock(monkeypatch):
    monkeypatch.setenv("COPILOTO_USE_CLOUD_DLP", "1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "mock-project")

    with patch("google.cloud.dlp_v2.DlpServiceClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.item.value = "meu cpf é [BRAZIL_CPF_NUMBER]"
        mock_client.deidentify_content.return_value = mock_resp

        texto, contagem = redigir_com_dlp("meu cpf é 123.456.789-00")
        assert texto == "meu cpf é [BRAZIL_CPF_NUMBER]"


def test_pubsub_ativo_por_padrao_e_falso():
    assert not pubsub_ativo()


def test_publicar_gatilhos_pubsub_desativado_retorna_zero():
    gatilhos = [{"cliente_id": "C001", "prioridade": 1}]
    assert publicar_gatilhos_pubsub(gatilhos) == 0


def test_publicar_gatilhos_pubsub_com_mock():
    gatilhos = [
        {"cliente_id": "C001", "prioridade": 1, "canal": "whatsapp"},
        {"cliente_id": "C002", "prioridade": 2, "canal": "app"},
    ]

    with patch("google.cloud.pubsub_v1.PublisherClient") as mock_pub_cls:
        mock_pub = MagicMock()
        mock_pub_cls.return_value = mock_pub
        mock_future = MagicMock()
        mock_future.result.return_value = "msg-id"
        mock_pub.publish.return_value = mock_future

        total = publicar_gatilhos_pubsub(gatilhos, project_id="proj", topic_id="topico-teste")
        assert total == 2
        assert mock_pub.publish.call_count == 2


def test_bigquery_ativo_por_padrao_e_falso():
    assert not bigquery_ativo()


def test_carregar_bigquery_desativado_retorna_none():
    assert carregar_clientes_bigquery() is None


def test_exportar_bigquery_com_mock(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-teste")

    with patch("google.cloud.bigquery.Client") as mock_bq_cls:
        mock_client = MagicMock()
        mock_bq_cls.return_value = mock_client
        mock_client.insert_rows_json.return_value = []  # sem erros

        clientes = [{"id": "C001", "nome": "Ana"}]
        sucesso = exportar_para_bigquery(clientes, project_id="proj-teste")
        assert sucesso is True
        mock_client.insert_rows_json.assert_called_once()
