"""Mock do core bancário: fonte única de dados para as tools do ADK e para o
servidor MCP. Idempotente, com trilha de auditoria em JSONL.

Substitua por adapters reais (core, fatura, crédito) mantendo a mesma
interface. É isso que o desenho de solução deve mostrar como "integração viável".
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DATA_PATH = RAIZ / "data" / "clientes.json"
AUDIT_PATH = Path(__file__).resolve().parent / "audit.jsonl"
# registro de consentimentos e oposições: persistido para valer também na rotina proativa
CONSENT_PATH = Path(__file__).resolve().parent / "consentimentos.json"
# lembretes do mês seguinte: persistidos para a rotina proativa usar a janela de cada cliente
LEMBRETES_PATH = Path(__file__).resolve().parent / "lembretes.json"
STATUS_EM_ABERTO = {"aberta", "paga_parcialmente"}
FINALIDADES = {
    "acessibilidade": "usar a necessidade de acessibilidade para adaptar as respostas",
    "avisos_proativos": "receber avisos antes do vencimento da fatura",
}

_lock = threading.RLock()  # reentrante: executar_autorizada audita dentro da seção travada


class ClienteNaoEncontrado(KeyError):
    pass


class Store:
    def __init__(self, data_path: Path = DATA_PATH, audit_path: Path = AUDIT_PATH,
                 consent_path: Path = CONSENT_PATH, lembretes_path: Path = LEMBRETES_PATH):
        self.data_path = data_path
        self.audit_path = audit_path
        self.consent_path = consent_path
        self._consentimentos: dict[str, dict] | None = None
        self.lembretes_path = lembretes_path
        self._lembretes: dict[str, int] | None = None
        self._operacoes: dict[str, list[dict]] = {}
        self._clientes: dict[str, dict] | None = None
        self._meta: dict = {}
        self._idempotencia: dict[str, dict] = {}
        self._contratos: list[dict] = []
        self._capacidades_usadas: dict[str, dict] = {}

    # ---------- carga ----------
    def _carregar(self) -> None:
        if self._clientes is not None:
            return
        if not self.data_path.exists():
            if self.data_path != DATA_PATH:
                raise FileNotFoundError(f"{self.data_path} não existe")
            # o dataset não vai para o git (880 KB): é gerado, determinístico, na primeira carga
            from data.gerar_dataset import main as gerar_dataset

            gerar_dataset()
        raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        self._meta = raw.get("meta", {})
        self._clientes = {}
        for c in raw["clientes"]:
            self._clientes[c["cliente_id"]] = c
            if "alias_id" in c:
                self._clientes[c["alias_id"]] = c
            if "uuid" in c:
                self._clientes[c["uuid"]] = c

    def reset(self) -> None:
        self._clientes = None
        self._idempotencia.clear()
        self._contratos.clear()
        self._capacidades_usadas.clear()
        self._consentimentos = None
        self._lembretes = None
        self._operacoes.clear()

    def _cliente(self, cliente_id: str) -> dict:
        self._carregar()
        assert self._clientes is not None
        if cliente_id in self._clientes:
            return self._clientes[cliente_id]
        cid_lower = cliente_id.lower()
        for k, v in self._clientes.items():
            if k.lower() == cid_lower:
                return v
        raise ClienteNaoEncontrado(cliente_id)

    # ---------- leitura ----------
    def listar_ids(self) -> list[str]:
        self._carregar()
        assert self._clientes is not None
        return sorted(self._clientes)

    def hoje(self) -> str:
        self._carregar()
        return self._meta.get("hoje", "2026-09-21")

    def get_perfil(self, cliente_id: str) -> dict:
        """Perfil com minimização de dados: nada de CPF, endereço ou telefone."""
        c = self._cliente(cliente_id)
        return {
            "cliente_id": c["cliente_id"],
            "primeiro_nome": c["nome"].split()[0],
            "idade": c["idade"],
            "renda_mensal": c["renda_mensal"],
            "saldo_conta": c["saldo_conta"],
            "score": c["score"],
            "negativado": c["negativado"],
            "letramento_financeiro": c["letramento_financeiro"],
            "acessibilidade": c.get("acessibilidade"),
            "canal_preferido": c["canal_preferido"],
            "historico_rotativo_12m": c["historico_rotativo_12m"],
            "objetivo_declarado": c.get("objetivo_declarado"),
        }

    def get_fatura(self, cliente_id: str) -> dict:
        c = self._cliente(cliente_id)
        f = c["fatura"]
        return {
            "cliente_id": cliente_id,
            "valor_total": f["valor_total"],
            "valor_minimo": round(f["valor_total"] * 0.15, 2),
            "valor_em_aberto": round(f["valor_total"] - f.get("pago", 0.0), 2),
            "dias_ate_vencimento": f["dias_ate_vencimento"],
            "limite_total": c["limite_total"],
            "limite_disponivel": round(c["limite_total"] - f["valor_total"], 2),
            "itens": f["itens"],
            "status": f.get("status", "aberta"),
        }

    def vencimento(self, cliente_id: str) -> str:
        """Data de vencimento da fatura atual (identifica o ciclo)."""
        dias = self._cliente(cliente_id)["fatura"]["dias_ate_vencimento"]
        return (date.fromisoformat(self.hoje()) + timedelta(days=dias)).isoformat()

    def chave_idempotencia(self, acao: str, cliente_id: str, *extras: object) -> str:
        """Chave de negócio (ação + cliente + ciclo da fatura + parâmetros).

        Não depende do id da chamada do LLM: se o modelo repetir a mesma ação,
        a chave é a mesma e o core devolve o resultado anterior (replay).
        """
        return ":".join([acao, cliente_id, self.vencimento(cliente_id), *map(str, extras)])

    def em_aberto(self, cliente_id: str) -> float:
        f = self._cliente(cliente_id)["fatura"]
        return round(f["valor_total"] - f.get("pago", 0.0), 2)

    def operacoes(self, cliente_id: str) -> list[dict]:
        """Pagamentos e parcelamentos efetivados neste ciclo (para o acompanhamento do cliente)."""
        return list(self._operacoes.get(cliente_id, []))

    def cotar_parcelamento(self, cliente_id: str, n_parcelas: int) -> dict:
        """Valores do parcelamento, pela mesma conta do simulador (sem efetivar)."""
        if not 2 <= n_parcelas <= 24:
            raise ValueError("n_parcelas deve estar entre 2 e 24")
        from copiloto_fatura.tools.simulador import PARAMS, iof, parcela_price

        valor = self.em_aberto(cliente_id)  # depois de um pagamento parcial, parcela só o que falta
        total = parcela_price(valor, n_parcelas, PARAMS.taxa_parcelamento_am) * n_parcelas + iof(valor, n_parcelas * 30)
        return {
            "valor_original": valor,
            "n_parcelas": n_parcelas,
            "parcela": round(total / n_parcelas, 2),
            "custo_total": round(total, 2),
        }

    def get_extrato(self, cliente_id: str, dias: int = 30) -> list[dict]:
        c = self._cliente(cliente_id)
        return [t for t in c["transacoes_30d"] if t["dias_atras"] <= dias]

    def get_fluxo_previsto(self, cliente_id: str) -> dict:
        c = self._cliente(cliente_id)
        return {
            "saldo_atual": c["saldo_conta"],
            "entradas": c["entradas_previstas"],
            "saidas": c["saidas_previstas"],
        }

    # ---------- escrita (idempotente + auditada) ----------
    # ---------- consentimentos (LGPD) ----------
    def _carregar_consentimentos(self) -> dict[str, dict]:
        if self._consentimentos is None:
            try:
                self._consentimentos = json.loads(self.consent_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._consentimentos = {}
        return self._consentimentos

    def consentimentos(self, cliente_id: str) -> dict:
        return dict(self._carregar_consentimentos().get(cliente_id, {}))

    def registrar_consentimento(self, cliente_id: str, finalidade: str, aceito: bool) -> dict:
        """Registra aceite ou recusa por finalidade (com data), persiste e audita.

        O registro fica mesmo se o cliente pedir para apagar as preferências:
        é a comprovação de que a escolha dele foi respeitada.
        """
        if finalidade not in FINALIDADES:
            raise ValueError(f"finalidade desconhecida: {finalidade}")
        self._cliente(cliente_id)
        with _lock:
            todos = self._carregar_consentimentos()
            registro = {"aceito": bool(aceito), "em": datetime.now(timezone.utc).isoformat()}
            todos.setdefault(cliente_id, {})[finalidade] = registro
            self.consent_path.parent.mkdir(parents=True, exist_ok=True)
            self.consent_path.write_text(json.dumps(todos, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
            self._audit({"acao": "consentimento", "cliente_id": cliente_id, "finalidade": finalidade, "aceito": bool(aceito)})
        return registro

    def consentiu(self, cliente_id: str, finalidade: str) -> bool:
        """Acessibilidade: só com aceite explícito. Avisos: sim, salvo oposição registrada."""
        registro = self.consentimentos(cliente_id).get(finalidade)
        if registro is None:
            return finalidade == "avisos_proativos"
        return registro["aceito"]

    # ---------- lembrete do mês seguinte ----------
    def lembrete(self, cliente_id: str) -> int | None:
        if self._lembretes is None:
            try:
                self._lembretes = json.loads(self.lembretes_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._lembretes = {}
        return self._lembretes.get(cliente_id)

    def registrar_lembrete(self, cliente_id: str, dias_antes: int) -> dict:
        if not 1 <= int(dias_antes) <= 10:
            raise ValueError("o lembrete deve ser de 1 a 10 dias antes do vencimento")
        self._cliente(cliente_id)
        with _lock:
            self.lembrete(cliente_id)
            assert self._lembretes is not None
            self._lembretes[cliente_id] = int(dias_antes)
            self.lembretes_path.parent.mkdir(parents=True, exist_ok=True)
            self.lembretes_path.write_text(json.dumps(self._lembretes, indent=1), encoding="utf-8", newline="\n")
            self._audit({"acao": "lembrete", "cliente_id": cliente_id, "dias_antes": int(dias_antes)})
        return {"dias_antes": int(dias_antes)}

    def _audit(self, evento: dict) -> None:
        evento = {"ts": datetime.now(timezone.utc).isoformat(), **evento}
        with _lock:
            with self.audit_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(evento, ensure_ascii=False) + "\n")

    def executar_autorizada(self, acao: str, cliente_id: str, args: dict, autorizacao: str | None,
                            canal: str = "agente") -> dict:
        """Porta de entrada das ações: só executa com capacidade válida do host.

        Confere a assinatura e os parâmetros, recalcula a cotação (se os valores
        mudaram desde a aprovação, recusa) e trata a capacidade como uso único:
        repetida, devolve o recibo original.
        """
        from copiloto_fatura.autorizacao import cotar, parametros, verificar

        with _lock:
            dados = verificar(autorizacao, acao, cliente_id, args)
            nonce = dados["nonce"]
            if nonce in self._capacidades_usadas:
                return {**self._capacidades_usadas[nonce], "replay": True}
            if cotar(self, acao, cliente_id, args) != dados["cotacao"]:
                raise ValueError("os valores mudaram desde a aprovação: peça nova cotação ao cliente")
            p = parametros(acao, args)
            if acao == "parcelar_fatura":
                chave = self.chave_idempotencia("parcelar", cliente_id, p["n_parcelas"])
                r = self.parcelar_fatura(cliente_id, p["n_parcelas"], chave, canal)
            elif acao == "pagar_fatura":
                chave = self.chave_idempotencia("pagar", cliente_id, p["valor"])
                r = self.pagar_fatura(cliente_id, p["valor"], chave, canal)
            elif acao == "aplicar_cdb":
                chave = self.chave_idempotencia("aplicar_cdb", cliente_id, p["valor"])
                r = self.aplicar_cdb(cliente_id, p["valor"], chave, p.get("dias_permanencia", 30), canal)
            elif acao == "resgatar_cdb":
                chave = self.chave_idempotencia("resgatar_cdb", cliente_id, p["valor"])
                r = self.resgatar_cdb(cliente_id, p["valor"], chave, canal)
            else:
                raise ValueError(f"ação desconhecida: {acao}")
            self._capacidades_usadas[nonce] = r
            return r

    def parcelar_fatura(
        self, cliente_id: str, n_parcelas: int, idempotency_key: str, canal: str = "agente"
    ) -> dict:
        if idempotency_key in self._idempotencia:
            return {**self._idempotencia[idempotency_key], "replay": True}
        c = self._cliente(cliente_id)
        cotacao = self.cotar_parcelamento(cliente_id, n_parcelas)
        if c["fatura"].get("status", "aberta") not in STATUS_EM_ABERTO:
            return {"status": "recusado", "motivo": f"fatura já está {c['fatura']['status']}"}
        contrato = {
            "status": "efetivado",
            "contrato_id": f"PARC-{cliente_id}-{len(self._contratos) + 1:04d}",
            "cliente_id": cliente_id,
            **cotacao,
            "canal": canal,
            "replay": False,
        }
        c["fatura"]["status"] = "parcelada"
        self._contratos.append(contrato)
        self._operacoes.setdefault(cliente_id, []).append({"tipo": "parcelamento", **contrato})
        self._idempotencia[idempotency_key] = contrato
        self._audit({"acao": "parcelar_fatura", "idempotency_key": idempotency_key, **contrato})
        return contrato

    def pagar_fatura(
        self, cliente_id: str, valor: float, idempotency_key: str, canal: str = "agente"
    ) -> dict:
        if idempotency_key in self._idempotencia:
            return {**self._idempotencia[idempotency_key], "replay": True}
        c = self._cliente(cliente_id)
        if valor <= 0:
            raise ValueError("valor deve ser positivo")
        if valor > c["saldo_conta"]:
            return {"status": "recusado", "motivo": "saldo insuficiente", "saldo": c["saldo_conta"]}
        c["saldo_conta"] = round(c["saldo_conta"] - valor, 2)
        restante = round(self.em_aberto(cliente_id) - valor, 2)
        c["fatura"]["pago"] = round(c["fatura"].get("pago", 0.0) + valor, 2)
        c["fatura"]["status"] = "paga" if restante <= 0 else "paga_parcialmente"
        recibo = {
            "status": "efetivado",
            "comprovante_id": f"PAG-{cliente_id}-{len(self._idempotencia) + 1:04d}",
            "cliente_id": cliente_id,
            "valor_pago": round(valor, 2),
            "restante_fatura": max(restante, 0.0),
            "novo_saldo": c["saldo_conta"],
            "canal": canal,
            "replay": False,
        }
        self._idempotencia[idempotency_key] = recibo
        self._operacoes.setdefault(cliente_id, []).append({"tipo": "pagamento", **recibo})
        self._audit({"acao": "pagar_fatura", "idempotency_key": idempotency_key, **recibo})
        return recibo

    def get_investimentos(self, cliente_id: str) -> dict:
        c = self._cliente(cliente_id)
        return c.get("custodia_investimentos", {"cdb_liquidez_diaria": 0.0, "posicoes": []})

    def aplicar_cdb(
        self, cliente_id: str, valor: float, idempotency_key: str, dias_permanencia: int = 30, canal: str = "agente"
    ) -> dict:
        if idempotency_key in self._idempotencia:
            return {**self._idempotencia[idempotency_key], "replay": True}
        c = self._cliente(cliente_id)
        if valor <= 0:
            raise ValueError("valor deve ser positivo")
        if valor > c["saldo_conta"]:
            return {"status": "recusado", "motivo": "saldo insuficiente", "saldo": c["saldo_conta"]}
        c["saldo_conta"] = round(c["saldo_conta"] - valor, 2)
        custodia = c.setdefault("custodia_investimentos", {"cdb_liquidez_diaria": 0.0, "posicoes": []})
        custodia["cdb_liquidez_diaria"] = round(custodia["cdb_liquidez_diaria"] + valor, 2)
        from gestor_caixa.simulador_liquidez import SimuladorLiquidez
        sim = SimuladorLiquidez.simular_rendimento(valor, dias_permanencia)
        posicao = {
            "id": f"POS-{len(custodia['posicoes']) + 1:04d}",
            "valor_aplicado": round(valor, 2),
            "dias_permanencia": dias_permanencia,
            "rendimento_estimado": sim["rendimento_liquido"],
            "data_aplicacao": self.hoje(),
        }
        custodia["posicoes"].append(posicao)
        recibo = {
            "status": "efetivado",
            "comprovante_id": f"APL-{cliente_id}-{len(self._idempotencia) + 1:04d}",
            "cliente_id": cliente_id,
            "valor_aplicado": round(valor, 2),
            "produto": "CDB Itaú Liquidez Diária (100% CDI)",
            "rendimento_estimado_liquido": sim["rendimento_liquido"],
            "novo_saldo_conta": c["saldo_conta"],
            "saldo_total_investido": custodia["cdb_liquidez_diaria"],
            "canal": canal,
            "replay": False,
        }
        self._idempotencia[idempotency_key] = recibo
        self._operacoes.setdefault(cliente_id, []).append({"tipo": "investimento", **recibo})
        self._audit({"acao": "aplicar_cdb", "idempotency_key": idempotency_key, **recibo})
        return recibo

    def resgatar_cdb(
        self, cliente_id: str, valor: float, idempotency_key: str, canal: str = "agente"
    ) -> dict:
        if idempotency_key in self._idempotencia:
            return {**self._idempotencia[idempotency_key], "replay": True}
        c = self._cliente(cliente_id)
        if valor <= 0:
            raise ValueError("valor deve ser positivo")
        custodia = c.setdefault("custodia_investimentos", {"cdb_liquidez_diaria": 0.0, "posicoes": []})
        if valor > custodia["cdb_liquidez_diaria"]:
            return {"status": "recusado", "motivo": "saldo investido insuficiente", "investido": custodia["cdb_liquidez_diaria"]}
        custodia["cdb_liquidez_diaria"] = round(custodia["cdb_liquidez_diaria"] - valor, 2)
        c["saldo_conta"] = round(c["saldo_conta"] + valor, 2)
        recibo = {
            "status": "efetivado",
            "comprovante_id": f"RESG-{cliente_id}-{len(self._idempotencia) + 1:04d}",
            "cliente_id": cliente_id,
            "valor_resgatado": round(valor, 2),
            "novo_saldo_conta": c["saldo_conta"],
            "saldo_total_investido": custodia["cdb_liquidez_diaria"],
            "canal": canal,
            "replay": False,
        }
        self._idempotencia[idempotency_key] = recibo
        self._operacoes.setdefault(cliente_id, []).append({"tipo": "resgate", **recibo})
        self._audit({"acao": "resgatar_cdb", "idempotency_key": idempotency_key, **recibo})
        return recibo


STORE = Store()

