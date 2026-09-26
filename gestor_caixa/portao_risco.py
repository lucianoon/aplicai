"""Portão determinístico de risco e conformidade regulatória (Suitability Zero-LLM)."""

from __future__ import annotations

from gestor_caixa.esquemas import ProjecaoCaixa30d, RegimeCliente


class PortaoRisco:
    """Implementa as travas de suitability e regulação bancária (CVM 30 / CMN 4.949)."""

    @staticmethod
    def avaliar_elegibilidade_investimento(projecao: ProjecaoCaixa30d) -> tuple[bool, str]:
        """Avalia se o cliente pode receber ofertas de aplicação financeira.

        Retorna (autorizado: bool, motivo_regulatorio: str).
        """
        # Trava 1: Saldo devedor imediato (Cheque Especial)
        if projecao.saldo_atual < 0:
            return False, "BLOQUEIO_CVM: Cliente com saldo devedor em conta corrente."

        # Trava 2: Superendividamento ou uso recente de rotativo
        if projecao.regime == RegimeCliente.DEFICIT_CRITICO:
            return False, "BLOQUEIO_SUITABILITY: Histórico de rotativo ou negativação ativa. Prioridade é estancar passivos."

        # Trava 3: Déficit projetado (saldo não cobre os compromissos fixos do mês)
        if projecao.regime == RegimeCliente.DEFICIT_PREVISTO:
            return False, (
                f"BLOQUEIO_LIQUIDEZ: Saldo livre projetado insuficiente para cobrir débitos "
                f"contratuais (próximo grande débito: {projecao.data_proximo_grande_debito})."
            )

        # Trava 4: Capital ocioso mínimo não atingido
        if projecao.saldo_livre_efetivo < 1000.0:
            return False, (
                "BLOQUEIO_COLCHAO: Saldo atual é necessário para honrar o colchão de segurança "
                "de despesas essenciais do mês."
            )

        return True, "AUTORIZADO_LIQUIDEZ_DIARIA"

    @staticmethod
    def avaliar_necessidade_alivio_passivo(projecao: ProjecaoCaixa30d) -> bool:
        """Determina se a jornada de alívio de dívida / parcelamento deve ser prioritária."""
        return projecao.regime in (RegimeCliente.DEFICIT_CRITICO, RegimeCliente.DEFICIT_PREVISTO)
