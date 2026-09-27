# Documento técnico resumido — Aplicaí

> Entregável 5. Justificativas, limitações, estratégia de testes e próximos passos para produção.

## 1. Decisões e justificativas
| Decisão | Alternativa descartada | Por quê |
|---|---|---|
| Cálculo em código determinístico | LLM calcula juros | Erro zero, auditável, testável, sem alucinação de número |
| Multiagente (orquestrador + ação) com diagnóstico em código | Sub-agente analista com LLM | Diagnóstico é determinístico: um LLM ali só somaria chamadas e tokens. Ação isolada com guardrail próprio |
| Gatilho proativo sem LLM | Varrer base com LLM | Custo por token ~zero; latência previsível |
| Aprovação nativa do ADK presa à cotação (5 min, uso único) + capacidade assinada conferida pelo core | Parâmetro `confirmado` preenchido pelo LLM | O modelo não consegue aprovar sozinho; recusa, expiração, edição ou mudança de valores bloqueiam; vale para tools diretas e MCP |
| Consentimento para acessibilidade, oferta igual para todos | Usar a acessibilidade do cadastro direto | É dado de saúde (sensível); oferecer a todos evita revelar quem tem necessidade registrada |
| Negativação e rotativo fora do payload do modelo | Mandar o perfil completo | Minimização e equidade: a IA não precisa desses dados para explicar, e eles poderiam enviesar tom ou oferta |
| Crédito pessoal nunca recomendado e só oferecido até 30% da renda | Oferecer o crédito mais barato a todos | Crédito responsável (Lei 14.181/2021): dívida nova só com capacidade de pagamento, e alerta explícito |
| Modo demo com modelo roteirizado | Depender só do Gemini na apresentação | Plano B sem internet e sem cota; o resto do sistema roda de verdade |
| Filtro de saída para PII, promessas indevidas e discriminação, sem checagem estrita de `R$` | Bloquear todo `R$` sem evidência exata | Arredondamento legítimo do modelo derrubaria a demo; a garantia numérica é estrutural (cotação do core) |
| Cliente sempre do `state` da sessão | `cliente_id` como argumento das tools | Fecha acesso a dados de terceiros e economiza tokens |
| Idempotência de negócio (ação + cliente + ciclo) | Id da chamada do LLM | Repetição do modelo vira replay, não execução dupla |
| MCP para o core | SDK acoplado | Protocolo aberto, mesma interface para mock e real |
| Gemini 3.8 Flash | Pro | Latência/custo; Pro só se o eval mostrar ganho |

## 2. Limitações conhecidas
- Taxas e regras são parâmetros aproximados; precisam dos valores do produto real.
- Memória de longo prazo em estado de sessão (Memory Bank não ligado no protótipo).
- Sem canal de voz no protótipo (Live API é próximo passo).
- Dados 100% sintéticos; sem Open Finance real.

## 3. Estratégia de testes
- **Sem LLM (zero tokens):** simulador, guardrails, mock do core, servidor MCP e o fluxo de aprovação ponta a ponta no runtime do ADK com um LLM roteirizado, local e via MCP (`uv run pytest`).
- **Resultado (23/09/2026):** 12 de 12 casos com `gemini-3.8-flash`; ~77 mil tokens de entrada nos 11 casos principais. A avaliação encontrou e corrigiu telefones inventados e um falso positivo do filtro de discriminação. Detalhes em `docs/eval_resultados.md`.
- **Eval do agente (com LLM):** `eval/copiloto_fatura.evalset.json` com caminho feliz, LGPD, injeção, ação sem confirmação, sofrimento financeiro e PII. Métricas: trajetória de ferramentas + juiz LLM na resposta final.
- **Próximo:** simulação de usuários sintéticos multi-turn e autoraters da Evaluation Suite; red team de injeção; testes de carga no Agent Runtime.

## 4. Caminho para produção
1. Ligar adapters reais atrás da mesma interface do `mock_core.store` (fatura, pagamento, parcelamento, crédito).
2. Deploy no Agent Runtime (`adk deploy agent_engine`), Sessions + Memory Bank.
3. Agent Gateway + Model Armor + Agent Identity; registro no Agent Registry.
4. Piloto com holdout (ex.: 5% da base com gap negativo), dashboards de métricas do entregável 1.
5. Integração ao ia.i e aos canais (app, WhatsApp, voz).
