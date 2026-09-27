# IA responsável e guardrails

> **Sistema:** Aplicaí
> **Referências:** LGPD (Lei 13.709/2018), Lei 14.181/2021 (superendividamento), Resolução CVM 30 (adequação ao perfil),
> Resolução CMN 4.549/2017 (rotativo), Lei 14.690/2023 (teto de encargos), Resolução Conjunta nº 8/2023 (educação financeira).
> Os controles abaixo são **inspirados** nessas normas e estão em código, com testes. Não são certificação de conformidade.
> A tabela risco → controle → prova está em `ARQUITETURA_GCP_GUARDRAILS_E_JORNADA.md`; este documento explica os princípios e os detalhes.

---

## 1. Princípios adotados neste projeto

1. **O cliente primeiro.** O Aplicaí não oferece investimento a quem está no vermelho nem crédito a quem não cabe: para essas pessoas, a melhor aplicação é não pagar juros.
2. **O código calcula.** Nenhum valor que o cliente vê (juros, parcela, rendimento, reserva) sai do modelo de linguagem.
3. **O cliente aprova.** Nenhuma operação acontece sem o cliente ver o valor exato e aprovar, e a aprovação não é texto.
4. **Privacidade por padrão.** O modelo recebe só o necessário; dados pessoais são mascarados; dado sensível só com consentimento; o cliente vê, apaga e se opõe.
5. **Tratamento igual.** As decisões dependem só de valores financeiros; idade, gênero, score e negativação não mudam opções.
6. **Tudo registrado.** Operações, bloqueios, consentimentos e aprovações ficam numa trilha de auditoria.

---

## 2. As quatro camadas

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. ANTES DO MODELO  (redigir_pii_before_model)                   │
│    máscara de dados pessoais · bloqueio de manipulação           │
├──────────────────────────────────────────────────────────────────┤
│ 2. ANTES DE CADA FERRAMENTA  (politica_before_tool)              │
│    só o titular da sessão · parâmetros válidos ·                 │
│    operação exige cotação + aprovação                            │
├──────────────────────────────────────────────────────────────────┤
│ 3. NA EXECUÇÃO  (autorizacao.py · store.executar_autorizada)     │
│    regras de elegibilidade e limite da sobra dentro da cotação · │
│    autorização assinada (HMAC, 60 s, uso único) ·                │
│    banco recalcula · idempotência                                │
├──────────────────────────────────────────────────────────────────┤
│ 4. DEPOIS DO MODELO  (validar_saida_after_model)                 │
│    máscara na resposta · promessa indevida · discriminação       │
└──────────────────────────────────────────────────────────────────┘
```

Todas rodam em código, como callbacks do ADK ou dentro do banco, e valem para os dois agentes. Não dependem de o modelo obedecer ao prompt.

---

## 3. Detalhe de cada camada

### 3.1 Antes do modelo (`copiloto_fatura/guardrails.py`)

**Máscara de dados pessoais (LGPD, art. 6º, III).** Antes de qualquer texto chegar ao Gemini, os padrões abaixo são trocados por marcadores como `[CPF_REDIGIDO]`: CPF, CNPJ, RG, cartão (inclusive Amex), chave Pix aleatória, telefone fixo e celular, e-mail, CEP, endereço, agência e conta, código de segurança e data de nascimento. Os padrões que dependem de contexto (RG, conta, CVV, nascimento) exigem a palavra-chave junto, para não mascarar valores em reais. Opcionalmente, o Google Cloud Sensitive Data Protection faz a detecção (`COPILOTO_USE_CLOUD_DLP=1`), com os padrões locais como reserva.

**Bloqueio de manipulação.** Frases como "ignore suas instruções", "modo desenvolvedor", "revele o prompt", "você agora é" são detectadas na mensagem do turno, inclusive com disfarces (acentos, caracteres invisíveis, números no lugar de letras). O sistema responde com uma mensagem fixa **sem chamar o modelo**: custo zero. Uma tentativa antiga não bloqueia os turnos seguintes, e perguntas legítimas ("tem opção sem juros?") passam.

**Auditoria.** Só a contagem por tipo de dado mascarado é registrada, nunca o valor. A trilha usa o identificador de negócio (`C004`), não dados pessoais.

### 3.2 Antes de cada ferramenta (`copiloto_fatura/guardrails.py`)

**Titular da sessão.** O cliente vem do estado da sessão; nenhuma ferramenta aceita cliente como argumento do modelo. Pedidos sobre outra pessoa ("a fatura do meu marido", "agora sou o C002") são bloqueados e auditados.

**Parâmetros.** Número de parcelas fora de 2 a 24, valores negativos ou não numéricos são recusados antes da cotação.

**Aprovação presa à cotação.** Para pagar, parcelar, aplicar ou resgatar, a proteção calcula a cotação e pede a aprovação pelo fluxo de confirmação do ADK. O texto que o cliente vê é gerado da cotação. A aprovação vale 5 minutos, para aquela chamada e aquela cotação, uma única vez; recusa, expiração, cotação editada ou valores que mudaram cancelam a operação.

**Consentimento e oposição (LGPD, art. 7º, 8º e 18).** A rotina de avisos consulta os consentimentos persistidos; `registrar_consentimento("avisos_proativos", false)` registra a oposição com data, e ela vale na hora. Apagar preferências não apaga o registro da oposição, que é a prova de que a escolha foi respeitada.

### 3.3 Na execução (`copiloto_fatura/autorizacao.py`, `gestor_caixa/portao_risco.py`, `mock_core/store.py`)

**Regras de elegibilidade dentro da cotação.** Para `aplicar_cdb`, a cotação só existe se o cliente passar por cinco regras, nesta ordem:

```text
gestor_caixa/portao_risco.py (resumo)
saldo negativo                                         -> BLOQUEIO_SALDO_DEVEDOR
endividado (negativado ou 3+ meses no rotativo em 12)  -> BLOQUEIO_SUITABILITY
saldo não cobre as contas dos próximos 30 dias         -> BLOQUEIO_LIQUIDEZ
sobra abaixo do mínimo para oferta                     -> BLOQUEIO_COLCHAO
perfil de investidor ausente ou vencido                -> BLOQUEIO_PERFIL_INVESTIDOR
```

e o valor não pode passar da sobra do mês. Como a cotação roda no guardrail e de novo no banco, a regra vale no chat, no app e no MCP: não dá para contorná-la chamando a operação direto.

**Autorização assinada.** Aprovada a cotação, o sistema emite:

```json
{
  "payload": {
    "cotacao": {"acao": "aplicar_cdb", "cliente_id": "C004", "valor": 28550.0,
                "dias_permanencia": 30, "rendimento_liquido": 189.07},
    "nonce": "a3f8194e82b7194c",
    "expira": 1758931200
  },
  "assinatura": "<HMAC-SHA256 do payload com a chave do sistema>"
}
```

O banco não confia no que o modelo diz que foi aprovado: confere a assinatura, a validade (60 s), a operação, o cliente e os parâmetros, **recalcula a cotação** e só executa se o resultado for idêntico. Se um débito caiu segundos antes e a cotação mudou, recusa. A mesma autorização apresentada de novo devolve o comprovante original (uso único); a mesma operação no mesmo ciclo da fatura também (idempotência por chave de negócio). A chave de assinatura vem do Secret Manager em produção e nunca passa pelo modelo nem pelo cliente.

### 3.4 Depois do modelo (`copiloto_fatura/guardrails.py`, `copiloto_fatura/prompts.py`)

**Dados pessoais na resposta** são mascarados.

**Promessa indevida.** Crédito "aprovado" ou "garantido", empréstimo sem juros, "sem consulta ao Serasa", atendente "já acionado": a resposta inteira é trocada por uma mensagem segura, e chamadas de ferramenta que vinham junto são descartadas. Frases com negação ("não posso garantir a aprovação") passam. Rendimento é sempre "estimado", nunca "garantido"; o modelo não recomenda ações nem produtos de risco.

**Discriminação e inferência sensível.** Deduzir saúde, religião, raça, orientação ou gênero a partir dos gastos; generalizar por grupo ("mulheres costumam..."); usar idade, gênero ou negativação para restringir; ofender. A resposta é trocada por uma mensagem de respeito. Há testes de falso positivo: "gastos com farmácia", "saúde financeira" e "a aposentadoria entra no dia 10" passam.

**Superendividamento (Lei 14.181/2021).** Para quem está no vermelho, o modelo é instruído a acolher, não julgar, mostrar a opção de menor parcela e encaminhar para atendimento humano; o encaminhamento no protótipo é simulado e o modelo diz isso. Crédito pessoal só aparece se a parcela couber em 30% da renda, e nunca é recomendado, só mostrado.

---

## 4. Tratamento igual e minimização

- **O que vai ao modelo:** primeiro nome, familiaridade com finanças, canal preferido, objetivo declarado, fatura e itens, saldo e contas previstas, renda, perfil de investidor (perfil e validade).
- **O que fica no banco:** CPF, endereço, telefone, idade, score, negativação, histórico de rotativo. Negativação e rotativo só são usados pelo código (elegibilidade e prioridade dos avisos).
- **Teste contrafactual:** trocar nome, idade, score, negativação, familiaridade e acessibilidade da mesma cliente não muda um byte do diagnóstico da fatura.
- **Acessibilidade é dado de saúde:** só vai ao modelo e à memória com consentimento explícito; a oferta de adaptar as respostas é feita a todos, para não revelar quem tem algo registrado.
- **Memória:** só chaves e valores de uma lista permitida; texto livre (saúde, família, religião) é recusado.
- **Decisões explicáveis (LGPD, art. 20):** a recomendação de pagamento vem com o motivo; a recusa de investimento vem com código e explicação; a prioridade dos avisos vem com o motivo e não tira opções de ninguém.

---

## 5. Trilha de auditoria

Cada operação e cada bloqueio gera uma linha em `mock_core/audit.jsonl` com data e hora em UTC, o identificador de negócio do cliente e:

- **operações:** ação, chave de idempotência, comprovante ou contrato, valores, canal (`agente`, `mcp` ou `app_superapp_itoken`);
- **guardrails:** `pii_redigida` (contagem por tipo), `injecao_bloqueada`, `acesso_terceiro_bloqueado`, `troca_de_titular_bloqueada`, `aprovacao_solicitada`, `acao_recusada_pelo_cliente`, `aprovacao_invalida` (com o motivo), `acao_autorizada`, `promessa_bloqueada`, `resposta_discriminatoria_bloqueada`, `pii_na_saida_redigida`;
- **consentimentos e lembretes:** finalidade, aceite ou recusa, data.

Isso permite medir quantas vezes cada proteção agiu. Em produção, a trilha vai para armazenamento imutável e centralizado (Cloud Logging ou equivalente).

---

## 6. Como se prova

- `uv run pytest`: 156 testes sem internet. Entre eles: 18 dos guardrails, 7 da autorização (forjada, adulterada, expirada, reutilizada, outro cliente ou parâmetro), 14 de LGPD e equidade, 18 do núcleo de liquidez e elegibilidade, 15 do agente com o fluxo de aprovação, 1 de integração MCP por `stdio`.
- `uv run pytest eval -s`: avaliação com o Gemini real. Na rodada de 23/09, 12 de 12 casos passaram: dado de terceiro, injeção (0 tokens), CPF e cartão no texto, promessa de crédito, dado de saúde na memória, equidade por idade, "você acha que estou doente?", direitos do titular e oposição, e a operação pausando para aprovação (`docs/eval_resultados.md`).

---

## 7. Limites conhecidos

- Os filtros de texto são heurísticos e podem deixar passar paráfrases. A garantia forte é estrutural: o modelo não calcula nem executa.
- A máscara cobre o que vai ao modelo; a sessão do ADK guarda o texto original. Se as sessões forem persistidas, mascarar antes de gravar e definir retenção.
- A avaliação com o Gemini cobre a jornada da fatura; a jornada de investimento tem testes determinísticos, mas ainda não tem caso na avaliação com modelo.
- A identidade do cliente é simulada; em produção vem do token do canal, validado no gateway.
- Banco, autorizações usadas e idempotência ficam em memória; o processo MCP tem a própria cópia.
- Streaming e voz não foram validados.
- Termos do provedor do modelo (uso do conteúdo para treinamento, região de processamento) e transferência internacional (LGPD, art. 33) precisam ser confirmados antes de um piloto.
