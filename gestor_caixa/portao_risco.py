"""Portão determinístico de risco e conformidade regulatória (Suitability Zero-LLM)."""

from __future__ import annotations

from gestor_caixa.esquemas import ProjecaoCaixa30d, RegimeCliente

# O único produto oferecido é o mais conservador: CDB de liquidez diária, 100% do CDI, com FGC.
# Ele é adequado a qualquer perfil; a exigência é o perfil existir e estar dentro da validade.
PERFIS_ADEQUADOS_AO_PRODUTO = {"conservador", "moderado", "arrojado"}


class PortaoRisco:
    """Travas de política interna de suitability (inspiradas na CVM 30 e na Lei 14.181)."""

    @staticmethod
    def avaliar_elegibilidade_investimento(projecao: ProjecaoCaixa30d) -> tuple[bool, str]:
        """Avalia se o cliente pode receber ofertas de aplicação financeira.

        Retorna (autorizado: bool, motivo_regulatorio: str).
        """
        # Trava 1: Saldo devedor imediato (Cheque Especial)
        if projecao.saldo_atual < 0:
            return False, "BLOQUEIO_SALDO_DEVEDOR: Cliente com saldo devedor em conta corrente."

        # Trava 2: Superendividamento ou uso recente de rotativo
        if projecao.regime == RegimeCliente.DEFICIT_CRITICO:
            return False, "BLOQUEIO_SUITABILITY: Histórico de rotativo ou negativação ativa. Prioridade é estancar passivos."

        # Trava 3: Déficit projetado (saldo não cobre os compromissos fixos do mês)
        if projecao.regime == RegimeCliente.DEFICIT_PREVISTO:
            return False, (
                f"BLOQUEIO_LIQUIDEZ: Saldo livre projetado insuficiente para cobrir débitos "
                f"contratuais (próximo grande débito: {projecao.data_proximo_grande_debito})."
            )

        # Trava 4: Capital ocioso mínimo não atingido (mesmo critério do regime de oportunidade)
        if projecao.regime != RegimeCliente.OPORTUNIDADE_LIQUIDEZ:
            return False, (
                "BLOQUEIO_COLCHAO: Saldo atual é necessário para honrar o colchão de segurança "
                "de despesas essenciais do mês."
            )

        # Trava 5: adequação ao perfil de investidor (sem perfil válido não há oferta)
        if not projecao.perfil_investidor_valido or projecao.perfil_investidor not in PERFIS_ADEQUADOS_AO_PRODUTO:
            return False, (
                "BLOQUEIO_PERFIL_INVESTIDOR: Perfil de investidor ausente ou vencido. O cliente precisa "
                "responder o questionário de perfil antes de receber a oferta."
            )

        return True, "AUTORIZADO_LIQUIDEZ_DIARIA"

    @staticmethod
    def avaliar_necessidade_alivio_passivo(projecao: ProjecaoCaixa30d) -> bool:
        """Determina se a jornada de alívio de dívida / parcelamento deve ser prioritária."""
        return projecao.regime in (RegimeCliente.DEFICIT_CRITICO, RegimeCliente.DEFICIT_PREVISTO)
