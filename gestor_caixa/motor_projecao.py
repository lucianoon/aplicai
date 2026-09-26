"""Motor de projeção de fluxo de caixa determinístico e cálculo do colchão dinâmico."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from gestor_caixa.esquemas import (
    CompromissoContratual,
    ProjecaoCaixa30d,
    RegimeCliente,
    TipoCompromisso,
)


class MotorProjecaoCaixa:
    """Calcula a projeção de 30 dias de caixa, colchão de segurança e capital ocioso."""

    @classmethod
    def extrair_compromissos_cliente(cls, cliente: dict[str, Any]) -> list[CompromissoContratual]:
        """Identifica despesas fixas conhecidas da base de dados e transações."""
        compromissos: list[CompromissoContratual] = []

        # 1. Compromissos explícitos em 'saidas_previstas'
        for s in cliente.get("saidas_previstas", []):
            desc = s.get("descricao", "").lower()
            tipo = TipoCompromisso.OUTRO
            dia = s.get("dia_offset", 10)

            if "imovel" in desc or "financiamento" in desc or "habitac" in desc:
                tipo = TipoCompromisso.FINANCIAMENTO_IMOVEL
                dia = 8  # data padrão identificada na base de dados
            elif "escola" in desc or "faculdade" in desc or "mensalidade" in desc:
                tipo = TipoCompromisso.MENSALIDADE_ESCOLAR
                dia = 10
            elif "condominio" in desc:
                tipo = TipoCompromisso.CONDOMINIO
                dia = 10
            elif "energia" in desc or "luz" in desc or "agua" in desc:
                tipo = TipoCompromisso.ENERGIA_AGUA
                dia = 15
            elif "seguro" in desc:
                tipo = TipoCompromisso.SEGURO_AUTO
                dia = 28

            compromissos.append(
                CompromissoContratual(
                    tipo=tipo,
                    descricao=s.get("descricao", "Despesa fixa prevista"),
                    dia_vencimento=dia,
                    valor_estimado=float(s.get("valor", 0.0)),
                    debito_automatico=True,
                )
            )

        # 2. Fatura aberta do cartão de crédito
        fatura = cliente.get("fatura", {})
        if fatura.get("status") in ("aberta", "paga_parcialmente"):
            valor_fatura = float(fatura.get("valor_total", 0.0)) - float(fatura.get("pago", 0.0))
            if valor_fatura > 0:
                dias_venc = int(fatura.get("dias_ate_vencimento", 5))
                # Estima dia de vencimento baseado em hoje
                dia_venc_fatura = min(30, max(1, 15 + (dias_venc % 15)))
                compromissos.append(
                    CompromissoContratual(
                        tipo=TipoCompromisso.FATURA_CARTAO,
                        descricao="Fatura de Cartão de Crédito",
                        dia_vencimento=dia_venc_fatura,
                        valor_estimado=round(valor_fatura, 2),
                        debito_automatico=False,
                    )
                )

        return compromissos

    @classmethod
    def projetar(
        cls,
        cliente_id: str,
        saldo_atual: float,
        renda_mensal: float,
        cliente_raw: dict[str, Any],
        dia_do_mes_atual: int = 5,
    ) -> ProjecaoCaixa30d:
        """Gera o diagnóstico completo de liquidez e colchão dinâmico."""
        compromissos = cls.extrair_compromissos_cliente(cliente_raw)

        # Total de débitos fixos conhecidos
        total_fixos = sum(c.valor_estimado for c in compromissos)

        # Margem de segurança para despesas essenciais diárias (supermercado, combustível, farmácia)
        # Calibrada em 15% da renda mensal
        margem_variavel = round(renda_mensal * 0.15, 2)

        # Próximo grande débito (destaque para financiamento dia 8 ou fatura)
        proximo_grande = None
        valor_grande = 0.0
        menor_delta_dia = 999

        for c in compromissos:
            delta = (c.dia_vencimento - dia_do_mes_atual) % 30
            if delta < menor_delta_dia and c.valor_estimado > valor_grande:
                menor_delta_dia = delta
                valor_grande = c.valor_estimado
                proximo_grande = f"{c.descricao} (Dia {c.dia_vencimento})"

        # Cálculo do Colchão de Segurança Mínimo:
        # Reserva os débitos que vencem antes do próximo salário
        colchao_minimo = round(total_fixos + margem_variavel, 2)
        saldo_livre_efetivo = round(saldo_atual - colchao_minimo, 2)

        # Classificação do Regime
        historico_rotativo = cliente_raw.get("historico_rotativo_12m", 0)
        negativado = cliente_raw.get("negativado", False)

        if saldo_atual < 0 or historico_rotativo >= 3 or negativado:
            regime = RegimeCliente.DEFICIT_CRITICO
        elif saldo_livre_efetivo < 0 or (saldo_atual < total_fixos):
            regime = RegimeCliente.DEFICIT_PREVISTO
        elif saldo_livre_efetivo >= 2000.0 and saldo_atual >= 5000.0:
            regime = RegimeCliente.OPORTUNIDADE_LIQUIDEZ
        else:
            regime = RegimeCliente.NEUTRO

        return ProjecaoCaixa30d(
            cliente_id=cliente_id,
            saldo_atual=round(saldo_atual, 2),
            renda_mensal_esperada=round(renda_mensal, 2),
            compromissos_identificados=compromissos,
            total_compromissos_fixos=round(total_fixos, 2),
            margem_seguranca_variavel=margem_variavel,
            colchao_minimo_obrigatorio=colchao_minimo,
            saldo_livre_efetivo=max(0.0, saldo_livre_efetivo),
            regime=regime,
            data_proximo_grande_debito=proximo_grande,
            valor_proximo_grande_debito=round(valor_grande, 2),
            dias_ate_proximo_debito=menor_delta_dia if menor_delta_dia < 999 else None,
        )
