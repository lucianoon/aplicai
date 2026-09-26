# Pitch (5 minutos) — Copiloto da Fatura

| Tempo | Bloco | Conteúdo | Quem |
|---|---|---|---|
| 0:00–0:30 | Dor | "O rotativo do cartão cobra 436% ao ano e tem 66% de inadimplência (BCB, jul/2026). 81,7 milhões de brasileiros estão inadimplentes. A porta de entrada é a fatura: no vencimento, a pessoa não sabe quanto vai ter em conta nem quanto custa cada saída, paga o mínimo e cai no rotativo." | Negócio |
| 0:30–1:00 | Jornada e momento | "Escolhemos um momento: dias antes do vencimento, para quem o saldo previsto não cobre a fatura. Na nossa base, 31 em 200, somando R$ 11,3 mil de juros evitáveis." | Negócio |
| 1:00–3:00 | Demo ao vivo | Tela de chat (`web/`), persona Ana: aviso proativo → opções em reais → "quero a recomendada" → duas aprovações com valores exatos → "economizou R$ 375,10" → lembrete agendado. Um caso de proteção: pedir a fatura do marido (bloqueado). Plano B: modo demo sem IA ou o vídeo (`docs/roteiro_demo.md`). | Tech |
| 3:00–4:00 | Arquitetura | Diagrama: orquestrador + agente de ação no ADK; contas em código; aprovação presa à cotação com vale assinado conferido pelo core; LGPD e equidade; MCP para o core; eval com Gemini 12 de 12. Frase: "o LLM conversa, o código calcula, a trava protege." | Tech |
| 4:00–5:00 | Impacto e experimento | Métrica-guia (% que não entra no rotativo no vencimento seguinte), juros evitados, A/B com grupo de controle por 3 ciclos, e a resposta para "o rotativo não dá receita?": receita com 66% de inadimplência vira provisão; o parcelado mantém receita com menos risco. | Negócio |

Regras: uma pessoa fala por bloco; ninguém lê slide; demo com fonte grande e janela única; encerrar com a frase
"a Ana economizou R$ 375 neste mês e vai ser avisada antes da próxima fatura". Números e fontes em
`docs/templates/01_proposta_de_negocio.md`.
