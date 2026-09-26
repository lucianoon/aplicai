# Proposta de negócio — Copiloto da Fatura

> Entregável 1. Peso na rubrica: Business Thinking (30%). Números públicos com fonte e data; números da base
> sintética marcados como ilustração. Consultado em 23/09/2026.

## 1. Jornada escolhida
**Momento:** decisão de como pagar a fatura do cartão de crédito, nos dias que antecedem o vencimento.
- **Relevante e frequente:** acontece todo mês, para toda a base de cartões. O cartão de crédito movimentou
  R$ 1,7 trilhão no 1º semestre de 2026, alta de 12% em um ano (Abecs, via [Let's Money](https://www.letsmoney.com.br/noticias/cartoes-2-3-tri-1s26-credito-12/)).
- **Momento crítico:** é a porta de entrada do rotativo, o crédito mais caro do mercado, e da inadimplência.
- **Potencial em escala:** a mesma decisão, com os mesmos cálculos, vale para qualquer cliente com fatura aberta.

## 2. Dor do cliente (concreta, ligada a comportamento real)
- **O rotativo é caro demais para ser uma escolha consciente:** taxa média de **436% ao ano** (15,0% ao mês)
  para pessoa física em julho de 2026, contra 189% ao ano (9,3% ao mês) no parcelado ([BCB, séries 22022, 25477, 22023 e 25478](https://dadosabertos.bcb.gov.br/dataset/22022-taxa-media-de-juros-das-operacoes-de-credito-com-recursos-livres---pessoas-fisicas---cartao-d)).
- **E é onde a dívida desanda:** a inadimplência do rotativo de pessoa física chegou a **65,9%** em julho de
  2026, contra 11,1% no parcelado e 9,5% no cartão como um todo ([BCB, séries 21127, 21128 e 21129](https://dadosabertos.bcb.gov.br/dataset/21129-inadimplencia-da-carteira-de-credito-com-recursos-livres---pessoas-fisicas---cartao-de-credit)).
- **O problema é grande e antigo:** 81,7 milhões de brasileiros inadimplentes em fevereiro de 2026, com dívida
  média de R$ 6.598,13; 42% deles já estavam inadimplentes há dez anos ([Serasa, Mapa da Inadimplência](https://www.serasa.com.br/imprensa/10-anos-do-mapa-de-inadimplencia/)).
- **O comportamento:** o cliente não sabe quanto terá em conta no vencimento nem quanto custa cada saída em
  reais; paga o mínimo "para não sujar o nome" e cai no rotativo sem perceber.
- **Persona de referência:** Ana (C001), renda R$ 3.200, fatura R$ 1.850, R$ 610 em conta no vencimento.
  Pagando só o mínimo, a fatura sai por R$ 2.688,36; com a recomendação, R$ 2.313,26 (R$ 375,10 a menos).

## 3. Público
- **Primário:** clientes com saldo previsto menor que a fatura na janela de aviso. Na base sintética: 31 de 200
  clientes (15,5%) numa janela de 5 dias.
- **Prioridade 1:** o saldo não cobre nem o mínimo (13 clientes). **Prioridade 2:** uso recente do rotativo
  ou restrição de crédito (11). **Prioridade 3:** demais casos com falta de saldo (7).
- **Quem não é abordado:** quem registrou oposição aos avisos (LGPD) e quem consegue pagar o total.

## 4. Proposta de valor
Em uma frase: **no momento certo, mostrar em reais o custo de cada saída e executar a escolha com a aprovação do cliente.**
- **Proativo:** a rotina detecta o aperto antes do vencimento, sem IA e sem custo de tokens.
- **Confiável:** as contas são feitas por código, e a ação só acontece com aprovação, com os valores exatos na tela.
- **Responsável:** nunca recomenda o rotativo nem crédito novo; encaminha para humano quando nada cabe.
- **Fecha o ciclo:** mostra quanto a pessoa economizou, lembra antes da próxima fatura e liga a decisão à meta
  que ela declarou ("sair do vermelho").
- **O que NÃO é:** assistente genérico, chatbot de dicas, planejador financeiro.

## 5. Por que é bom para o banco (a pergunta "mas o rotativo não dá receita?")
- **Receita do rotativo é receita arriscada:** com 65,9% de inadimplência no rotativo contra 11,1% no
  parcelado (BCB, jul/2026), boa parte dos juros do rotativo vira provisão e custo de cobrança.
- **O teto legal limita o ganho:** desde a Lei 14.690/2023, juros e encargos do rotativo não passam de 100% da
  dívida original.
- **O parcelado mantém a receita com menos risco:** a opção recomendada ainda é crédito do banco (juros de
  parcelamento), só que numa modalidade em que o cliente consegue pagar.
- **Relacionamento:** reduz reclamação e renegociação, e aumenta a confiança no momento mais sensível do mês.
- **A validar no piloto:** margem líquida (juros menos provisão e cobrança) do grupo tratado contra o de controle.

## 6. Hipótese de impacto e indicadores

**Métrica-guia:** percentual de clientes abordados que **não entram no rotativo** no vencimento seguinte.

| Indicador | Baseline | Meta do piloto | Como medir |
|---|---|---|---|
| % de clientes com falta de saldo que entram no rotativo | medir no grupo de controle | −20% relativo | A/B com grupo de controle |
| Juros evitados por cliente abordado (R$) | 0 | média de `economia_vs_rotativo` | simulador + eventos de ação |
| Conversas com decisão tomada | — | > 60% | eventos da sessão |
| Clientes que aceitam o lembrete do mês seguinte | — | > 40% | `agendar_lembrete` |
| Inadimplência em 90 dias no grupo tratado | medir no controle | −10% relativo | acompanhamento por safra |
| Pedidos de oposição aos avisos | — | < 5% | `registrar_consentimento` |

**Desenho do piloto:** clientes com falta de saldo prevista, sorteados entre tratamento (recebem o aviso) e
controle (não recebem), por 3 ciclos de fatura. Comparar as métricas acima e a margem líquida.

**Ilustração com a base sintética (não é previsão):** os 31 clientes abordados somam R$ 11.266,68 de juros
evitados se seguirem a recomendação, cerca de R$ 363 por cliente por mês.

## 7. Narrativa problema → solução → resultado (abertura do pitch)
1. Todo mês, milhões de pessoas descobrem no vencimento que não têm o valor da fatura, pagam o mínimo e caem no
   rotativo: 436% ao ano e 66% de inadimplência.
2. O Copiloto da Fatura avisa antes, mostra em reais quanto custa cada saída e executa a escolha só com a
   aprovação do cliente, com as contas feitas por código.
3. A Ana economiza R$ 375 neste mês, recebe o aviso antes da próxima fatura, e o banco troca uma dívida que
   tende a virar inadimplência por um parcelamento que cabe no bolso.

## Observações
- **Taxas do simulador (a trocar pelas do case):** 14% ao mês no rotativo, 9% no parcelamento e 4,5% no
  crédito pessoal. As duas primeiras estão próximas das médias do BCB (15,0% e 9,3% em jul/2026). A do crédito
  pessoal está abaixo da média do não consignado (6,4% ao mês, [série 25464](https://dadosabertos.bcb.gov.br/dataset/25464-taxa-media-mensal-de-juros-das-operacoes-de-credito-com-recursos-livres---pessoas-fisicas---c)),
  o que deixa essa opção mais atraente do que no mercado.
- Trocar as taxas é uma linha em `copiloto_fatura/tools/simulador.py` (`Parametros`), mas muda todos os números:
  depois, rode `uv run pytest`, ajuste os textos esperados do eval e refaça os prints.
