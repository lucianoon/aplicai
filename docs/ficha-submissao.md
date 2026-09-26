# Ficha de submissão — Parte 1 do Projeto

Texto pronto para colar no formulário da Batalha de Agentes (Itaú + Google).

| Campo | Texto |
|---|---|
| **Nome do Agente** | IA.Í — Copiloto da Fatura |
| **Equipe** | Luciano de Oliveira Nunes |

## O Problema

Qual dor concreta queremos resolver e por que ela importa?

**1 frase.** No vencimento da fatura a pessoa não entende o próprio caixa, não vê o custo de pagar só o mínimo e o rotativo vira a decisão padrão.

**2 evidências / impactos**

1. O case da Batalha cita 83,3 milhões de negativados (Serasa): o cartão é um dos caminhos mais comuns até essa lista.
2. Na persona Ana, a fatura de R$ 1.850,00 vira R$ 2.688,36 se ela pagar só o mínimo. Ensinar o conceito de rotativo sem ligar ao caixa dela não muda a decisão — a Resolução Conjunta nº 8 pede informação clara para a pessoa decidir, não só aula.

## Momento do Usuário

Para quem estamos resolvendo e em qual situação?

**Persona + contexto / gatilho**

- **Ana (C001), ajuste:** fatura de R$ 1.850,00, saldo previsto R$ 610,00, objetivo “sair do vermelho”. Gatilho: “como está minha fatura?” / “quero ver as opções”, dias antes do vencimento.
- **Bruno (C002), folga:** o salário cai antes do vencimento; dá para quitar sem juros e preservar a reserva.
- **Carla (C003), aperto:** o saldo não cobre o mínimo; o momento é de alívio e, se houver sofrimento, acolhimento humano (simulado).

Canal: conversa no app/WhatsApp do banco, com o titular já identificado. A IA.Í não escolhe o cliente.

## Proposta do Agente

Como o agente ajudará a resolver essa dor?

**1 proposta de valor.** A IA.Í, inteligência artificial do Itaú, transforma dado em contexto, contexto em previsão e previsão em um próximo passo que cabe — a pessoa decide; dinheiro só se move depois do Aprovar.

**3 capacidades**

1. **Entender** — o que está acontecendo com o dinheiro: fatura, caixa no vencimento, maiores itens do ciclo.
2. **Antecipar** — o que acontece se pagar o mínimo (rotativo) ou se quitar agora (sem juros).
3. **Orientar** — uma recomendada que cabe, em reais, e o caminho cotar → aprovar → executar.

## Dados e tecnologia

Quais dados, inteligência e ações tornam a solução possível?

**Arquitetura (5 etapas)**

1. **Entrada** — titular da sessão, PII redigida, injeção bloqueada; mensagem nova invalida aprovação antiga.
2. **Leitura em paralelo** — fatura, fluxo previsto e perfil no core mock.
3. **Diagnóstico em código** — opções, recomendada e “se não fizer nada”; o LLM não calcula.
4. **Conselho** — classificador + IA.Í no ciclo entender → antecipar → orientar; RAG nas normas do Bacen (inclui Resolução Conjunta nº 8).
5. **Ação** — `cotar_acao` → `RequestInput` (Aprovar) → `executar` com capacidade HMAC; o core confere de novo.

**Dados / tecnologias**

- Dados: fatura e itens, saldo e fluxo até o vencimento, objetivo declarado. Sem renda, idade, score ou negativação no que vai ao modelo.
- Stack: Google ADK 2.x (Workflow), Gemini, Vertex AI Embeddings + Agent Runtime, Cloud Run, Python, modo `demo` sem cota.

## Como mediremos valor

Como saberemos que a solução gerou valor?

1. **Saída do rotativo:** jornada que escolhe a recomendada (ou quitar) em vez do mínimo.
2. **Economia em R$** frente ao caminho “se não fizer nada” (já calculada no diagnóstico; na Ana, da ordem de R$ 375).
3. **Resposta útil:** polegar na conversa (`/api/avaliacao`).
4. **Segurança da ação:** zero execução sem Aprovar e sem capacidade HMAC válida.

## Escopo da Demo

O que será demonstrado ao final?

**1 jornada ponta a ponta (Ana)**

Abrir a Ana → “Quero ver as opções” → cartão ENTENDER / ANTECIPAR / ORIENTAR → “Quero a recomendada” → Aprovar o pagamento de R$ 549,00 → parcelar o resto em 6x → Aprovar. A fatura fecha parcelada; nada se move sem o botão.

**Limites do protótipo**

- Três personas + base sintética; clientes e valores fictícios.
- Core mock; encaminhamento humano é simulado.
- Sem voz, imagem ou arquivo.
- Protótipo da Batalha — não é produto do Itaú.
