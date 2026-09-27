"""Contratos de dados e esquemas estritos (Pydantic v2) para o Gestor de Caixa e Liquidez."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class RegimeCliente(str, Enum):
    """Classificação determinística da saúde financeira do correntista."""
    DEFICIT_CRITICO = "deficit_critico"              # Saldo negativo ou rotativo ativo
    DEFICIT_PREVISTO = "deficit_previsto"            # Saldo livre projetado < 0
    NEUTRO = "neutro"                                # Equilíbrio sem capital ocioso relevante
    OPORTUNIDADE_LIQUIDEZ = "oportunidade_liquidez"  # Capital ocioso >= R$ 2.000 e saldo >= R$ 5.000


class TipoCompromisso(str, Enum):
    FINANCIAMENTO_IMOVEL = "financiamento_imovel"
    MENSALIDADE_ESCOLAR = "mensalidade_escolar"
    CONDOMINIO = "condominio"
    SEGURO_AUTO = "seguro_auto"
    ENERGIA_AGUA = "energia_agua"
    ALUGUEL = "aluguel"
    FATURA_CARTAO = "fatura_cartao"
    OUTRO = "outro"


class CompromissoContratual(BaseModel):
    """Despesa fixa futura já contratada ou prevista no calendário."""
    tipo: TipoCompromisso
    descricao: str
    dia_vencimento: int = Field(ge=1, le=31)
    dias_ate_vencimento: int = Field(default=0, ge=0)
    valor_estimado: float = Field(gt=0)
    debito_automatico: bool = True


class ProjecaoCaixa30d(BaseModel):
    """Resultado da projeção de fluxo de caixa determinística."""
    cliente_id: str
    saldo_atual: float
    renda_mensal_esperada: float
    compromissos_identificados: list[CompromissoContratual] = Field(default_factory=list)
    total_compromissos_fixos: float = 0.0
    margem_seguranca_variavel: float = 0.0
    colchao_minimo_obrigatorio: float = 0.0
    saldo_livre_efetivo: float = 0.0
    regime: RegimeCliente
    data_proximo_grande_debito: str | None = None
    valor_proximo_grande_debito: float = 0.0
    dias_ate_proximo_debito: int | None = None


class CotacaoInvestimento(BaseModel):
    """Cotação determinística de aplicação em CDB Liquidez Diária."""
    cotacao_id: str
    cliente_id: str
    valor_aplicacao: float = Field(gt=0)
    produto: str = "CDB Itaú Liquidez Diária (100% CDI)"
    taxa_anual_cdi: float = 10.75
    dias_permanencia: int = 30
    rendimento_bruto: float
    rendimento_liquido: float
    ir_aliquota: float = 22.5
    ir_valor: float
    iof_valor: float = 0.0
    data_resgate_programado: str | None = None
    motivo_resgate_programado: str | None = None
    expira_em_epoch: float


class TokenAutorizacao(BaseModel):
    """Token criptográfico para validação transacional (2-Phase Commit)."""
    token_jwt: str
    cotacao_id: str
    cliente_id: str
    acao: str  # "aplicar_cdb" | "resgatar_cdb" | "parcelar_fatura" | "pagar_fatura"
    valor: float
    expira_em_epoch: float


class ComprovanteTransacao(BaseModel):
    """Comprovante de execução retornado pelo Core Bancário."""
    id_transacao: str
    codigo_autenticacao: str
    status: str = "EFETIVADO"
    data_hora_utc: str
    cliente_id: str
    acao: str
    valor: float
    detalhes: dict[str, Any] = Field(default_factory=dict)
