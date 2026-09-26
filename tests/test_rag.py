from copiloto_fatura.rag import MecanismoRAG, consultar_regras_e_politicas, similaridade_cosseno


def test_similaridade_cosseno():
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]
    assert abs(similaridade_cosseno(v1, v2) - 1.0) < 1e-5
    assert abs(similaridade_cosseno(v1, v3) - 0.0) < 1e-5


def test_rag_busca_rotativo():
    rag = MecanismoRAG()
    resultados = rag.buscar("O que acontece se eu ficar mais de 30 dias no rotativo?")
    assert len(resultados) > 0
    primeiro = resultados[0]
    assert "4549" in primeiro["id"] or "ROTATIVO" in primeiro["id"]
    assert "rotativo" in primeiro["conteudo"].lower()


def test_rag_busca_iof():
    rag = MecanismoRAG()
    resultados = rag.buscar("Qual é a alíquota de IOF para parcelamento de fatura?")
    assert len(resultados) > 0
    assert any("IOF" in r["id"] or "0,38%" in r["conteudo"] for r in resultados)


def test_rag_tool_format():
    texto = consultar_regras_e_politicas("Posso transferir minha dívida para outro banco?")
    assert isinstance(texto, str)
    assert len(texto) > 20


def test_rag_busca_resolucao_conjunta_8():
    rag = MecanismoRAG()
    resultados = rag.buscar("O que diz a Resolução Conjunta nº 8 sobre educação financeira?")
    assert len(resultados) > 0
    primeiro = resultados[0]
    assert "RC8" in primeiro["id"] or "EDUCACAO" in primeiro["id"]
    assert "educação financeira" in primeiro["conteudo"].lower() or "educacao financeira" in primeiro["conteudo"].lower()
