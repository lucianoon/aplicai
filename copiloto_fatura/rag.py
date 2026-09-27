"""Mecanismo de RAG e Vector Search do Aplicaí.

Provê recuperação semântica sobre regulamentações financeiras, normas do Bacen,
regras de IOF e políticas de parcelamento de fatura.

Arquitetura:
1. Base de Conhecimento Regulatório (Resolução CMN 4.549, Resolução Conjunta nº 8,
   Lei do Superendividamento, IOF).
2. Embeddings via Vertex AI (modelo 'text-embedding-004', 768 dimensões).
3. Busca Vetorial por Similaridade de Cosseno com filtro de metadados.
4. Fallback léxico determinístico (BM25 simplificado) caso esteja offline ou sem cota,
   garantindo funcionamento contínuo e sem falhas no palco do hackathon.
"""

from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("copiloto_fatura.rag")

# Base de Conhecimento Regulatório Bancário indexada
BASE_CONHECIMENTO: list[dict[str, str]] = [
    {
        "id": "BACEN-CMN-4549-ROTATIVO",
        "titulo": "Resolução CMN nº 4.549/2017 - Limitação do Crédito Rotativo a 30 dias",
        "categoria": "regulamentacao",
        "conteudo": (
            "O saldo devedor não liquidado da fatura de cartão de crédito só pode permanecer no "
            "crédito rotativo até o vencimento da fatura subsequente (máximo de 30 dias). Após esse prazo, "
            "a instituição financeira é obrigada por norma do Banco Central a transferir o saldo devedor "
            "remanescente para uma linha de crédito parcelado com condições financeiras mais vantajosas "
            "do que as do rotativo."
        ),
    },
    {
        "id": "IOF-DECRETO-6306-CREDITO",
        "titulo": "Decreto nº 6.306/2007 - Incidência de IOF em Operações de Crédito e Parcelamento",
        "categoria": "tributacao",
        "conteudo": (
            "Sobre operações de parcelamento de fatura, crédito pessoal e rotativo incide o Imposto sobre "
            "Operações Financeiras (IOF). A alíquota é composta por uma parcela fixa de 0,38% aplicada "
            "sobre o valor principal da operação somada a uma alíquota diária de 0,0082% ao dia (limitada "
            "a 3,00% ao ano para pessoas físicas)."
        ),
    },
    {
        "id": "LEI-SUPERENDIVIDAMENTO-14181",
        "titulo": "Lei nº 14.181/2021 - Prevenção ao Superendividamento e Crédito Responsável",
        "categoria": "protecao_consumidor",
        "conteudo": (
            "A concessão de crédito e renegociação de dívidas deve preservar o 'mínimo existencial' do "
            "consumidor e respeitar sua capacidade real de pagamento. É vedada a oferta de crédito "
            "predatório ou sem consulta prévia ao fluxo de rendimentos. Instituições devem oferecer "
            "orientação e canais de acolhimento quando detectada incapacidade material de subsistência."
        ),
    },
    {
        "id": "FATURA-PAGAMENTO-MINIMO",
        "titulo": "Regra de Pagamento Mínimo e Encargos Financeiros",
        "categoria": "politica_interna",
        "conteudo": (
            "O pagamento mínimo corresponde a 15% do valor total da fatura. Ao pagar o valor mínimo ou qualquer "
            "quantia inferior ao total, a diferença não paga entra automaticamente no crédito rotativo até a "
            "próxima fatura, incidindo juros remuneratórios e tributos. O pagamento de entrada associado a "
            "parcelamento com taxa prefixada é sempre financeiramente superior ao pagamento do mínimo isolado."
        ),
    },
    {
        "id": "PORTABILIDADE-DIVIDA-RESOLUCAO-5112",
        "titulo": "Resolução CMN nº 5.112/2023 - Portabilidade da Dívida do Cartão",
        "categoria": "regulamentacao",
        "conteudo": (
            "O cliente tem direito à portabilidade gratuita do saldo devedor do cartão de crédito para outra "
            "instituição financeira autorizada que ofereça proposta de crédito com juros menores. A instituição "
            "credora original tem o direito de contrapropor uma oferta de refinanciamento equivalente."
        ),
    },
    {
        "id": "BACEN-RC8-EDUCACAO-FINANCEIRA",
        "titulo": "Resolução Conjunta nº 8/2023 - Política de Educação Financeira",
        "categoria": "educacao_financeira",
        "conteudo": (
            "A Resolução Conjunta nº 8, de 2023, do Conselho Monetário Nacional e do Banco Central, institui "
            "a política de educação financeira no Sistema Financeiro Nacional. As instituições devem oferecer "
            "informação clara, adequada e oportuna para a pessoa entender o próprio contexto, antecipar o "
            "efeito de uma decisão e orientar o próximo passo com autonomia. A orientação precisa caber nos "
            "produtos disponíveis e no público atendido; o dever é ajudar a decidir com informação, não só "
            "ensinar conceito e não substituir a escolha da cliente."
        ),
    },
]


def _produto_escalar(v1: list[float], v2: list[float]) -> float:
    return sum(a * b for a, b in zip(v1, v2))


def _norma(v: list[float]) -> float:
    return math.sqrt(sum(a * a for a in v))


def similaridade_cosseno(v1: list[float], v2: list[float]) -> float:
    """Calcula a similaridade de cosseno entre dois vetores normalizados."""
    n1, n2 = _norma(v1), _norma(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return _produto_escalar(v1, v2) / (n1 * n2)


@dataclass
class ItemBaseConhecimento:
    id: str
    titulo: str
    categoria: str
    conteudo: str
    vetor: list[float] | None = None


class MecanismoRAG:
    """Gerenciador de RAG e Busca Vetorial regulatória."""

    def __init__(self, itens: list[dict[str, str]] | None = None):
        self.itens_brutos = itens or BASE_CONHECIMENTO
        self.itens: list[ItemBaseConhecimento] = [
            ItemBaseConhecimento(
                id=item["id"],
                titulo=item["titulo"],
                categoria=item["categoria"],
                conteudo=item["conteudo"],
            )
            for item in self.itens_brutos
        ]
        self._cliente_embeddings = None
        self._vetorizado: bool = False

    def _obter_cliente_vertex(self):
        """Inicializa o cliente do Vertex AI Text Embedding caso as variáveis estejam disponíveis."""
        if self._cliente_embeddings is not None:
            return self._cliente_embeddings

        projeto = os.getenv("GOOGLE_CLOUD_PROJECT")
        localizacao = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        if not projeto:
            return None

        try:
            from vertexai.language_models import TextEmbeddingModel

            self._cliente_embeddings = TextEmbeddingModel.from_pretrained("text-embedding-004")
            return self._cliente_embeddings
        except Exception as exc:
            logger.debug("Vertex AI Embeddings não disponível (%s); usando busca léxica de fallback.", exc)
            return None

    def indexar(self) -> None:
        """Gera os embeddings da base via Vertex AI quando conectado."""
        if self._vetorizado:
            return

        cliente = self._obter_cliente_vertex()
        if not cliente:
            self._vetorizado = True
            return

        try:
            textos = [f"{it.titulo}\n{it.conteudo}" for it in self.itens]
            embeddings = cliente.get_embeddings(textos)
            for it, emb in zip(self.itens, embeddings):
                it.vetor = emb.values
            self._vetorizado = True
            logger.info("Base regulatória indexada com sucesso no Vertex AI Text Embeddings.")
        except Exception as exc:
            logger.warning("Falha ao gerar embeddings no Vertex AI: %s. Mantendo fallback léxico.", exc)
            self._vetorizado = True

    def buscar(self, consulta: str, top_k: int = 2) -> list[dict[str, Any]]:
        """Realiza busca vetorial ou léxica dependendo do ambiente."""
        self.indexar()
        cliente = self._obter_cliente_vertex()

        # 1. Tentar busca vetorial se tiver embeddings
        if cliente and any(it.vetor is not None for it in self.itens):
            try:
                emb_consulta = cliente.get_embeddings([consulta])[0].values
                pontuados = []
                for it in self.itens:
                    if it.vetor is not None:
                        score = similaridade_cosseno(emb_consulta, it.vetor)
                        pontuados.append((score, it))
                pontuados.sort(key=lambda x: x[0], reverse=True)
                return [
                    {
                        "id": it.id,
                        "titulo": it.titulo,
                        "categoria": it.categoria,
                        "conteudo": it.conteudo,
                        "score": round(score, 4),
                        "metodo": "vetorial_vertex_ai",
                    }
                    for score, it in pontuados[:top_k]
                ]
            except Exception as exc:
                logger.warning("Falha na busca vetorial (%s); caindo para busca léxica.", exc)

        # 2. Fallback determinístico (BM25 / Keyword matching com peso em títulos)
        termos_consulta = set(re.findall(r"\w+", consulta.lower()))
        pontuados_lex = []
        for it in self.itens:
            score = 0.0
            texto_completo = f"{it.titulo} {it.conteudo}".lower()
            palavras = re.findall(r"\w+", texto_completo)
            for termo in termos_consulta:
                if len(termo) <= 2:
                    continue
                if termo in it.titulo.lower():
                    score += 3.0
                score += palavras.count(termo) * 1.0

            if score > 0:
                pontuados_lex.append((score, it))

        pontuados_lex.sort(key=lambda x: x[0], reverse=True)
        if not pontuados_lex:
            pontuados_lex = [(1.0, it) for it in self.itens[:top_k]]

        return [
            {
                "id": it.id,
                "titulo": it.titulo,
                "categoria": it.categoria,
                "conteudo": it.conteudo,
                "score": round(score, 2),
                "metodo": "lexico_determinista",
            }
            for score, it in pontuados_lex[:top_k]
        ]


_INSTANCIA_RAG: MecanismoRAG | None = None


def obter_mecanismo_rag() -> MecanismoRAG:
    global _INSTANCIA_RAG
    if _INSTANCIA_RAG is None:
        _INSTANCIA_RAG = MecanismoRAG()
    return _INSTANCIA_RAG


def consultar_regras_e_politicas(consulta: str, top_k: int = 2) -> str:
    """Consulta normas do Banco Central (CMN 4.549, RC 8), IOF e regras de parcelamento de fatura.

    Use esta ferramenta quando o cliente perguntar sobre normas bancárias, direitos do
    consumidor, regras de rotativo (prazo de 30 dias), tributação (IOF), portabilidade de dívida
    ou educação financeira (Resolução Conjunta nº 8).

    Args:
        consulta: pergunta ou termo de busca (ex: "quanto tempo posso ficar no rotativo?", "qual o IOF?").
        top_k: número de artigos ou normas mais relevantes a retornar.
    """
    rag = obter_mecanismo_rag()
    resultados = rag.buscar(consulta, top_k=top_k)

    trechos = []
    for r in resultados:
        trechos.append(f"[{r['id']} - {r['titulo']}]\n{r['conteudo']}")
    return "\n\n".join(trechos)
