"""Modelo de demonstração: plano B da demo, sem internet e sem cota (``COPILOTO_MODEL=demo``).

Faz o papel do Gemini com regras fixas: entende as frases da demo, chama as mesmas
ferramentas que o modelo real chamaria e escreve as respostas com os números que
as ferramentas devolveram. Guardrails, aprovação, core e auditoria rodam de verdade;
só a "inteligência" é trocada por um roteiro. Não é um agente de produção: frases
fora do roteiro recebem uma resposta genérica.

Frases que ele entende (sem acento também):
- "sou a cliente C001", qualquer pergunta sobre a fatura -> diagnóstico e opções
- "quero parcelar em 6x", "quero a recomendada", "pagar o total" -> ação com aprovação
- "me avisa 5 dias antes" -> lembrete; "como estou indo?" -> progresso
- "agiota", "desesperada", "não tenho dinheiro" -> acolhimento e apoio humano
- "o que vocês guardam sobre mim", "apagar", "não quero mais avisos" -> direitos do titular
- "pode adaptar", "uma informação por linha", "áudio" -> consentimento de acessibilidade
"""

from __future__ import annotations

import re
import unicodedata
from types import SimpleNamespace
from typing import Any, AsyncGenerator

from google.adk.models import LlmRequest, LlmResponse
from google.adk.models.base_llm import BaseLlm
from google.genai import types

from copiloto_fatura.autorizacao import brl

PREFIXO_CONTEXTO = "For context:"
AGENTE_ACAO = "agente_acao"
AGENTE_RAIZ = "copiloto_fatura"


def _sem_acento(texto: str) -> str:
    # não usa guardrails.normalizar: ele troca dígitos por letras (leetspeak) e quebraria "C001" e "6x"
    texto = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(ch for ch in texto if not unicodedata.combining(ch))


def _chamada(nome: str, **args: Any) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=nome, args=args))]))


def _texto(t: str) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=t)]))


class _Conversa:
    """O que o modelo "enxerga" no pedido: última fala do cliente e o que aconteceu desde então."""

    def __init__(self, req: LlmRequest):
        contents = req.contents or []
        self.idx = max((i for i, c in enumerate(contents) if self._fala_do_cliente(c)), default=-1)
        self.fala = " ".join(p.text for p in contents[self.idx].parts if p.text) if self.idx >= 0 else ""
        self.u = _sem_acento(self.fala)
        depois = contents[self.idx + 1:]
        self.respostas: dict[str, dict] = {}
        for c in depois:
            for p in c.parts or []:
                if p.function_response and p.function_response.name != "adk_request_confirmation":
                    self.respostas[p.function_response.name] = p.function_response.response or {}
        self.contexto = " ".join(p.text for c in depois for p in c.parts or [] if p.text)
        self.chamadas = {p.function_call.name for c in contents for p in c.parts or [] if p.function_call}
        self.inicio = next((p.function_response.response for c in contents for p in c.parts or []
                            if p.function_response and p.function_response.name == "iniciar_atendimento"), {}) or {}
        instr = req.config.system_instruction if req.config else ""
        instr = instr if isinstance(instr, str) else " ".join(p.text or "" for p in getattr(instr, "parts", []) or [])
        m = re.search(r"Cliente da sessão: (C\d{3})", instr)
        mencionados = re.findall(r"\bc\d{3}\b", self.u)
        self.cid = m.group(1) if m else (mencionados[0].upper() if mencionados else None)
        self.outros = sorted({x.upper() for x in mencionados} - {self.cid})
        self.acao = "parcelar_fatura" in req.tools_dict

    @staticmethod
    def _fala_do_cliente(c: types.Content) -> bool:
        textos = [p.text for p in c.parts or [] if p.text]
        return c.role == "user" and bool(textos) and not textos[0].startswith(PREFIXO_CONTEXTO)

    def tem(self, padrao: str) -> bool:
        return re.search(padrao, self.u) is not None

    def escolheu(self) -> bool:
        """Escolha afirmativa de uma opção ("quero parcelar em 6x"), não "não vou conseguir pagar tudo"."""
        if self.tem(r"nao (vou|consigo|da|tenho)"):
            return False
        return self.tem(r"\d{1,2} ?x|recomendad|primeira opcao|quero essa") or self.tem(
            r"(quero|prefiro|escolho|pode|vamos|faz|faca|bora)\b.*\b(parcel|pag)")

    def nome(self) -> str:
        if self.inicio.get("primeiro_nome"):
            return self.inicio["primeiro_nome"]
        from mock_core.store import STORE  # o agente de ação não recebe o perfil nas mensagens

        return STORE.get_perfil(self.cid)["primeiro_nome"] if self.cid else ""


def _diagnostico(cid: str) -> dict:
    from copiloto_fatura.tools.contexto import analisar_fatura

    return analisar_fatura(SimpleNamespace(state={"cliente_id": cid}))


def _descreve(o: dict) -> str:
    if o["id"] == "pagar_total":
        return f"pagar a fatura inteira, {brl(o['custo_total'])}, sem juros"
    if o["id"] == "parcial_mais_parcelamento":
        return (f"pagar {brl(o['pagar_agora'])} agora e parcelar o resto em {o['n_parcelas']}x de "
                f"{brl(o['parcela'])} (custo total {brl(o['custo_total'])})")
    if o["id"] == "credito_pessoal_12x":
        return (f"crédito pessoal em 12x de {brl(o['parcela'])} (custo total {brl(o['custo_total'])}); "
                "é uma dívida nova e depende de análise de crédito")
    return f"parcelar em {o['n_parcelas']}x de {brl(o['parcela'])} (custo total {brl(o['custo_total'])})"


def _texto_opcoes(nome: str, r: dict, oferecer_adaptacao: bool) -> str:
    f, cx = r["fatura"], r["caixa"]
    linhas = [f"Oi{', ' + nome if nome else ''}. Sua fatura é de {brl(f['total'])} e vence em {f['vence_em_dias']} dias. "
              f"No vencimento você terá {brl(cx['saldo_no_vencimento'])} em conta"
              + (f", então faltam {brl(cx['falta_para_o_total'])}." if cx["falta_para_o_total"] else ".")]
    rec, *outras = r["opcoes_para_apresentar"]
    linhas.append(f"\nMinha recomendação: **{_descreve(rec)}**. {r['motivo_recomendacao']}"
                  + (f" Você economiza {brl(rec['economia_vs_rotativo'])} frente a pagar só o mínimo e cair no rotativo."
                     if rec["economia_vs_rotativo"] > 0 else ""))
    if outras:
        linhas.append("\nOutras opções:\n" + "\n".join(f"- {_descreve(o)}" for o in outras))
    rot = r["se_nao_fizer_nada"]
    linhas.append(f"\nSe pagar só o mínimo ({brl(rot['pagar_agora'])}), o resto vai para o rotativo, o crédito mais caro: "
                  f"custo total de {brl(rot['custo_total'])}.")
    linhas.append('\nQual você prefere? Por exemplo: "quero a recomendada" ou "quero parcelar em 6x".')
    if oferecer_adaptacao:
        linhas.append("\n_Se preferir, posso adaptar o jeito de responder: uma informação por linha ou resumo em áudio._")
    return "\n".join(linhas)


def _raiz(c: _Conversa) -> LlmResponse:
    if not c.cid:
        return _texto("Oi! Eu sou o Copiloto da Fatura. Para começar, me diga seu código de cliente (por exemplo, C001).")
    if "iniciar_atendimento" not in c.chamadas:
        return _chamada("iniciar_atendimento", cliente_id=c.cid)
    nome, rs = c.nome(), c.respostas

    if c.outros:
        return _texto(f"{nome}, só posso mostrar dados do titular desta conversa. Os dados de {', '.join(c.outros)} "
                      "só podem ser vistos pela própria pessoa, no atendimento dela. Posso seguir com a sua fatura?")

    if c.tem(r"agiota|desesper|nao tenho (dinheiro|nada)|nao consigo pagar nada"):
        if "analisar_fatura" not in rs:
            return _chamada("analisar_fatura")
        if "encaminhar_para_humano" not in rs:
            return _chamada("encaminhar_para_humano", motivo="sofrimento_financeiro")
        r = rs["analisar_fatura"]
        menor = r["opcoes_para_apresentar"][0]
        return _texto(
            f"{nome}, sinto muito que você esteja passando por isso. Não recorra a agiota: costuma sair muito mais caro "
            f"do que qualquer opção do banco.\n\nSua fatura é de {brl(r['fatura']['total'])} e vence em "
            f"{r['fatura']['vence_em_dias']} dias. O saldo previsto ({brl(r['caixa']['saldo_no_vencimento'])}) não cobre "
            f"nem o mínimo. A menor parcela possível seria {_descreve(menor)}, mas o melhor caminho é renegociar.\n\n"
            "Registrei um pedido de apoio de um especialista em renegociação. Neste protótipo, esse encaminhamento é "
            "simulado: para atendimento real agora, procure os canais oficiais do Itaú. Nenhuma cobrança foi feita.")

    passos = []
    if c.tem(r"nao quero (mais )?(receber|aviso)|\bparar\b"):
        passos.append(("registrar_consentimento", {"finalidade": "avisos_proativos", "aceito": False}))
    if c.tem(r"apag"):
        passos.append(("apagar_meus_dados", {}))
    if c.tem(r"guarda|meus dados|sabem sobre mim|sabe sobre mim"):
        passos.append(("meus_dados", {}))
    if passos:
        for nome_tool, args in passos:
            if nome_tool not in rs:
                return _chamada(nome_tool, **args)
        partes = []
        if "registrar_consentimento" in rs:
            partes.append("Pronto: registrei que você não quer mais receber os avisos antes do vencimento.")
        if "apagar_meus_dados" in rs:
            partes.append("Apaguei as preferências que eu tinha guardado. O registro das suas escolhas de consentimento fica "
                          "como comprovação.")
        if "meus_dados" in rs:
            d = rs["meus_dados"]
            partes.append("Nesta conversa eu uso: " + ", ".join(d["dados_usados_na_conversa"]) + ". Não uso: "
                          + ", ".join(d["dados_que_nao_usamos"]) + ".")
        juntas = " ".join(partes)
        return _texto(f"{nome}, {juntas[0].lower()}{juntas[1:]}")

    if c.tem(r"lembr|avis[ae]") and not c.tem(r"nao quero"):
        if "agendar_lembrete" not in rs:
            n = re.search(r"(\d{1,2}) dias?", c.u)
            return _chamada("agendar_lembrete", dias_antes=int(n.group(1)) if n else 5)
        r = rs["agendar_lembrete"]
        if r.get("status") != "ok":
            return _texto(f"Não consegui agendar: {r.get('motivo')}.")
        return _texto(f"Combinado, {nome}! Vou te avisar em {r['aviso_em']}, antes do vencimento da próxima fatura "
                      f"({r['proximo_vencimento']}), com as opções já calculadas.")

    if c.tem(r"adapt|uma (informacao|coisa) por linha|audio"):
        if "registrar_consentimento" not in rs:
            return _chamada("registrar_consentimento", finalidade="acessibilidade", aceito=True)
        return _texto("Combinado. A partir de agora respondo com uma informação por linha e posso mandar um resumo em áudio.")

    if c.escolheu():
        return _chamada("transfer_to_agent", agent_name=AGENTE_ACAO)

    if c.tem(r"como (estou|esta|to)|progresso|economizei"):
        if "acompanhar_progresso" not in rs:
            return _chamada("acompanhar_progresso")
        return _texto(_texto_progresso(nome, rs["acompanhar_progresso"]))

    if "analisar_fatura" not in rs:
        return _chamada("analisar_fatura")
    return _texto(_texto_opcoes(nome, rs["analisar_fatura"], bool(c.inicio.get("oferecer_adaptacao"))))


def _texto_progresso(nome: str, p: dict) -> str:
    t = f"{nome}, resumo do mês: você {p['decisao']}."
    if p.get("economia_vs_rotativo"):
        t += f" Isso custa {brl(p['economia_vs_rotativo'])} a menos do que pagar só o mínimo e cair no rotativo."
    if p.get("compromisso_mensal"):
        t += f" O compromisso é de {brl(p['compromisso_mensal'])} por mês, durante {p['meses']} meses."
    if p.get("objetivo_declarado"):
        t += f" É um passo concreto para a sua meta: {p['objetivo_declarado']}."
    if p.get("proximo_aviso"):
        t += f" Próximo aviso: {p['proximo_aviso']}."
    elif p.get("oferecer_lembrete"):
        t += " Quer que eu te avise antes da próxima fatura? Diga quantos dias antes, de 1 a 10."
    return t


N_PARCELAS_PARCIAL = 6  # o mesmo da opção "pagar parte e parcelar o resto" no simulador


def _passos_da_acao(c: _Conversa) -> list[tuple[str, dict]]:
    pagou = c.respostas.get("pagar_fatura", {}).get("status") == "efetivado"
    if pagou and c.tem(r"recomendad|primeira|quero essa|pagar .* agora"):
        # depois do pagamento parcial o diagnóstico muda; o plano escolhido continua o mesmo
        return [("pagar_fatura", {}), ("parcelar_fatura", {"n_parcelas": N_PARCELAS_PARCIAL})]
    r = _diagnostico(c.cid)
    em_aberto = r["fatura"]["total"]
    if c.tem(r"pagar (o )?total|pagar tudo|inteira"):
        return [("pagar_fatura", {"valor": em_aberto})]
    n = re.search(r"(\d{1,2}) ?x", c.u)
    if n:
        return [("parcelar_fatura", {"n_parcelas": int(n.group(1))})]
    if c.tem(r"recomendad|primeira|quero essa|pagar .* agora"):
        rec = r["opcoes_para_apresentar"][0]
        if rec["id"] == "parcial_mais_parcelamento":
            return [("pagar_fatura", {"valor": rec["pagar_agora"]}), ("parcelar_fatura", {"n_parcelas": rec["n_parcelas"]})]
        if rec["id"] == "pagar_total":
            return [("pagar_fatura", {"valor": em_aberto})]
        return [("parcelar_fatura", {"n_parcelas": rec["n_parcelas"]})]
    return []


def _acao(c: _Conversa) -> LlmResponse:
    passos = _passos_da_acao(c) if c.cid and c.escolheu() else []
    if not passos:
        return _chamada("transfer_to_agent", agent_name=AGENTE_RAIZ)
    rs = c.respostas
    for nome_tool, args in passos:
        if nome_tool not in rs:
            return _chamada(nome_tool, **args)
        status = rs[nome_tool].get("status")
        if status == "cancelado":
            return _texto("Tudo bem, você não aprovou e nada foi feito. Quer ver as opções de novo?")
        if status != "efetivado":
            return _texto(f"Não foi possível concluir: {rs[nome_tool].get('motivo', 'erro no processamento')}. Nada foi cobrado.")
    if "acompanhar_progresso" not in rs:
        return _chamada("acompanhar_progresso")
    feitos = []
    if "pagar_fatura" in rs:
        feitos.append(f"paguei {brl(rs['pagar_fatura']['valor_pago'])} (comprovante {rs['pagar_fatura']['comprovante_id']})")
    if "parcelar_fatura" in rs:
        p = rs["parcelar_fatura"]
        feitos.append(f"parcelei {brl(p['valor_original'])} em {p['n_parcelas']}x de {brl(p['parcela'])} "
                      f"(contrato {p['contrato_id']})")
    return _texto("Pronto: " + " e ".join(feitos) + ".\n\n" + _texto_progresso(c.nome(), rs["acompanhar_progresso"]))


class DemoLlm(BaseLlm):
    """Modelo roteirizado da demonstração. Ver o docstring do módulo."""

    model: str = "demo"

    @classmethod
    def supported_models(cls) -> list[str]:
        return [r"demo"]

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        c = _Conversa(llm_request)
        yield _acao(c) if c.acao else _raiz(c)
