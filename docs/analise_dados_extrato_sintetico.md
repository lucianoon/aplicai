# Análise dos Dados: `hackathon_dados.extrato_sintetico`
**Batalha de Agentes Itaú + Google** | Projeto: `batalha-time-09-nciv` (Time 09)

Este documento consolida a análise exploratória de dados (EDA), métricas de negócio e a integração técnica realizada com a tabela oficial de extratos fornecida para o hackathon.

---

## 1. Visão Geral da Base

A tabela `hackathon_dados.extrato_sintetico` no BigQuery contém o histórico anual completo de 2025 para uma coorte representativa de correntistas:

* **Tabela BigQuery**: `batalha-time-09-nciv.hackathon_dados.extrato_sintetico`
* **Total de Transações**: **467.585**
* **Clientes Únicos (`id_usuario`)**: **1.000 clientes**
* **Média de Transações**: ~467 transações/cliente/ano (~39 transações/mês por cliente)
* **Período**: 01/01/2025 a 31/12/2025 (12 meses completos)
* **Volume Financeiro Total**: **R$ 202.896.226,42** (~R$ 202,9 milhões)
* **Qualidade dos Dados**: 100% íntegro (zero nulos em datas, valores, descrições, categorias e saldos)

---

## 2. Balanço Financeiro Geral

| Tipo de Movimentação | Qtd. Transações | % Volume de Transações | Volume Financeiro (R$) | Ticket Médio |
| :--- | :--- | :--- | :--- | :--- |
| **Saídas (`S`)** | 432.508 | 92,5% | R$ 101.608.829,73 | R$ 234,93 |
| **Entradas (`E`)** | 35.077 | 7,5% | R$ 101.287.396,69 | R$ 2.887,57 |
| **Total** | **467.585** | **100,0%** | **R$ 202.896.226,42** | **R$ 433,92** |

> **Insight de Negócio**: Embora o sistema agregado aparente equilíbrio (entradas quase empatando com saídas), a análise a nível de indivíduo revela profunda assimetria e vulnerabilidade financeira.

---

## 3. Diagnóstico de Saúde Financeira dos Clientes

Para a jornada do **Aplicaí**, o comportamento individual de caixa é o fator determinante para prevenir o inadimplemento e a rolagem no rotativo:

### 3.1 Perfil de Renda Mensal
* **Renda Média Mensal**: **R$ 8.440,62**
* **Renda Mínima**: R$ 4.058,99
* **Renda Máxima**: R$ 13.065,87
* **Faixas**:
  * 25,5% dos clientes (255) recebem entre R$ 3.000 e R$ 7.000/mês
  * 74,5% dos clientes (745) recebem entre R$ 7.000 e R$ 15.000/mês

### 3.2 Déficit Orçamentário e Superendividamento
* **493 clientes (49,3%)** apresentam balanço deficitário médio (gastam mais do que ganham mensalmente).
* **327 clientes (32,7%)** entraram no **saldo negativo (cheque especial)** ao longo de 2025.
* **56.141 transações** ocorreram com saldo devedor.
* O pior saldo individual negativo atingiu **-R$ 42.649,81**.

---

## 4. Decomposição de Gastos e Receitas

### 4.1 Principais Gastos (Saídas)
1. **Empréstimos e Financiamentos**: R$ 24,96M (destaque para *Financiamento de imóvel*: R$ 23,90M)
2. **Produtos Financeiros**: R$ 20,02M
   * *Pagamento de fatura*: R$ 18,24M (exatamente 12.000 pagamentos, 1 por mês para cada um dos 1.000 clientes)
   * Ticket médio de pagamento de fatura: **R$ 1.520,16**
3. **Casa / Moradia**: R$ 14,34M (Condomínio R$ 4,05M, Energia R$ 2,25M)
4. **Educação**: R$ 7,89M (Mensalidades escolares: R$ 7,22M)
5. **Lojas e Comércio / E-commerce**: R$ 4,81M (31.256 transações)
6. **Lazer & Entretenimento**: R$ 4,24M
7. **Veículos & Transporte**: R$ 3,51M

### 4.2 Principais Entradas
1. **Salários e Bonificações**: R$ 60,59M
   * Salário CLT: R$ 52,71M (9.600 lançamentos)
   * 13º Salário: R$ 4,39M (1.600 lançamentos)
   * Bônus PLR: R$ 3,49M (714 lançamentos)
2. **Recebimentos Diversos (PIX/Transferências)**: R$ 33,42M
3. **Rendimentos / Aluguéis**: R$ 4,13M
4. **Benefícios INSS**: R$ 3,15M

---

## 5. Dinâmica de Parcelamento e Meios de Pagamento

* **Parcelamentos**:
  * **29.847 transações** (6,38%) correspondem a compras parceladas.
  * Média de **7,24 parcelas** (máximo de 12 parcelas).
  * Concentrado exclusivamente em 4 categorias:
    * *Viagens*: ~6,7 parcelas (valor médio parcela: R$ 237,80)
    * *Casa / Móveis*: ~10,0 parcelas (valor médio parcela: R$ 295,93)
    * *Lojas e Sites*: ~6,8 parcelas (valor médio parcela: R$ 77,22)
    * *Lazer / Eletrônicos*: ~6,7 parcelas (valor médio parcela: R$ 312,26)
* **Meios de Pagamento no dia a dia**:
  * **PIX**: 161.645 transações (R$ 52,85M)
  * **Cartão de Crédito**: 131.172 transações (R$ 22,08M)
  * **Débito em Conta**: 37.974 transações (R$ 15,13M)

---

## 6. Sazonalidade Temporal (Ciclos de Caixa)

A análise mês a mês demonstra claramente a dinâmica de caixa:
* **Fevereiro e Março**: Meses de forte saldo positivo agregado (+R$ 1,28M e +R$ 966k), refletindo o pagamento de bônus e PLR.
* **Abril a Outubro**: Período de queima de caixa sustentada (saldos agregados negativos de até -R$ 895k/mês).
* **Novembro e Dezembro**: Recomposição de liquidez (+R$ 1,35M e +R$ 1,19M) decorrente do 13º salário e gratificações de fim de ano.

---

## 7. Integrações e Melhorias Implementadas

Para incorporar integralmente os dados reais ao Aplicaí:

1. **Pipeline de Carga e Sincronização (`scripts/carregar_dados_extrato_sintetico.py`)**:
   * Consulta os dados diretamente do BigQuery e consolida perfis completos dos clientes.
   * Conecta clientes reais via UUID original da base Itaú e gera alias amigável.
   * Preserva as 3 personas de demo (`C001` Ana, `C002` Bruno, `C003` Carla) para garantir estabilidade e testes automatizados.

2. **Adaptadores do BigQuery (`proativo/gcp_adapters.py`)**:
   * Adicionados métodos nativos:
     * `carregar_clientes_bigquery`: carga estruturada da tabela `hackathon_dados.extrato_sintetico`.
     * `obter_extrato_bigquery(cliente_id, limite)`: busca pontual de transações em tempo de execução.
     * `obter_kpis_globais_bigquery()`: telemetria estatística em tempo real da base.

3. **Core Bancário Híbrido (`mock_core/store.py`)**:
   * Indexação dupla: o atendente ou o cliente podem se identificar por `C001`, `C050` ou pelo UUID completo do BigQuery (ex.: `001221d1-3626-45c1-807a-990502adf808`), com resolução case-insensitive.

4. **Gatilhos Proativos Calibrados (`proativo/gatilho.py`)**:
   * A rotina de D-5 agora roda sobre a base real do BigQuery, identificando exatamente os clientes que entrarão em déficit na data de vencimento da fatura e calculando a economia real frente ao rotativo.
