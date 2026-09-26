# Business Case & Análise Empírica de Dados (BigQuery)

> **Estudo de Viabilidade Econômica, Análise de Comportamento Transacional & Unit Economics**  
> **Fonte Primária de Dados:** BigQuery `batalha-time-09-nciv.hackathon_dados.extrato_sintetico`  
> **Volume Analisado:** 467.585 transações bancárias | 1.000 clientes correntistas  
> **Período Histórico:** Ciclos completos de 2024 e 2025

---

## 1. O Diagnóstico Empírico da Base Itaú

Ao realizarmos a Análise Exploratória de Dados (EDA) na base oficial da Batalha de Agentes, desmistificamos a premissa de que "clientes bancários só precisam de dicas genéricas de educação financeira". Os dados revelam duas realidades estruturais:

### 1.1 O Abismo da Liquidez Ociosa (R$ 13,48 Milhões a 0%)
- **298 clientes (29,8% da base)** mantêm sistematicamente saldos médios em conta corrente superiores a **R$ 20.000,00**, com pico de até R$ 38.250,00.
- Esse capital ocioso não está aplicado em nenhuma modalidade de investimento, rendendo **0% ao mês**.
- **O Custo de Oportunidade do Cliente:** Com o CDI a ~10,75% a.a., um saldo médio de R$ 25.000,00 deixa de render aproximadamente **R$ 180 a R$ 210 líquidos por mês** (mais de R$ 2.400 ao ano por cliente).
- **A Oportunidade para o Itaú:** Ao oferecer o *Cash Sweeper* automatizado com resgate D+0, o Itaú converte depósitos à vista não fidelizados em captação líquida estável de **CDB e LCI/LCA**, aumentando o *Share of Wallet* e a retenção frente a fintechs concorrentes.

### 1.2 O Ciclo Destrutivo do Crédito Rotativo (R$ 541 Mil em Juros)
- **493 clientes (49,3% da base)** apresentam déficit orçamentário mensal recorrente (média de -R$ 1.736,00/mês).
- **689 clientes (68,9%)** recorreram a pagamentos mínimos ou parciais de fatura em 2025, caindo no crédito rotativo (taxa média de 14,9% ao mês ou 436% ao ano).
- **R$ 541.280,00** foram pagos exclusivamente em encargos e juros de cheque especial e rotativo por esse grupo.
- **A Descoberta do "Gatilho do Dia 8":** Mais de 70% dos clientes que entraram no rotativo possuem débitos automáticos fixos de **Financiamento Habitacional / Imobiliário (~R$ 2.845,00)** agendados para o **dia 8** do mês. O descasamento entre o pagamento do financiamento no início do mês e o fechamento da fatura no final do mês consome a liquidez, empurrando o correntista para a inadimplência.

---

## 2. A Tese Econômica: Por que o Banco Ganha Apoiando o Cliente?

Uma dúvida recorrente em comitês executivos de risco é: *"Se o banco lucra com juros de rotativo (14,9% a.m.), por que deveríamos implementar um agente que evita que o cliente caia nele?"*.

A resposta baseia-se na matemática atuarial de risco de crédito:

### 2.1 Receita Ilusória vs. Provisão para Devedores Duvidosos (PDD / PCLD)
- De acordo com dados públicos do Banco Central do Brasil (séries 21127 e 21129), a **inadimplência do crédito rotativo de pessoa física supera 65%**.
- Isso significa que a maior parte dos juros contabilizados no rotativo jamais é efetivamente paga; ela se transforma em **inadimplência grave, custo de cobrança judicial e baixa a prejuízo (write-off)**, obrigando o banco a aumentar sua Provisão para Créditos de Liquidação Duvidosa (PCLD).
- Desde a Lei 14.690/2023, os juros totais do rotativo estão limitados a 100% da dívida original, eliminando a antiga tese de juros infinitos.

### 2.2 Troca Eficiente de Carteira: De Dívida Podre para Crédito Saudável
- Ao intervir preventivamente no **Dia D-5** da fatura, o agente propõe o **Parcelamento Protegido da Fatura** (taxas reduzidas de 1,99% a 3,5% a.m.).
- **Resultado para o Cliente:** Economia média de **R$ 375,10 em juros por ciclo**, com parcelas fixas que cabem no fluxo de caixa.
- **Resultado para o Banco:** A inadimplência na modalidade de fatura parcelada cai para **11,1%** (redução de 83% no risco de calote). O banco preserva a margem financeira líquida, reduz provisões contábeis e fideliza o cliente por todo o ciclo de vida.

---

## 3. Unit Economics & Projeção de Escala

Considerando a base do piloto e extrapolando para 100.000 correntistas Itaú:

| Métrica | Base Atual (Sem Agente) | Projeção com Agente (Piloto 100k) | Impacto Anual Projetado |
| :--- | :--- | :--- | :--- |
| **Captação Nova em CDB (Sweeper)** | R$ 0,00 | R$ 380 Milhões aplicados | +R$ 15,2 Mi em Margem Financeira Líquida |
| **Clientes em Rotativo no Ciclo** | 49.300 clientes (49,3%) | 29.500 clientes (-40%) | -19.800 clientes em risco |
| **Perda com PDD / Write-off de Cartões** | R$ 42,0 Milhões | R$ 26,5 Milhões | **Economia de R$ 15,5 Milhões em PDD** |
| **Custo de Operação da IA (Inferência Gemini)** | R$ 0,00 | R$ 0,0018 por cliente/mês | R$ 216.000 / ano (ROI > 140x) |

---

## 4. Indicadores de Sucesso do Piloto (KPIs)

1. **Taxa de Conversão do Smart Card Sweeper:** Meta $> 35\%$ de adesão à aplicação no primeiro toque.
2. **Índice de Evasão do Rotativo:** Redução relativa de $\ge 25\%$ no volume de clientes que caem no rotativo após notificação do agente.
3. **Respeito ao Colchão de Liquidez:** Zero ocorrências de clientes que aplicaram via Sweeper e tiveram débitos essenciais devolvidos por insuficiência de fundos nos 30 dias subsequentes.
4. **Satisfação e Acolhimento (CSAT / NPS Transacional):** Score $> 85$ na avaliação de clareza e transparência das simulações financeiras.
