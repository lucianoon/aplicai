# Roteiro de Demonstração & Pitch Executivo (3 Minutos)

> **Playbook de Apresentação para a Banca Avaliadora (Itaú Unibanco + Google)**  
> **Tempo Total:** 3 minutos cronometrados  
> **Interface de Apoio:** Itaú SuperApp Mobile (`http://localhost:8080`)

---

## 1. Distribuição de Tempo do Pitch

```
00:00 - 00:35 ──────► 1. O Gancho & A Dor Empírica dos Dados (BigQuery)
00:35 - 01:20 ──────► 2. A Tese do Agente Autônomo de Liquidez & Investimentos
01:20 - 02:15 ──────► 3. Demonstração ao Vivo no SuperApp (Diego & iToken)
02:15 - 02:45 ──────► 4. Engenharia, Guardrails Zero-LLM & IA Responsável
02:45 - 03:00 ──────► 5. Fechamento de Impacto (Business & Escala)
```

---

## 2. Roteiro Passo a Passo (Script Falado)

### [00:00 - 00:35] O Gancho: A Descoberta no BigQuery
> *"Boa tarde, banca! Ao analisarmos as quase 500 mil transações da base oficial do Itaú no BigQuery, encontramos dois extremos gritantes:*  
> *De um lado, **metade dos clientes ganha mais do que gasta, e essa sobra fica parada na conta rendendo zero**.*  
> *Do outro lado, **a outra metade gasta mais do que ganha: um terço da base entrou no cheque especial em 2025**, muitas vezes porque o financiamento e a escola vencem logo depois do salário.*  
> *A maioria dos robôs de investimento do mercado falha porque é cega: tenta vender produto sem olhar o fluxo de contas do cliente. Hoje, apresentamos o **Itaú Gestor de Liquidez com IA**."*

---

### [00:35 - 01:20] A Tese de Produto: Investimento Biphasic
> *"O nosso agente não é um chatbot passivo de dar conselhos de ações. Ele opera um sistema de **Cash Sweeping Biphasic**:*  
> *1º) Ele calcula deterministicamente o fluxo dos próximos 30 dias e **blinda um colchão de segurança** para todas as contas essenciais e faturas do mês.*  
> *2º) O excedente ocioso é apresentado em **1 Smart Card Nativo** na tela inicial do Itaú SuperApp, pronto para render a 100% do CDI com **1 toque via iToken**.*  
> *E se o cliente estiver em aperto financeiro? O agente aciona o **Portão de Risco**: bloqueia investimentos por compliance com a CVM e protege o cliente com parcelamento sem juros abusivos."*

---

### [01:20 - 02:15] Demonstração ao Vivo (Live Demo no Celular)

#### Passo 1: Abertura na Conta de Diego Takahashi (Personnalité)
- **Ação:** Mostre a tela inicial do SuperApp.
- **Fala:** *"Aqui está o nosso SuperApp real. O Diego tem R$ 38.250 em conta. Veja que ele não precisa abrir chat nem digitar nada: logo abaixo do saldo, o **Smart Card Proativo** já calculou que R$ 9.700 são necessários para o colchão de despesas e faturas, e identificou **R$ 28.550 parados a 0%**."*

#### Passo 2: Aplicação com 1 Toque via iToken
- **Ação:** Clique no botão **`[⚡ Aplicar R$ 28.550 com iToken]`**.
- **Fala:** *"Em vez de atrito de texto, acionamos a autenticação bancária oficial. O modal do **iToken** exibe o código temporal de segurança, garantia do FGC e carência diária. Ao autorizar..."*
- **Ação:** Clique em **`[Autorizar Operação]`**.
- **Fala:** *"O sistema executa no Core Bancário via **capability assinada HMAC-SHA256**, emite o comprovante oficial com **hash digital SHA-256** e atualiza o saldo da conta e a custódia do CDB instantaneamente."*

#### Passo 3: O Copiloto IA.Í Sob Demanda
- **Ação:** Clique no botão flutuante **`[✨ IA.Í Copilot]`**.
- **Fala:** *"E se o cliente quiser entender as regras? O Copiloto IA.Í abre sob demanda. Ele pode perguntar sobre descontos de IOF, tributação regressiva ou simular resgates em linguagem natural, tudo respaldado pelos dados reais do extrato."*

---

### [02:15 - 02:45] Engenharia de Missão Crítica & Governança Bancária
> *"Por que essa solução está pronta para ir para produção amanhã?*  
> *Primeiro: **Zero-LLM Math**. Nenhuma conta de juros, CDI ou reserva é feita por inteligência artificial generativa; é código Python determinístico com **144 testes automatizados cobrindo 100% dos fluxos**.*  
> *Segundo: **Segurança em 4 Camadas**. Filtro de PII para LGPD, defesa contra Prompt Injection, travas regulatórias da CVM 30 e proteção ética contra o superendividamento da Lei 14.181."*

---

### [02:45 - 03:00] Fechamento: Impacto no Balanço do Itaú
> *"O resultado é uma vitória dupla: para o cliente, liquidez que rende todo dia com segurança; para o Itaú, bilhões em captação de CDB estável e redução direta de PDD no crédito rotativo.*  
> *Itaú Gestor de Liquidez com IA: inteligência autônoma que cuida do dinheiro de verdade. Muito obrigado!"*

---

## 3. Respostas Rápidas para Perguntas Difíceis da Banca

### P1: *"O Itaú ganha dinheiro com o rotativo. Por que o banco iria querer evitar que o cliente entre nele?"*
> **R:** *"Porque mais de 65% do rotativo vira inadimplência e custo de cobrança (dados do Banco Central). Desde a Lei 14.690/2023, os juros do rotativo têm teto de 100%. O parcelamento planejado tem 83% menos calote e preserva a margem financeira com crédito saudável e cliente fidelizado."*

### P2: *"E se a LLM errar o cálculo e aplicar mais dinheiro do que o cliente podia, fazendo ele entrar no cheque especial?"*
> **R:** *"Impossível pela nossa arquitetura. A LLM não tem acesso à execução direta. O `MotorProjecaoCaixa` e o `PortaoRisco` são módulos determinísticos Zero-LLM. Se a cotação mudar no segundo anterior à execução, a capability HMAC é rejeitada pelo core e a aplicação é cancelada."*

### P3: *"Por que não fazer tudo em um chatbot de WhatsApp?"*
> **R:** *"Nenhum correntista quer digitar texto e ler parágrafos para ver se pode aplicar R$ 1.000. O padrão do SuperApp é **Action-First com Smart Cards nativos** na tela inicial. O chat é um canal de suporte sob demanda, não a interface principal."*
