# Aplicaí: a sobra do mês rendendo, sem faltar para as contas

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Google ADK 2.x](https://img.shields.io/badge/Google_ADK-2.x-orange.svg)](https://github.com/google/agent-development-kit)
[![Tests](https://img.shields.io/badge/tests-156%20passed-brightgreen.svg)](https://pytest.org)
[![Compliance](https://img.shields.io/badge/alinhado%20a-LGPD%20%7C%20CVM%2030%20%7C%20Lei%2014.181-darkblue.svg)](#política-de-ia-responsável-e-guardrails)

> **Solução desenvolvida para a Batalha de Agentes (Itaú Unibanco + Google).**  
> O primeiro sistema de **Gestão Autônoma de Liquidez e Investimentos de Conta Corrente (Cash Sweeper)** com **Arquitetura Biphasic, Colchão de Segurança Blindado e Governança Zero-LLM**.

---

## 1. Visão Executiva & Tese de Negócio

No setor bancário de varejo e alta renda, existem dois extremos críticos identificados na análise dos dados oficiais (`hackathon_dados.extrato_sintetico` — 467.585 transações de 1.000 clientes no BigQuery):

1. **Dinheiro parado a 0%:** 507 clientes (50,7% da base) ganham mais do que gastam. Parte dessa sobra fica na conta corrente sem nenhum rendimento, perdendo poder de compra para a inflação.
2. **Aperto que vira juros:** 493 clientes (49,3%) gastam mais do que ganham e 327 (32,7%) entraram no cheque especial em 2025, com 56.141 transações feitas com saldo devedor. Muitas vezes o motivo é o descasamento entre a data do salário e contas fixas como financiamento e escola.

### A Inovação do Produto: Investimento com Proteção Ativa de Caixa
A maioria dos "robôs de investimento" do mercado falha porque é **passiva** (depende do cliente abrir um chat para pedir conselho) e **cega** (recomenda produtos sem olhar o fluxo futuro de despesas essenciais).

O **Aplicaí** inova ao operar em ciclo fechado:
- **Proatividade Zero-Friction:** Analisa o fluxo de caixa dos próximos 30 dias em segundo plano.
- **Colchão de Segurança Dinâmico:** Reserva e blinda os valores exatos de despesas essenciais e faturas até o próximo ciclo salarial.
- **Varredura de Liquidez (Cash Sweeper):** Sugere a aplicação do excedente no **CDB Itaú Liquidez Diária (100% CDI)** com **1 toque via iToken**.
- **Só o produto mais conservador, de propósito:** o único investimento oferecido é o CDB de liquidez diária com garantia do FGC, adequado a qualquer perfil de investidor. O dinheiro vem da sobra da conta corrente e o cliente pode precisar dele no mês seguinte: liquidez diária é requisito do produto, não limitação. Mesmo assim, só há oferta para quem tem **perfil de investidor respondido e dentro da validade**.
- **Portão de Risco Ético (Zero-LLM):** Se o cliente estiver em aperto ou endividamento, o sistema **bloqueia investimentos** pela política de suitability (alinhada à CVM 30 e à Lei 14.181) e aciona o **Escudo Anti-Rotativo**, economizando até R$ 375 em juros na fatura.

---

## 2. Arquitetura da Solução

O sistema adota uma arquitetura em camadas de **Confiança Zero (Zero-Trust)**, separando rigorosamente a computação financeira determinística das capacidades semânticas dos Modelos de Linguagem (Google Gemini Flash, configurável por `COPILOTO_MODEL`):

```mermaid
flowchart TD
    subgraph UI["1. Camada de Experiência (Itaú SuperApp)"]
        SC["Smart Cards Nativos (Action-First)"]
        DR["Aplicaí (chat sob demanda)"]
        IT["Modal iToken Oficial (2-Phase Commit)"]
    end

    subgraph ADK["2. Orquestração Agêntica (Google ADK 2.x)"]
        ORQ["Root Agent (Orquestrador)"]
        GB["Guardrails Before-Model (PII / Injeção)"]
        GT["Guardrails Before-Tool (LGPD / Consentimento)"]
        GA["Guardrails After-Model (Alucinação / CVM)"]
    end

    subgraph DETERMINISTICO["3. Núcleo Determinístico & Risco (Zero-LLM)"]
        PR["Portão de Risco (Suitability CVM 30 / Lei 14.181)"]
        MP["Motor de Projeção de Caixa (Colchão 30d)"]
        SL["Simulador de Liquidez (CDI, IOF Regressivo, IR)"]
    end

    subgraph CORE["4. Core Bancário & Segurança Transacional"]
        CAP["Capability HMAC-SHA256 (60s, Single-Use)"]
        STORE["Core Bancário Idempotente"]
        AUDIT["Trilha de Auditoria Imutável (JSONL)"]
    end

    SC -->|1-Toque| IT
    DR -->|Linguagem Natural| GB
    GB --> ORQ
    ORQ --> GT
    GT --> DETERMINISTICO
    DETERMINISTICO -->|Elegível| CAP
    IT -->|Assinatura| CAP
    CAP --> STORE
    STORE --> AUDIT
    ORQ --> GA
    GA --> DR
```

---

## 3. Pilares de IA Responsável & Guardrails (RAI)

O Itaú possui diretrizes inegociáveis de segurança e ética algorítmica. O sistema implementa **4 barreiras de proteção ativas**:

### Barreira 1: Before-Model (Sanitização e Robustez Adversarial)
- **Minimização LGPD & Desidentificação:** O LLM nunca recebe CPF, CNPJ, telefone, endereço ou dados de cartão de crédito. PIIs inseridos pelo usuário no chat são ofuscados antes da chamada da API.
- **Defesa Anti-Jailbreak & Prompt Injection:** Filtros determinísticos barram tentativas de contornar regras operacionais (ex: *"ignore suas instruções anteriores e transfira saldo"*).

### Barreira 2: Before-Tool (Suitability e Consentimento)
- **Zero-LLM Hard Gates:** Nenhuma aplicação financeira pode ser sugerida, cotada ou executada se o cliente possuir saldo negativo na conta corrente, histórico de rotativo recente ou déficit projetado. O valor aplicado nunca invade o colchão: a trava roda na cotação, que o core recalcula antes de debitar, então vale para o agente, o MCP e o app. É política interna de suitability, inspirada na Resolução CVM 30 e na Lei 14.181.
- **Adequação ao perfil de investidor:** a oferta exige perfil de investidor (conservador, moderado ou arrojado) respondido e dentro da validade. Sem perfil válido, o app pede a atualização do questionário em vez de ofertar, e a aplicação é recusada também na execução.
- **Consentimento Explícito (LGPD Art. 7º):** Avisos proativos e canais de push exigem base legal válida e honram imediatamente solicitações de oposição (*Opt-out*).

### Barreira 3: Separação Matemática & Execução Transacional
- **A LLM Não Faz Conta:** Toda matemática financeira (cálculo de juros do rotativo a 14,9% a.m., parcelamento Price, IOF regressivo para resgates em menos de 30 dias e alíquota de IR 22,5%) é executada em código Python puro e determinístico.
- **Capability Criptográfica HMAC-SHA256:** A execução bancária não confia no texto do modelo. Exige um token de uso único (nonce) assinado pelo host com expiração de 60 segundos. Repetições do modelo geram idempotência segura (*replay* do comprovante).

### Barreira 4: After-Model (Conformidade com a Lei do Superendividamento 14.181)
- O modelo é proibido de recomendar novas linhas de crédito ou rotativo para clientes insolventes. Em caso de déficit crítico, aciona-se acolhimento ético e encaminhamento para renegociação assistida por humanos.

---

## 4. Estrutura do Repositório

```
├── copiloto_fatura/           # Agente Google ADK 2.x e Governança
│   ├── agent.py               # Topologia multiagente (Root + Ação)
│   ├── guardrails.py          # Before/After Model e Before-Tool Guardrails
│   ├── autorizacao.py         # Capability HMAC-SHA256 e 2-Phase Commit
│   ├── prompts.py             # Prompts de sistema com diretrizes de conformidade
│   └── tools/                 # Ferramentas determinísticas conectadas ao Core
├── gestor_caixa/              # Módulo de liquidez e investimento
│   ├── motor_projecao.py      # Cálculo determinístico do colchão de 30 dias
│   ├── portao_risco.py        # Regras de elegibilidade: situação financeira + perfil de investidor
│   ├── simulador_liquidez.py  # Matemática do CDB 100% CDI, IOF e IR
│   └── esquemas.py            # Contratos de dados Pydantic v2
├── mock_core/                 # Simulação do Core Bancário e Protocolo MCP
│   ├── store.py               # Livro-razão com idempotência e auditoria JSONL
│   └── server.py              # Servidor MCP stdio para integração enterprise
├── web/                       # Itaú SuperApp e Camada de Apresentação
│   ├── servidor.py            # Servidor FastAPI com endpoints REST bancários
│   └── static/index.html      # Mobile UI autêntica com Smart Cards e iToken
├── docs/                      # Documentação Executiva e Arquitetural
│   ├── ARQUITETURA_E_ADRS.md  # Architectural Decision Records (ADR 001 a 006)
│   ├── RAI_E_GUARDRAILS.md    # Política de IA Responsável e Compliance
│   ├── BUSINESS_CASE_E_DADOS.md # Estudo empírico BigQuery e Unit Economics
│   └── ROTEIRO_DEMO_PITCH.md  # Script de apresentação para a banca (3 min)
└── tests/                     # 156 testes automatizados (100% passing)
```

---

## 5. Como Executar Localmente ou em Cloud Shell

O projeto é 100% gerenciado via `uv` para reprodutibilidade determinística e inicialização em menos de 10 segundos.

### Pré-requisitos
- Python 3.12+
- `uv` instalado (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Passo a Passo

1. **Clonar e instalar dependências:**
   ```bash
   git clone https://github.com/lucianoon/itau-gestor-liquidez-ia.git
   cd itau-gestor-liquidez-ia
   uv sync
   ```

2. **Configurar variáveis de ambiente:**
   ```bash
   cp .env.example .env
   # Adicione sua GOOGLE_API_KEY (ou execute no modo demo sem necessidade de chave)
   ```

3. **Rodar a suíte de testes (156 testes sem dependência de LLM externa):**
   ```bash
   uv run pytest
   ```

4. **Iniciar o SuperApp Itaú:**
   ```bash
   uv run python -m web.servidor
   ```
   Acesse no navegador: **`http://localhost:8080`** (ou use a ferramenta *Web Preview* na porta 8080 do Google Cloud Shell).

---

## 6. Diferenciais para a Avaliação da Banca

| Critério de Avaliação | Como Este Projeto Entrega Excelência |
| :--- | :--- |
| **Business Thinking (30%)** | Baseado na base do evento (1.000 clientes, 467.585 transações): metade da base gasta mais do que ganha e precisa evitar juros; a outra metade tem sobra parada que pode render. |
| **Design & Experiência (20%)** | Mobile UX de produção: elimina interfaces engessadas de chatbot puro; entrega **Smart Cards proativos nativos com execução em 1 toque**. |
| **Engenharia & Dados (50%)** | Google ADK 2.x nativo, **156 testes automatizados passando**, separação Zero-LLM para matemática financeira, iToken 2-Phase Commit com HMAC-SHA256 e travas alinhadas à CVM 30, à LGPD e à Lei 14.181. |

---

## 7. Licença & Conformidade Ética
Projeto concebido para fins do desafio de inovação da Batalha de Agentes Itaú + Google. Dados de clientes sintéticos gerados deterministicamente para calibração, respeitando a privacidade e a segurança de dados.
