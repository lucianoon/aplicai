# IA responsável no protótipo

Clientes fictícios, operações em memória. Os controles abaixo são demonstráveis e
testados, mas não são autenticação bancária, certificação de conformidade nem
garantia de ausência de vieses. Base: PR #1 (`fix/rai-guardrails`), portado para o
desenho atual.

## Identidade
- O cliente vem do `state["cliente_id"]` da sessão; nenhuma tool recebe cliente do modelo.
- `iniciar_atendimento` simula o login e fixa o titular uma vez. Pedido de outro
  cliente ("sou o marido", "agora sou o C002") é bloqueado e auditado.
- Para demonstrar outra persona, abra uma sessão nova.
- Produção: titular vindo da sessão autenticada do canal, nunca da conversa.

## Aprovação de ações (pagar, parcelar)
Controle estrutural: não depende de detectar o texto de um ataque.

1. O `before_tool` calcula a cotação com dados do core (cliente, ação, vencimento,
   fatura, parcelas, parcela e custo total, ou valor) e pede aprovação pelo fluxo
   nativo do ADK (`adk_request_confirmation`). O texto mostrado é gerado da cotação,
   não pelo modelo.
2. A aprovação vale **5 minutos**, para **aquela chamada e aquela cotação**, e é
   **consumida uma vez**. Recusa, expiração, cotação editada no canal ou valores que
   mudaram no core bloqueiam a operação.
3. Aprovada, o host assina uma **capacidade** (HMAC, 60 segundos) que o modelo nunca
   vê. O core confere assinatura, validade, ação, cliente e parâmetros, **recalcula a
   cotação** e só então executa. A mesma capacidade repetida devolve o recibo
   original, sem novo débito.
4. Vale igual para tools diretas e MCP: capacidade enviada pelo modelo é descartada
   e o segredo vai ao processo MCP pelo ambiente (`COPILOTO_AUTH_SECRET`).

Escrever "sim" no chat não autoriza nada. Sem a capacidade, o core recusa mesmo que
o guardrail seja removido por engano.

## Entrada
- Dado pessoal mascarado em todo texto enviado ao modelo: CPF, CNPJ, RG, cartão
  (inclusive Amex), chave Pix aleatória, telefone fixo e celular, e-mail, CEP, endereço,
  agência e conta, CVV e data de nascimento. Os padrões contextuais (RG, conta, CVV,
  nascimento) exigem a palavra-chave junto, para não mascarar valores em reais.
- Injeção de prompt detectada só na mensagem do turno, também com ofuscação simples
  (acentos, caracteres invisíveis, leetspeak). Uma tentativa antiga não bloqueia os
  turnos seguintes. "Tem opção sem juros?" não é tratado como ataque.

## Saída
- PII na resposta do modelo é mascarada.
- Promessa indevida troca a resposta por uma mensagem segura: crédito aprovado ou
  garantido, empréstimo sem juros, "sem consulta ao Serasa", humano "já acionado".
  Frases com negação ("não posso garantir a aprovação") passam.
- Resposta discriminatória troca a resposta por uma mensagem de respeito: inferir
  saúde, religião, raça, orientação ou gênero a partir dos gastos; generalizar por
  grupo ("mulheres costumam..."); usar idade, gênero ou negativação para restringir
  ("por ser negativada..."); ofensas. Com a mesma tolerância a negação ("não faço
  suposições sobre a sua saúde" passa) e testes de falso positivo ("gastos com
  farmácia", "saúde financeira", "a aposentadoria entra no dia 10").
- Não há checagem de todo valor em `R$` contra os resultados das tools: com modelo
  real, arredondamentos legítimos ("cerca de R$ 415") seriam bloqueados e a demo
  cairia. A garantia numérica é estrutural: os números vêm de `analisar_fatura` e
  qualquer execução usa a cotação do core.

## LGPD

### Minimização (art. 6º, III)
- O modelo recebe: primeiro nome, familiaridade com finanças, canal preferido, objetivo
  declarado, fatura e itens por categoria, saldo e fluxo previsto, renda.
- Ficam no core e nunca vão ao modelo: CPF, endereço, telefone, idade, score,
  negativação e histórico de rotativo. Negativação e rotativo só servem ao código
  (prioridade da rotina proativa), não à conversa.

### Dado sensível (art. 5º, II e art. 11)
- Necessidade de acessibilidade (baixa visão, leitor de tela) é dado de saúde.
  Só vai ao modelo e à memória depois de **consentimento explícito** registrado
  (`registrar_consentimento("acessibilidade", ...)`), com data.
- A oferta de adaptação é feita a **todos** que ainda não responderam, para não revelar
  quem tem alguma necessidade registrada. Recusar apaga a preferência e encerra a oferta.

### Bases legais (proposta para o protótipo; validar com o jurídico)
| Tratamento | Base legal sugerida |
| --- | --- |
| Conversa, diagnóstico, simulação e execução | Execução de contrato (art. 7º, V) |
| Avisos proativos antes do vencimento | Legítimo interesse (art. 7º, IX), com oposição a qualquer momento |
| Adaptação por acessibilidade | Consentimento específico (art. 11, I) |
| Auditoria de ações e consentimentos | Cumprimento de obrigação e exercício regular de direitos (art. 7º, II e VI) |

### Direitos do titular (art. 18) e oposição
- `meus_dados`: mostra o que é usado, o que não é, as preferências e os consentimentos.
- `apagar_meus_dados`: apaga as preferências lembradas. O registro de consentimentos e
  de operações fica como comprovação.
- Oposição aos avisos: `registrar_consentimento("avisos_proativos", false)`. O registro é
  persistido no core (`mock_core/consentimentos.json`) e a rotina proativa respeita.
  Toda mensagem proativa termina com "é só responder PARAR".

### Decisões automatizadas (art. 20)
- A recomendação vem com `motivo_recomendacao`, gerado pelo código a partir de
  números: o cliente sempre sabe por que aquela opção e decide sozinho.
- A prioridade da rotina proativa vem com `motivo_prioridade`. Ela só define quem
  recebe ajuda primeiro; ninguém perde opções por causa dela.

### Retenção e transferência internacional
- Protótipo: dados 100% fictícios, tudo em memória, exceto auditoria e consentimentos
  em arquivo local fora do Git.
- A sessão do ADK guarda o texto original do cliente; a redação vale para o que vai ao
  modelo. Se as sessões forem persistidas, redigir antes de gravar e definir prazo.
- Produção: prazo de retenção por tipo de dado; confirmar região de processamento e
  termos do provedor. No Gemini API gratuito, os termos podem permitir uso do conteúdo
  para melhorar produtos; no pago ou no Enterprise, não (confirmar os termos vigentes).
  Transferência internacional exige base do art. 33.

## Equidade
- As contas recebem só fatura, saldo previsto, renda e prazo. Um teste contrafactual
  troca nome, idade, negativação, score, letramento e acessibilidade da mesma cliente e
  confere que o diagnóstico sai idêntico.
- Letramento e acessibilidade mudam o jeito de explicar, nunca as opções oferecidas.
- O prompt proíbe deduzir características pessoais e tratar alguém diferente por
  idade, gênero ou histórico de crédito; o filtro de saída barra quando acontece.
- Eval com LLM: casos de mesma situação com idade diferente (10) e pedido de inferência
  de saúde (11).
- Produção: medir impacto por faixa etária, região e gênero declarado (quando houver)
  nas métricas do piloto.

## Memória
- Só chaves e valores de uma lista permitida (canal, linguagem, lembrete, opção
  preferida e acessibilidade, esta com consentimento), separada por cliente.
  Texto livre, como saúde, família ou religião, é recusado.
- O encaminhamento humano guarda só uma categoria e diz ao cliente que, no protótipo,
  é simulado e que o atendimento real está nos canais oficiais.

## Limites conhecidos
- Filtros de texto são heurísticos: podem deixar passar paráfrases.
- O core, as capacidades usadas e a idempotência ficam em memória; o processo MCP
  tem uma cópia própria do core.
- A redação cobre o que vai ao modelo, não o histórico original do ADK nem toda telemetria.
- Streaming e Live/áudio não foram validados.
- Produção: Model Armor e Sensitive Data Protection no Agent Gateway, autenticação
  real, segredo em Secret Manager/KMS, core transacional compartilhado, retenção de
  dados e avaliação de equidade.

## Validação
- `uv run pytest` (sem LLM): aprovação, recusa, expiração, cotação editada, valores
  alterados, capacidade forjada, adulterada, expirada, reutilizada e para outro
  parâmetro ou cliente, caminho MCP real por stdio, filtros de entrada e saída
  (incluindo dados pessoais brasileiros e discriminação, com falsos positivos),
  minimização, contrafactual de equidade, consentimento, direitos do titular,
  oposição respeitada pela rotina proativa, memória e encaminhamento.
- `adk eval` (com LLM): casos 01 a 12 em `eval/`, incluindo promessa de crédito, dado
  sensível na memória, falso positivo de injeção, equidade por idade, inferência de
  saúde e direitos do titular.
