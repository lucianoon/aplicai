# Ficha de submissão

Texto pronto para colar no formulário da Batalha de Agentes (Itaú + Google).

| Campo | Texto |
|---|---|
| **Nome do Agente** | Aplicaí |
| **Frase** | A sobra do mês rendendo, sem nunca faltar para as contas. |
| **Equipe** | Luciano de Oliveira Nunes |

## O Problema

Qual dor concreta queremos resolver e por que ela importa?

**1 frase.** Metade dos clientes deixa a sobra do mês parada na conta rendendo zero, por medo de faltar para as contas; a outra metade gasta mais do que ganha e cai no rotativo, o crédito mais caro do mercado.

**2 evidências / impactos**

1. Na base do evento (1.000 clientes, 467.585 transações de 2025), 507 clientes (50,7%) ganham mais do que gastam e 493 (49,3%) gastam mais do que ganham; 327 (32,7%) entraram no cheque especial no ano, com 56.141 transações feitas com saldo devedor.
2. R$ 25.000 parados deixam de render cerca de R$ 165 líquidos por mês (simulador do projeto, CDI a 10,75% a.a.). Do outro lado, a fatura de R$ 1.850 da persona Ana vira R$ 2.688,36 se ela pagar só o mínimo. Um robô de investimento comum oferece produto sem olhar o mês do cliente; a Resolução Conjunta nº 8 pede informação clara para a pessoa decidir.

## Momento do Usuário

Para quem estamos resolvendo e em qual situação?

**Persona + contexto / gatilho**

- **Diego (C004), sobra:** R$ 38.250 na conta, R$ 9.700 de contas nos próximos 30 dias, perfil de investidor em dia. Gatilho: card na tela inicial do app, sem digitar nada, com R$ 28.550 disponíveis para aplicar.
- **Elaine (C005), sobra sem perfil:** R$ 17.150 disponíveis, mas nunca respondeu o perfil de investidor. Gatilho: card pedindo a atualização do perfil; nenhuma oferta antes disso.
- **Carla (C003), dívida:** conta negativa e fatura vencendo em 2 dias. Gatilho: card de acolhimento e renegociação; investimento bloqueado.
- **Ana (C001), mês que não fecha:** fatura de R$ 1.850 e R$ 610 na conta. Gatilho: "não vou conseguir pagar a fatura toda", no chat, dias antes do vencimento.

Canal: app do banco, com o titular já identificado. O Aplicaí nunca escolhe o cliente; o cliente vem da sessão.

## Proposta do Agente

Como o agente ajudará a resolver essa dor?

**1 proposta de valor.** O Aplicaí projeta os próximos 30 dias do cliente, reserva o dinheiro das contas e faz só a sobra render, no investimento mais conservador que existe (CDB de liquidez diária com FGC), com um toque. Quando o mês não fecha, o mesmo motor mostra o jeito mais barato de pagar a fatura sem cair no rotativo. A IA conversa, o código calcula e o cliente aprova.

**3 capacidades**

1. **Reservar** — identifica as contas dos próximos 30 dias (financiamento, escola, fatura) e calcula, em código, quanto precisa ficar na conta e quanto sobra.
2. **Decidir com regras** — só oferece investimento a quem não está no vermelho, não tem dívida em atraso, tem dinheiro para as contas do mês e perfil de investidor válido; para os demais, mostra a opção mais barata para a fatura.
3. **Executar com aprovação** — cotação exata, aprovação do cliente e autorização assinada que o banco confere e recalcula antes de aplicar, resgatar, pagar ou parcelar.

## Dados e tecnologia

Quais dados, inteligência e ações tornam a solução possível?

**Arquitetura (5 etapas)**

1. **Entrada** — titular fixado na sessão; dados pessoais mascarados e tentativas de manipulação bloqueadas antes de chegar à IA.
2. **Projeção em código** — contas dos próximos 30 dias, reserva, sobra e situação do cliente (endividado, falta prevista, equilibrado, sobra para investir).
3. **Regras de elegibilidade** — situação financeira, limite da sobra e perfil de investidor; cada recusa tem código e explicação.
4. **Conversa** — dois agentes no Google ADK (um conversa, outro executa) com Gemini; o modelo explica os números das ferramentas e nunca calcula; base de normas (rotativo, IOF, superendividamento, Resolução Conjunta nº 8) para explicar direitos.
5. **Operação** — cotar → aprovar → autorização HMAC-SHA256 de uso único (60 s) → o banco recalcula e executa, com idempotência e trilha de auditoria. Vale igual no app, no chat e pelo MCP.

**Dados / tecnologias**

- Dados: saldo, entradas e saídas previstas, fatura e itens, renda, perfil de investidor (perfil e validade). Idade, score, negativação e histórico de rotativo ficam no banco e nunca vão ao modelo.
- Stack: Google ADK 2.x (dois agentes), Gemini, Cloud Run, FastAPI, Python; servidor MCP do banco simulado; modo `demo` sem cota para a jornada da fatura; 156 testes automatizados sem internet.

## Como mediremos valor

Como saberemos que a solução gerou valor?

1. **Segurança da reserva:** zero clientes que aplicaram pelo Aplicaí e ficaram sem saldo para uma conta nos 30 dias seguintes.
2. **Sobra que rende:** parte da sobra elegível convertida em aplicação e adesão ao card em um toque (meta acima de 35%).
3. **Saída do rotativo:** queda de pelo menos 25% em clientes que caem no rotativo depois do aviso, e economia em reais frente ao "se não fizer nada" (R$ 375,10 na persona Ana).
4. **Segurança da operação:** zero execução sem aprovação e sem autorização assinada válida; zero diferença de oferta por idade ou gênero na mesma situação.

## Escopo da Demo

O que será demonstrado ao final?

**Jornada ponta a ponta (Diego), mais as travas e o outro lado**

Abrir o Diego → card com R$ 9.700 reservados e R$ 28.550 disponíveis → Aplicar → Autorizar → saldo e custódia atualizados. Abrir a Carla (conta negativa: sem oferta, acolhimento) e a Elaine (sobra sem perfil de investidor: sem oferta, pede atualização). Se houver tempo, a Ana no chat: "não vou conseguir pagar a fatura toda" → pagar R$ 549 agora e parcelar o resto em 6x de R$ 294,04, R$ 375,10 a menos do que o rotativo → Aprovar. Nada se move sem o botão.

**Limites do protótipo**

- Cinco personas + base sintética; clientes e valores fictícios; taxas ilustrativas.
- Banco simulado; encaminhamento humano simulado; resgate sugerido, não agendado.
- Um único produto de investimento (CDB de liquidez diária); política inspirada na CVM 30 e na Lei 14.181, não certificação de conformidade.
- Sem voz, imagem ou arquivo.
- Protótipo da Batalha de Agentes, não é produto do Itaú.
