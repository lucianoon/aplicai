# Desenho de solução — Copiloto da Fatura

> Entregável 4. Peso: Arquitetura, Engenharia e Ciência de Dados (50%). Inclua o diagrama (docs/arquitetura.md ou LeanIX/Gliffy) e responda item a item.

## 1. Arquitetura do agente e uso de IA
- **Orquestração:** ADK 2.x, agente orquestrador (Gemini 3.8 Flash) + sub-agente de ação (transferência). Diagnóstico e simulação são uma tool determinística (`analisar_fatura`): LLM onde há conversa, código onde há conta.
- **Separação de responsabilidades:** LLM conversa e decide o fluxo; **cálculo financeiro é 100% código determinístico** (`simular_opcoes`), auditável e testado.
- **Detecção proativa em lote sem LLM** (`proativo/gatilho.py`): BigQuery/Pub/Sub em produção; LLM só na conversa (FinOps de tokens).
- **Escalável:** stateless por sessão; Agent Runtime com cold start sub-segundo; Gemini Flash para latência.

## 2. Contexto, memória e integrações
- **Contexto:** perfil (minimizado), fatura, extrato, fluxo previsto → diagnóstico estruturado.
- **Memória:** sessão (ADK Sessions) + preferências com escopo `user:` (Memory Bank em produção).
- **Integrações:** core bancário via MCP (`mock_core/server.py`), mesma interface para fatura, pagamento e parcelamento reais. Open Finance como fonte adicional de entradas/saídas (com consentimento).
- **Viabilidade:** contratos de tool = contratos de API; idempotência por chave; trilha de auditoria por ação.

## 3. Segurança, dados e experimentação
- **LGPD:** minimização (sem CPF/endereço no contexto do modelo), redação de PII antes do modelo, bloqueio de dados de terceiros por sessão, consentimento por finalidade, log auditável.
- **Guardrails:** injeção de prompt (callback) + Model Armor/Agent Gateway em produção; aprovação do cliente para toda ação via fluxo nativo do ADK (`request_confirmation`, a cotação exibida é calculada em código); titular fixo na sessão; limites de parâmetros; humano no loop.
- **Identidade e governança:** Agent Identity, Agent Registry, Skill Registry (Gemini Enterprise Agent Platform).
- **Dados:** dataset sintético calibrado (200 clientes); métricas de negócio por evento.
- **Experimentação:** A/B com holdout; evalset de 6 casos (feliz + adversariais) em `adk eval`; simulação sintética de usuários e autoraters (Evaluation Suite) como próximo passo.
- **Observabilidade:** traces do ADK, dashboard do Agent Runtime, `audit.jsonl` para ações e guardrails.
- **Performance:** Flash para conversa; simulador em milissegundos; gatilho em lote fora do horário de pico (deferred tier).

## 4. Diagrama
Ver `docs/arquitetura.md` (Mermaid) e exportar para a ferramenta exigida.
