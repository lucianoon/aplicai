"""Gera ``data/clientes.json``: 200 clientes sintéticos + 3 personas de demo.

Determinístico (seed 42). Distribuições calibradas de forma grosseira em
dados públicos; troque pelos números do case quando o Itaú liberar.

Referências usadas para calibrar (documente no entregável de dados):
- Serasa: 83,3 mi de negativados (case da Batalha).
- Pesquisas de educação financeira: 55% com baixa familiaridade.
- Renda mediana do trabalho no Brasil na casa de R$ 2,5 mil a R$ 3 mil.

Uso: uv run python -m data.gerar_dataset
"""

from __future__ import annotations

import json
import random
from pathlib import Path

HOJE = "2026-09-21"
SAIDA = Path(__file__).resolve().parent / "clientes.json"

NOMES = [
    "Ana", "Bruno", "Carla", "Diego", "Elaine", "Fábio", "Gabriela", "Henrique", "Isabela",
    "João", "Karina", "Lucas", "Mariana", "Nelson", "Olívia", "Paulo", "Quitéria", "Rafael",
    "Sônia", "Tiago", "Úrsula", "Vinícius", "Wagner", "Ximena", "Yara", "Zeca",
]
SOBRENOMES = ["Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Costa", "Ferreira"]
CATEGORIAS = [
    ("supermercado", 0.28), ("transporte", 0.12), ("delivery", 0.12), ("farmácia", 0.08),
    ("streaming", 0.05), ("roupas", 0.10), ("combustível", 0.10), ("lazer", 0.08), ("outros", 0.07),
]


def _renda(rng: random.Random) -> float:
    return round(min(max(rng.lognormvariate(7.95, 0.55), 1412.0), 25000.0), 2)


def _itens_fatura(rng: random.Random, total: float) -> list[dict]:
    itens = []
    restante = total
    for cat, peso in CATEGORIAS[:-1]:
        v = round(total * peso * rng.uniform(0.6, 1.4), 2)
        v = min(v, restante)
        if v > 0:
            itens.append({"categoria": cat, "valor": v})
            restante = round(restante - v, 2)
    if restante > 0:
        itens.append({"categoria": "outros", "valor": restante})
    return itens


def _transacoes(rng: random.Random, renda: float) -> list[dict]:
    out = []
    for _ in range(rng.randint(12, 40)):
        cat = rng.choices([c for c, _ in CATEGORIAS], [p for _, p in CATEGORIAS])[0]
        out.append(
            {
                "dias_atras": rng.randint(0, 30),
                "categoria": cat,
                "valor": round(rng.uniform(8, renda * 0.08), 2),
                "meio": rng.choice(["cartao", "pix", "debito"]),
            }
        )
    return sorted(out, key=lambda t: t["dias_atras"])


def gerar_cliente(rng: random.Random, i: int) -> dict:
    renda = _renda(rng)
    letramento = rng.choices(["baixo", "medio", "alto"], [0.55, 0.30, 0.15])[0]
    negativado = rng.random() < 0.45
    fatura = round(renda * rng.uniform(0.15, 0.95), 2)
    dias_venc = rng.randint(1, 28)
    saldo = round(renda * rng.uniform(-0.05, 0.6), 2)
    dia_salario = rng.randint(1, 10)
    return {
        "cliente_id": f"C{i:03d}",
        "nome": f"{rng.choice(NOMES)} {rng.choice(SOBRENOMES)}",
        "idade": rng.randint(19, 72),
        "renda_mensal": renda,
        "saldo_conta": saldo,
        "score": rng.randint(250, 950),
        "negativado": negativado,
        "letramento_financeiro": letramento,
        "acessibilidade": rng.choice([None, None, None, None, "baixa_visao", "leitor_de_tela", "baixa_alfabetizacao"]),
        "canal_preferido": rng.choice(["app", "whatsapp", "app", "voz"]),
        "historico_rotativo_12m": rng.choices([0, 1, 2, 3, 5], [0.45, 0.2, 0.15, 0.1, 0.1])[0],
        "objetivo_declarado": rng.choice([None, "sair do vermelho", "reserva de emergência", "trocar de carro", "viajar"]),
        "limite_total": round(max(fatura * rng.uniform(1.1, 2.5), 500), 2),
        "fatura": {"valor_total": fatura, "dias_ate_vencimento": dias_venc, "itens": _itens_fatura(rng, fatura), "status": "aberta"},
        "entradas_previstas": [
            {"dia_offset": dia_salario, "valor": round(renda * rng.uniform(0.9, 1.0), 2), "descricao": "salário"}
        ],
        "saidas_previstas": [
            {"dia_offset": rng.randint(1, 10), "valor": round(renda * rng.uniform(0.2, 0.35), 2), "descricao": "aluguel"},
            {"dia_offset": rng.randint(5, 15), "valor": round(renda * rng.uniform(0.04, 0.08), 2), "descricao": "energia"},
            {"dia_offset": rng.randint(5, 20), "valor": round(renda * rng.uniform(0.02, 0.05), 2), "descricao": "internet/celular"},
        ],
        "transacoes_30d": _transacoes(rng, renda),
    }


def personas_demo() -> list[dict]:
    """Quatro casos representativos calibrados no BigQuery (extrato_sintetico)."""
    ana = {
        "cliente_id": "C001", "uuid": "3f3f7877-71fd-4073-b0a8-692b105609d8", "alias_id": "3f3f7877-71fd-4073-b0a8-692b105609d8",
        "nome": "Ana Souza", "idade": 34, "renda_mensal": 3200.0,
        "saldo_conta": 610.0, "score": 540, "negativado": False, "letramento_financeiro": "baixo",
        "acessibilidade": None, "canal_preferido": "whatsapp", "historico_rotativo_12m": 2,
        "objetivo_declarado": "sair do vermelho", "limite_total": 4200.0,
        "fatura": {"valor_total": 1850.0, "dias_ate_vencimento": 5, "status": "aberta",
                   "itens": [{"categoria": "supermercado", "valor": 720.0}, {"categoria": "farmácia", "valor": 240.0},
                             {"categoria": "roupas", "valor": 390.0}, {"categoria": "delivery", "valor": 300.0},
                             {"categoria": "transporte", "valor": 200.0}]},
        "entradas_previstas": [{"dia_offset": 9, "valor": 3200.0, "descricao": "salário"}],
        # aluguel e energia vencem depois da fatura: no vencimento ela tem R$ 610 em conta
        "saidas_previstas": [{"dia_offset": 10, "valor": 950.0, "descricao": "aluguel"},
                             {"dia_offset": 12, "valor": 180.0, "descricao": "energia"}],
        "transacoes_30d": [{"dias_atras": 1, "categoria": "delivery", "valor": 62.9, "meio": "cartao"},
                           {"dias_atras": 2, "categoria": "supermercado", "valor": 310.0, "meio": "cartao"},
                           {"dias_atras": 6, "categoria": "roupas", "valor": 390.0, "meio": "cartao"}],
    }
    bruno = {
        "cliente_id": "C002", "uuid": "3df4aa25-75c6-4a76-af42-40f761ada3fe", "alias_id": "3df4aa25-75c6-4a76-af42-40f761ada3fe",
        "nome": "Bruno Lima", "idade": 41, "renda_mensal": 9800.0,
        "saldo_conta": 7400.0, "score": 810, "negativado": False, "letramento_financeiro": "alto",
        "acessibilidade": None, "canal_preferido": "app", "historico_rotativo_12m": 0,
        "objetivo_declarado": "reserva de emergência", "limite_total": 18000.0,
        "fatura": {"valor_total": 3100.0, "dias_ate_vencimento": 5, "status": "aberta",
                   "itens": [{"categoria": "supermercado", "valor": 1200.0}, {"categoria": "combustível", "valor": 600.0},
                             {"categoria": "lazer", "valor": 800.0}, {"categoria": "streaming", "valor": 500.0}]},
        "entradas_previstas": [{"dia_offset": 5, "valor": 9800.0, "descricao": "salário"}],
        "saidas_previstas": [{"dia_offset": 8, "valor": 2600.0, "descricao": "financiamento"}],
        "transacoes_30d": [{"dias_atras": 3, "categoria": "lazer", "valor": 800.0, "meio": "cartao"}],
    }
    carla = {
        "cliente_id": "C003", "uuid": "16c787c7-9510-41fa-a10c-7183c7d12008", "alias_id": "16c787c7-9510-41fa-a10c-7183c7d12008",
        "nome": "Carla Pereira", "idade": 58, "renda_mensal": 2100.0,
        "saldo_conta": -120.0, "score": 380, "negativado": True, "letramento_financeiro": "baixo",
        "acessibilidade": "baixa_visao", "canal_preferido": "voz", "historico_rotativo_12m": 5,
        "objetivo_declarado": "sair do vermelho", "limite_total": 2500.0,
        "fatura": {"valor_total": 2380.0, "dias_ate_vencimento": 2, "status": "aberta",
                   "itens": [{"categoria": "supermercado", "valor": 900.0}, {"categoria": "farmácia", "valor": 680.0},
                             {"categoria": "outros", "valor": 800.0}]},
        "entradas_previstas": [{"dia_offset": 10, "valor": 2100.0, "descricao": "aposentadoria"}],
        "saidas_previstas": [{"dia_offset": 6, "valor": 700.0, "descricao": "aluguel"},
                             {"dia_offset": 7, "valor": 150.0, "descricao": "energia"}],
        "transacoes_30d": [{"dias_atras": 2, "categoria": "farmácia", "valor": 340.0, "meio": "cartao"}],
    }
    diego = {
        "cliente_id": "C004", "uuid": "fe52b305-9f7c-4e06-8bfe-7950f882fdfa", "alias_id": "fe52b305-9f7c-4e06-8bfe-7950f882fdfa",
        "nome": "Diego Takahashi", "idade": 38, "renda_mensal": 13000.0,
        "saldo_conta": 38250.0, "score": 920, "negativado": False, "letramento_financeiro": "alto",
        "acessibilidade": None, "canal_preferido": "app", "historico_rotativo_12m": 0,
        "objetivo_declarado": "reserva de emergência", "limite_total": 35000.0,
        "fatura": {"valor_total": 4250.0, "dias_ate_vencimento": 8, "status": "aberta",
                   "itens": [{"categoria": "supermercado", "valor": 1450.0}, {"categoria": "combustível", "valor": 850.0},
                             {"categoria": "lojas e sites", "valor": 1200.0}, {"categoria": "restaurantes", "valor": 750.0}]},
        "entradas_previstas": [{"dia_offset": 5, "valor": 13000.0, "descricao": "remuneração"}],
        "saidas_previstas": [{"dia_offset": 10, "valor": 3500.0, "descricao": "investimentos"}],
        "transacoes_30d": [{"dias_atras": 1, "categoria": "supermercado", "valor": 380.0, "meio": "cartao"},
                           {"dias_atras": 3, "categoria": "combustível", "valor": 124.0, "meio": "cartao"},
                           {"dias_atras": 5, "categoria": "lojas e sites", "valor": 450.0, "meio": "cartao"}],
    }
    return [ana, bruno, carla, diego]


def main(n: int = 200, seed: int = 42) -> Path:
    rng = random.Random(seed)
    # Consome o passo do RNG do cliente 4 para manter a calibragem exata de C005..C200
    _ = gerar_cliente(rng, 4)
    sinteticos = [gerar_cliente(rng, i) for i in range(5, n + 1)]
    clientes = personas_demo() + sinteticos
    payload = {
        "meta": {
            "hoje": HOJE,
            "gerado_por": "data/gerar_dataset.py",
            "seed": seed,
            "n": len(clientes),
            "fontes_calibracao": [
                "Serasa (83,3 mi negativados) via case da Batalha de Agentes",
                "55% com baixa familiaridade em educação financeira (case)",
                "Renda mediana do trabalho ~R$ 2,5-3 mil (IBGE/PNAD)",
            ],
            "aviso": "Dados 100% fictícios. Nenhum dado pessoal real.",
        },
        "clientes": clientes,
    }
    SAIDA.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return SAIDA


if __name__ == "__main__":
    caminho = main()
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    neg = sum(c["negativado"] for c in dados["clientes"])
    aperto = sum(
        1 for c in dados["clientes"]
        if c["saldo_conta"] + sum(e["valor"] for e in c["entradas_previstas"] if e["dia_offset"] <= c["fatura"]["dias_ate_vencimento"])
        - sum(s["valor"] for s in c["saidas_previstas"] if s["dia_offset"] <= c["fatura"]["dias_ate_vencimento"])
        < c["fatura"]["valor_total"]
    )
    print(f"gerado {caminho} | clientes={len(dados['clientes'])} negativados={neg} em_aperto_no_vencimento={aperto}")
