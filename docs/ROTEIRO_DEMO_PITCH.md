# Roteiro da Apresentação (5 minutos)

> **Interface:** app em `http://localhost:8080` (ou a URL do Cloud Run)
> **Frase-guia:** a IA conversa, o código calcula e o cliente aprova.
> **Números:** só os da base do evento e do simulador do projeto (ver `docs/BUSINESS_CASE_E_DADOS.md`).

---

## 1. Divisão do tempo

| Tempo | Bloco |
| --- | --- |
| 0:00–0:40 | O problema, com os dados da base |
| 0:40–1:20 | A solução e o posicionamento conservador |
| 1:20–3:20 | Demo ao vivo: Diego, Carla e Ana |
| 3:20–4:10 | Por que é seguro |
| 4:10–4:45 | Valor e métricas do piloto |
| 4:45–5:00 | Fechamento |

---

## 2. Fala

### [0:00–0:40] O problema
> "Analisamos as 467 mil transações de mil clientes da base do evento e encontramos dois problemas opostos.
> Metade dos clientes ganha mais do que gasta, e essa sobra fica parada na conta rendendo zero.
> A outra metade gasta mais do que ganha: um terço da base entrou no cheque especial em 2025, muitas vezes porque o financiamento e a escola vencem logo depois do salário e a fatura vem depois.
> Um robô de investimento comum erra com os dois: oferece aplicação para quem está no vermelho e não olha as contas do mês de quem tem sobra."

### [0:40–1:20] A solução
> "O Gestor de Liquidez resolve os dois lados com uma regra: a IA conversa, o código calcula e o cliente aprova.
> Para quem tem sobra, ele calcula as contas dos próximos 30 dias, deixa esse dinheiro reservado e sugere investir só o que passa disso.
> E ele só oferece o investimento mais conservador que existe: CDB de liquidez diária, com garantia do FGC e resgate a qualquer dia. Não porque não sabemos fazer mais, mas porque é dinheiro que o cliente pode precisar no mês que vem. Mesmo assim, a oferta só aparece para quem tem o perfil de investidor em dia.
> Para quem está no aperto, ele bloqueia qualquer investimento e mostra a forma mais barata de pagar a fatura sem cair no rotativo."

### [1:20–2:00] Demo 1: Diego tem sobra
- **Ação:** abrir a conta do Diego.
> "O Diego tem R$ 38.250 na conta. Sem ele digitar nada, o app já separou R$ 9.700 para a fatura, as contas e o dia a dia do mês, e mostra que R$ 28.550 estão parados. O perfil de investidor dele está em dia, e o produto é o conservador."
- **Ação:** clicar em **Aplicar** e depois em **Autorizar**.
> "Ele vê o valor exato e aprova. Só com essa aprovação o sistema emite uma autorização assinada, e o banco refaz a conta antes de executar. Se ele tentasse aplicar o saldo inteiro, o sistema recusaria, porque ia faltar dinheiro para as contas."

### [2:00–2:35] Demo 2: Carla está no vermelho
- **Ação:** abrir a conta da Carla.
> "A Carla está com a conta negativa e uma fatura vencendo em dois dias. Aqui o app não oferece investimento nenhum: os juros da dívida dela são muito maiores que qualquer rendimento. Ele acolhe e encaminha para renegociação com uma pessoa, como pede a Lei do Superendividamento. E essa trava não depende da IA: mesmo que alguém pedisse a aplicação direto, o banco recusaria."

### [2:35–3:20] Demo 3: Ana, pelo chat
- **Ação:** abrir a IA.Í na conta da Ana e digitar: *"Não vou conseguir pagar a fatura toda, o que eu faço?"*
> "A Ana tem R$ 610 e uma fatura de R$ 1.850. A IA mostra a melhor opção que cabe no bolso dela: pagar R$ 549 agora e parcelar o resto em 6 vezes de R$ 294,04. Isso custa R$ 375,10 a menos do que pagar o mínimo e entrar no rotativo. Esses números não foram calculados pela IA: vêm do código, e a IA só explica."

### [3:20–4:10] Por que é seguro
> "Três garantias.
> Primeiro, a IA não faz conta: juros, parcelas, impostos e rendimento são código testado. São 156 testes automáticos que rodam sem internet.
> Segundo, a IA não movimenta dinheiro sozinha: toda operação passa por uma cotação, pela aprovação do cliente e por uma autorização com assinatura digital, válida por 60 segundos e uma única vez. Escrever 'sim' no chat não aprova nada.
> Terceiro, política de investimento em código: sem dívida, sem falta de dinheiro para as contas, com perfil de investidor em dia e só o produto conservador. E privacidade: CPF, cartão e telefone são mascarados antes de chegar à IA, e ninguém consegue ver dados de outra pessoa."

### [4:10–4:45] Valor e métricas
> "Para o cliente: dinheiro que rende sem risco de faltar para as contas, e menos juros quando aperta.
> Para o banco: captação de quem tem sobra e menos inadimplência no rotativo.
> No piloto, a métrica que mais importa é zero cliente que investiu pelo agente e depois ficou sem dinheiro para uma conta. Junto com ela, medimos quantos clientes deixam de cair no rotativo depois do aviso e quanto da sobra vira investimento."

### [4:45–5:00] Fechamento
> "Gestor de Liquidez: a IA conversa, o código calcula e o cliente decide. Obrigado."

---

## 3. Plano B

- **Gemini fora do ar ou sem cota:** subir o servidor com `COPILOTO_MODEL=demo`; o chat da Ana roda sem internet.
- **App não abre:** narrar com prints das telas do Diego e da Carla (deixar as abas abertas antes).
- **Tempo estourando:** se a demo passar de 2 minutos, cortar a Ana e ficar com Diego e Carla.

---

## 4. Perguntas prováveis da banca

### Proteções

**"Que proteções vocês têm?"**
> "Quatro momentos. Antes da IA: mascaramos dados pessoais e bloqueamos tentativas de manipulação. Antes de cada ferramenta: só o titular da sessão, e toda operação exige cotação e aprovação. Na execução: o banco confere a assinatura, refaz a conta e aplica as regras. Depois da IA: bloqueamos promessa de crédito e respostas discriminatórias. Cada bloqueio vira um evento na trilha de auditoria."

**"E se a IA errar e aplicar mais do que devia?"**
> "Ela não consegue. O limite do que pode ser investido é calculado em código, dentro da cotação, e o banco recalcula antes de executar. Se o valor passar da sobra do mês, a operação é recusada."

### Políticas de investimento

**"Vocês estão dentro das políticas para oferecer investimento?"**
> "Oferecemos só o produto mais conservador: CDB de liquidez diária, com FGC, adequado a qualquer perfil de investidor. A oferta exige perfil de investidor respondido e dentro da validade; sem isso, o app pede a atualização do questionário e a aplicação é recusada também na execução. Quem tem saldo negativo, dívida em atraso, uso frequente do rotativo ou falta de dinheiro para as contas do mês não recebe oferta. Rendimento líquido, IOF, IR e garantia aparecem antes da aprovação, e a IA não recomenda ações nem produtos de risco. É uma política interna inspirada na Resolução CVM 30 e na Lei 14.181."

**"Só CDB não é pouco?"**
> "É de propósito. É dinheiro da conta corrente que o cliente pode precisar no mês seguinte, então liquidez diária é requisito. Com a adequação ao perfil completa, o mesmo núcleo passa a oferecer produtos de outros perfis."

> **Não dizer:** "conformidade com a CVM 30" (dizer "inspirada") nem "resgate automático programado" (o sistema só sugere o resgate antes da maior conta do mês; não agenda).

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
