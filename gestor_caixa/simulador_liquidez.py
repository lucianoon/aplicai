"""Simulador financeiro determinístico de liquidez e investimentos (CDB 100% CDI).

Toda a matemática de rendimento, IOF e IR regressivo fica aqui, em código puro.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from gestor_caixa.esquemas import CotacaoInvestimento

# Tabela regressiva de IOF para resgate em menos de 30 dias corridos
TABELA_IOF = {
    1: 0.96, 2: 0.93, 3: 0.90, 4: 0.86, 5: 0.83, 6: 0.80, 7: 0.76, 8: 0.73, 9: 0.70,
    10: 0.66, 11: 0.63, 12: 0.60, 13: 0.56, 14: 0.53, 15: 0.50, 16: 0.46, 17: 0.43,
    18: 0.40, 19: 0.36, 20: 0.33, 21: 0.30, 22: 0.26, 23: 0.23, 24: 0.20, 25: 0.16,
    26: 0.13, 27: 0.10, 28: 0.06, 29: 0.03, 30: 0.00,
}


@dataclass(frozen=True)
class ParametrosInvestimento:
    cdi_anual: float = 0.1075          # 10,75% ao ano
    dias_uteis_ano: int = 252
    dias_corridos_ano: int = 365
    validade_cotacao_segundos: int = 900  # 15 minutos


PARAMS_INV = ParametrosInvestimento()


class SimuladorLiquidez:
    @staticmethod
    def aliquota_ir(dias_corridos: int) -> float:
        """Tabela regressiva de IR sobre rendimentos de renda fixa."""
        if dias_corridos <= 180:
            return 0.225
        elif dias_corridos <= 360:
            return 0.20
        elif dias_corridos <= 720:
            return 0.175
        return 0.15

    @classmethod
    def simular_rendimento(
        cls,
        valor: float,
        dias_corridos: int = 30,
        p: ParametrosInvestimento = PARAMS_INV,
    ) -> dict[str, float]:
        """Calcula rendimento bruto, IOF, IR e rendimento líquido exato."""
        if valor <= 0:
            raise ValueError("Valor de aplicação deve ser positivo")
        if dias_corridos <= 0:
            raise ValueError("Dias de permanência devem ser >= 1")

        # Conversão aproximada para dias úteis (proporção 252 / 365)
        dias_uteis = max(1, round(dias_corridos * (p.dias_uteis_ano / p.dias_corridos_ano)))
        taxa_diaria = (1.0 + p.cdi_anual) ** (1.0 / p.dias_uteis_ano) - 1.0

        fator_acumulado = (1.0 + taxa_diaria) ** dias_uteis
        rendimento_bruto = round(valor * (fator_acumulado - 1.0), 2)

        # IOF incide sobre o rendimento bruto nos primeiros 29 dias
        aliq_iof = TABELA_IOF.get(dias_corridos, 0.0) if dias_corridos < 30 else 0.0
        iof_valor = round(rendimento_bruto * aliq_iof, 2)

        base_ir = max(0.0, rendimento_bruto - iof_valor)
        aliq_ir = cls.aliquota_ir(dias_corridos)
        ir_valor = round(base_ir * aliq_ir, 2)

        rendimento_liquido = round(rendimento_bruto - iof_valor - ir_valor, 2)

        return {
            "valor_aplicado": round(valor, 2),
            "dias_corridos": dias_corridos,
            "dias_uteis": dias_uteis,
            "rendimento_bruto": rendimento_bruto,
            "iof_valor": iof_valor,
            "ir_aliquota_pct": round(aliq_ir * 100, 1),
            "ir_valor": ir_valor,
            "rendimento_liquido": rendimento_liquido,
            "valor_final_liquido": round(valor + rendimento_liquido, 2),
        }

    @classmethod
    def gerar_cotacao(
        cls,
        cliente_id: str,
        valor: float,
        dias_corridos: int = 30,
        data_resgate: str | None = None,
        motivo_resgate: str | None = None,
        p: ParametrosInvestimento = PARAMS_INV,
    ) -> CotacaoInvestimento:
        """Gera DTO de cotação com prazo de expiração de 15 minutos."""
        calc = cls.simular_rendimento(valor, dias_corridos, p)
        cotacao_id = f"COT-INV-{cliente_id}-{int(time.time())}"

        return CotacaoInvestimento(
            cotacao_id=cotacao_id,
            cliente_id=cliente_id,
            valor_aplicacao=calc["valor_aplicado"],
            produto="CDB Itaú Liquidez Diária (100% CDI)",
            taxa_anual_cdi=round(p.cdi_anual * 100, 2),
            dias_permanencia=dias_corridos,
            rendimento_bruto=calc["rendimento_bruto"],
            rendimento_liquido=calc["rendimento_liquido"],
            ir_aliquota=calc["ir_aliquota_pct"],
            ir_valor=calc["ir_valor"],
            iof_valor=calc["iof_valor"],
            data_resgate_programado=data_resgate,
            motivo_resgate_programado=motivo_resgate,
            expira_em_epoch=time.time() + p.validade_cotacao_segundos,
        )
