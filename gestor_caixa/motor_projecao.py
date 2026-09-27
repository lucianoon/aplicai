"""Motor de projeção de fluxo de caixa determinístico e cálculo do colchão dinâmico."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from gestor_caixa.esquemas import (
    CompromissoContratual,
    ProjecaoCaixa30d,
    RegimeCliente,
    TipoCompromisso,
)

HORIZONTE_DIAS = 30
MARGEM_VARIAVEL_PCT_RENDA = 0.15      # supermercado, combustível, farmácia
CAPITAL_OCIOSO_MINIMO = 2000.0        # abaixo disso não há oferta de aplicação
SALDO_MINIMO_OPORTUNIDADE = 5000.0
ROTATIVO_12M_CRITICO = 3              # meses no rotativo que caracterizam déficit crítico

# (palavras-chave, tipo): a primeira que casar com a descrição vence
_TIPOS_POR_PALAVRA = (
    (("imovel", "imóvel", "financiamento", "habitac"), TipoCompromisso.FINANCIAMENTO_IMOVEL),
    (("escola", "faculdade", "mensalidade"), TipoCompromisso.MENSALIDADE_ESCOLAR),
    (("aluguel",), TipoCompromisso.ALUGUEL),
    (("condominio", "condomínio"), TipoCompromisso.CONDOMINIO),
    (("energia", "luz", "agua", "água"), TipoCompromisso.ENERGIA_AGUA),
    (("seguro",), TipoCompromisso.SEGURO_AUTO),
)


def _tipo(descricao: str) -> TipoCompromisso:
    desc = descricao.lower()
    for palavras, tipo in _TIPOS_POR_PALAVRA:
        if any(p in desc for p in palavras):
            return tipo
    return TipoCompromisso.OUTRO


class MotorProjecaoCaixa:
    """Calcula a projeção de 30 dias de caixa, colchão de segurança e capital ocioso."""

    @classmethod
    def extrair_compromissos_cliente(
        cls, cliente: dict[str, Any], hoje: date | None = None
    ) -> list[CompromissoContratual]:
        """Despesas fixas que vencem na janela de 30 dias, com o prazo vindo dos próprios dados.

        ``dia_offset`` (saídas previstas) e ``dias_ate_vencimento`` (fatura) são dias a partir de hoje.
        """
        hoje = hoje or date.today()
        compromissos: list[CompromissoContratual] = []

        def adicionar(tipo: TipoCompromisso, descricao: str, dias: int, valor: float, automatico: bool) -> None:
            dias = max(0, dias)  # vencido ainda é devido: entra como hoje
            if valor <= 0 or dias > HORIZONTE_DIAS:
                return
            compromissos.append(
                CompromissoContratual(
                    tipo=tipo,
                    descricao=descricao,
                    dias_ate_vencimento=dias,
                    dia_vencimento=(hoje + timedelta(days=dias)).day,
                    valor_estimado=round(valor, 2),
                    debito_automatico=automatico,
                )
            )

        for s in cliente.get("saidas_previstas", []):
            descricao = s.get("descricao") or "Despesa fixa prevista"
            adicionar(_tipo(descricao), descricao, int(s.get("dia_offset", 0)), float(s.get("valor", 0.0)), True)

        fatura = cliente.get("fatura", {})
        if fatura.get("status") in ("aberta", "paga_parcialmente"):
            em_aberto = float(fatura.get("valor_total", 0.0)) - float(fatura.get("pago", 0.0))
            adicionar(TipoCompromisso.FATURA_CARTAO, "Fatura de Cartão de Crédito",
                      int(fatura.get("dias_ate_vencimento", 0)), em_aberto, False)

        return compromissos

    @classmethod
    def projetar(
        cls,
        cliente_id: str,
        saldo_atual: float,
        renda_mensal: float,
        cliente_raw: dict[str, Any],
        hoje: date | None = None,
    ) -> ProjecaoCaixa30d:
        """Gera o diagnóstico completo de liquidez e colchão dinâmico."""
        hoje = hoje or date.today()
        compromissos = cls.extrair_compromissos_cliente(cliente_raw, hoje)
        total_fixos = round(sum(c.valor_estimado for c in compromissos), 2)
        margem_variavel = round(renda_mensal * MARGEM_VARIAVEL_PCT_RENDA, 2)

        # Colchão: todos os compromissos da janela de 30 dias + margem para o dia a dia.
        # Conservador de propósito: não conta com o salário que ainda não caiu.
        colchao_minimo = round(total_fixos + margem_variavel, 2)
        saldo_livre_efetivo = round(saldo_atual - colchao_minimo, 2)

        # Débito de referência para o resgate programado: o maior da janela (empate: o mais próximo)
        maior = min(compromissos, key=lambda c: (-c.valor_estimado, c.dias_ate_vencimento), default=None)

        perfil = cliente_raw.get("perfil_investidor") or {}
        historico_rotativo = cliente_raw.get("historico_rotativo_12m", 0)
        negativado = cliente_raw.get("negativado", False)

        if saldo_atual < 0 or historico_rotativo >= ROTATIVO_12M_CRITICO or negativado:
            regime = RegimeCliente.DEFICIT_CRITICO
        elif saldo_livre_efetivo < 0:
            regime = RegimeCliente.DEFICIT_PREVISTO
        elif saldo_livre_efetivo >= CAPITAL_OCIOSO_MINIMO and saldo_atual >= SALDO_MINIMO_OPORTUNIDADE:
            regime = RegimeCliente.OPORTUNIDADE_LIQUIDEZ
        else:
            regime = RegimeCliente.NEUTRO

        return ProjecaoCaixa30d(
            cliente_id=cliente_id,
            saldo_atual=round(saldo_atual, 2),
            renda_mensal_esperada=round(renda_mensal, 2),
            compromissos_identificados=compromissos,
            total_compromissos_fixos=total_fixos,
            margem_seguranca_variavel=margem_variavel,
            colchao_minimo_obrigatorio=colchao_minimo,
            saldo_livre_efetivo=max(0.0, saldo_livre_efetivo),
            regime=regime,
            data_proximo_grande_debito=f"{maior.descricao} (Dia {maior.dia_vencimento})" if maior else None,
            valor_proximo_grande_debito=maior.valor_estimado if maior else 0.0,
            dias_ate_proximo_debito=maior.dias_ate_vencimento if maior else None,
            perfil_investidor=perfil.get("perfil"),
            perfil_investidor_valido=bool(perfil.get("perfil")) and perfil.get("valido_ate", "") >= hoje.isoformat(),
        )
