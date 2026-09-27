# Roteiro da Apresentação: Aplicaí (5 minutos)

> **Interface:** app em `http://localhost:8080` (ou a URL do Cloud Run)
> **Promessa:** a sobra do mês rendendo, sem nunca faltar para as contas.
> **Regra:** a IA conversa, o código calcula e o cliente aprova.
> **Números:** só os da base do evento e do simulador do projeto (ver `docs/BUSINESS_CASE_E_DADOS.md`).

---

## 1. Divisão do tempo

| Tempo | Bloco |
| --- | --- |
| 0:00–0:35 | O problema: dinheiro parado e medo de faltar |
| 0:35–1:15 | A promessa do Aplicaí e o produto conservador |
| 1:15–2:30 | Demo 1: Diego aplica a sobra com um toque |
| 2:30–3:15 | Demo 2: Carla e Elaine, quando o Aplicaí diz não |
| 3:15–4:05 | Por que é seguro |
| 4:05–4:40 | O outro lado da mesma regra: o mês que não fecha (Ana) |
| 4:40–5:00 | Fechamento |

---

## 2. Fala

### [0:00–0:35] O problema
> "Analisamos as 467 mil transações de mil clientes da base do evento. Metade deles ganha mais do que gasta, e essa sobra fica parada na conta rendendo zero.
> Por que não aplicam? Porque têm medo de faltar: o financiamento vence no dia 8, a escola no dia 10, a fatura no fim do mês. E o robô de investimento comum não olha nada disso: oferece o produto e deixa o risco com o cliente."

### [0:35–1:15] A promessa
> "O Aplicaí faz a sobra do mês render sem nunca tocar no dinheiro das contas.
> Ele projeta os próximos 30 dias, reserva o que vai sair e sugere aplicar só o que passa disso, num CDB de liquidez diária com garantia do FGC, o investimento mais conservador que existe. De propósito: é dinheiro que o cliente pode precisar no mês que vem, então liquidez diária é requisito, não limitação.
> E tem uma regra que nenhum robô tem: a IA conversa, mas não faz conta nem movimenta dinheiro. O código calcula, e o cliente aprova."

### [1:15–2:30] Demo 1: Diego aplica com um toque
- **Ação:** abrir a conta do Diego.
> "O Diego tem R$ 38.250 na conta. Sem digitar nada, ele já vê: R$ 9.700 reservados para a fatura, o financiamento e o dia a dia, e R$ 28.550 parados. O perfil de investidor dele está em dia, e o produto é o conservador."
- **Ação:** clicar em **Aplicar** e depois em **Autorizar**.
> "Ele vê o valor exato, o rendimento líquido e a garantia, e aprova. Só com essa aprovação o sistema emite uma autorização assinada, e o banco refaz a conta antes de executar."
- **Ação:** mostrar o saldo e a custódia atualizados.
> "Pronto: R$ 28.550 rendendo, e as contas do mês intactas. Se ele tentasse aplicar o saldo inteiro, o sistema recusaria, porque ia faltar dinheiro para o financiamento."

### [2:30–3:15] Demo 2: quando o Aplicaí diz não
- **Ação:** abrir a conta da Carla.
> "A Carla está com a conta negativa. O Aplicaí não oferece investimento nenhum: os juros da dívida dela são maiores que qualquer rendimento. Ele acolhe e encaminha para renegociação com uma pessoa, como pede a Lei do Superendividamento."
- **Ação:** abrir a conta da Elaine.
> "A Elaine tem R$ 17.150 sobrando, mas nunca respondeu o perfil de investidor. Sem perfil válido, não há oferta: o app pede a atualização primeiro. E essas duas travas não dependem da IA: mesmo que alguém pedisse a aplicação por elas, o banco recusaria."

### [3:15–4:05] Por que é seguro
> "Três garantias.
> Primeiro, a IA não faz conta: juros, impostos e rendimento são código testado. São 156 testes automáticos que rodam sem internet.
> Segundo, a IA não movimenta dinheiro: toda operação passa por cotação, aprovação do cliente e uma autorização com assinatura digital, válida por 60 segundos e uma única vez. Escrever 'sim' no chat não aprova nada.
> Terceiro, a política de investimento está em código: sem dívida, sem falta de dinheiro para as contas, com perfil de investidor em dia e só o produto conservador. E privacidade: CPF, cartão e telefone são mascarados antes de chegar à IA, e ninguém vê dados de outra pessoa."

### [4:05–4:40] O outro lado da mesma regra
- **Ação:** abrir o chat na conta da Ana e digitar: *"Não vou conseguir pagar a fatura toda, o que eu faço?"*
> "E quando o mês não fecha? O mesmo motor que protege as contas do Diego mostra para a Ana o jeito mais barato de pagar a fatura: R$ 549 agora e o resto em 6 vezes de R$ 294,04, R$ 375,10 a menos do que cair no rotativo. Para quem está no vermelho, a melhor aplicação é não pagar juros."

### [4:40–5:00] Fechamento
> "Aplicaí: a sobra do mês rendendo, sem nunca faltar para as contas. A IA conversa, o código calcula e o cliente decide. Obrigado."

---

## 3. Plano B

- **Gemini fora do ar ou sem cota:** subir o servidor com `COPILOTO_MODEL=demo`. O chat da Ana roda sem internet.
- **Chat no plano B:** o modo `demo` só cobre a jornada da fatura (Ana). Não digite perguntas sobre investimento no chat sem o Gemini; Diego, Carla e Elaine são mostrados pelos cards, que são código.
- **App não abre:** narrar com prints das telas do Diego, da Carla e da Elaine (deixar as abas abertas antes).
- **Tempo estourando:** cortar a Ana (bloco 4:05) e fechar direto. Diego, Carla e Elaine são o essencial.

---

## 4. Perguntas prováveis da banca

### Sobre o foco

**"Só CDB não é pouco?"**
> "É de propósito. É dinheiro da conta corrente que o cliente pode precisar no mês seguinte, então liquidez diária é requisito. Com a adequação ao perfil completa, o mesmo núcleo passa a oferecer produtos de outros perfis."

**"E quem não tem sobra?"**
> "Para esses, o Aplicaí faz o oposto: não oferece nada e mostra o jeito mais barato de pagar a fatura. É a mesma projeção de 30 dias; só muda o que ela recomenda. Metade da base do evento está nessa situação, então não é um caso de borda, é metade do produto."

### Proteções

**"Que proteções vocês têm?"**
> "Quatro momentos. Antes da IA: mascaramos dados pessoais e bloqueamos tentativas de manipulação. Antes de cada ferramenta: só o titular da sessão, e toda operação exige cotação e aprovação. Na execução: o banco confere a assinatura, refaz a conta e aplica as regras. Depois da IA: bloqueamos promessa de crédito e respostas discriminatórias. Cada bloqueio vira um evento na trilha de auditoria."

**"E se a IA errar e aplicar mais do que devia?"**
> "Ela não consegue. O limite do que pode ser investido é calculado em código, dentro da cotação, e o banco recalcula antes de executar. Se o valor passar da sobra do mês, a operação é recusada."

### Políticas de investimento

**"Vocês estão dentro das políticas para oferecer investimento?"**
> "Oferecemos só o produto mais conservador: CDB de liquidez diária, com FGC, adequado a qualquer perfil de investidor. A oferta exige perfil de investidor respondido e dentro da validade; sem isso, o app pede a atualização e a aplicação é recusada também na execução. Quem tem saldo negativo, dívida em atraso, uso frequente do rotativo ou falta de dinheiro para as contas do mês não recebe oferta. Rendimento líquido, IOF, IR e garantia aparecem antes da aprovação, e a IA não recomenda ações nem produtos de risco. É uma política interna inspirada na Resolução CVM 30 e na Lei 14.181."

> **Não dizer:** "conformidade com a CVM 30" (dizer "inspirada") nem "resgate automático programado" (o sistema só sugere o resgate antes do maior débito do mês; não agenda).

### O ciclo

**"Qual é o ciclo da solução?"**
> "Detectar, em lote e sem IA, a projeção dos próximos 30 dias. Diagnosticar a situação do cliente. Decidir pelas regras se pode investir ou se precisa de ajuda com a dívida. Ofertar no card do app ou no chat. Cotar em código. O cliente aprova. O banco executa sem duplicar. Tudo fica registrado. E acompanhamos o resultado e lembramos antes da próxima fatura, recomeçando no mês seguinte."

### Métricas

**"Como vocês sabem que funciona?"**
> "Hoje: 156 testes automáticos e uma avaliação com o Gemini real em que os 12 casos passaram, incluindo injeção, dado de terceiro, promessa de crédito, equidade por idade e dado de saúde, sem nenhuma operação executada sem aprovação. No piloto: zero cliente que investiu e ficou sem dinheiro para uma conta, queda de pelo menos 25% em quem cai no rotativo depois do aviso, adesão ao card acima de 35%, poucos resgates antes de 30 dias e nenhuma diferença de oferta por idade ou gênero na mesma situação."

> Observação: a avaliação com o Gemini (23/09) cobre a jornada da fatura; não há caso de avaliação da parte de investimento.

### Negócio

**"O banco ganha com o rotativo. Por que evitar?"**
> "Porque boa parte do rotativo vira inadimplência e custo de cobrança, e desde 2023 os juros têm teto de 100% da dívida. Um parcelamento que o cliente consegue pagar vale mais que uma dívida que não será paga."

**"Esses números são reais?"**
> "São da base do evento: mil clientes e 467 mil transações. As projeções para 100 mil clientes são hipóteses que o piloto precisa validar."

**"Por que o nome?"**
> "Aplicaí é como se fala: 'sobrou, aplica aí'. E o produto é isso: um toque para a sobra render, com a certeza de que as contas do mês estão protegidas."
