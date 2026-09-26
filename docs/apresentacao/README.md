# Material da apresentação

Tudo o que é preciso para apresentar em outra máquina, junto com o código.

| Arquivo | O que é |
| --- | --- |
| `guia-completo.pdf` | Guia do projeto em linguagem simples (18 páginas), versão de 23/09/2026. A versão viva fica no documento do Claude: https://claude.ai/code/artifact/64e51c3b-e255-4913-a613-b05056e001f2 |
| `prints-demo/` | 14 prints da tela de chat nos três roteiros, passo a passo, em **modo demo** (sem IA, números reais) |
| `prints-eval/` | 12 conversas reais com o `gemini-3.8-flash`, gravadas pelo `adk eval` de 23/09/2026 |

## Prints da tela (`prints-demo/`)

| Roteiro | Arquivos | Passos |
| --- | --- | --- |
| Ana, caminho feliz | `ana_01` a `ana_06` | aviso proativo → opções (recomendação e economia de R$ 375,10) → aprovação do pagamento de R$ 549 → aprovação do parcelamento do restante → resultado do mês → lembrete agendado |
| Carla, sofrimento financeiro | `carla_01` e `carla_02` | aviso sem promessa de solução → acolhimento, menor parcela e apoio humano (simulado) |
| Proteções | `protecoes_01` a `protecoes_06` | aviso → dado do marido bloqueado → ataque de texto recusado → pedido de 12x → aprovação recusada, nada executado → dados usados e não usados |

## Apresentar em outra máquina

```powershell
git clone https://github.com/lucianoon/itau-batalha-agentes.git
cd itau-batalha-agentes
$env:PYTHONUTF8 = "1"
uv sync
$env:COPILOTO_MODEL = "demo"; uv run python -m web.servidor   # sem chave e sem cota
```

Abra http://127.0.0.1:8080. Para usar o Gemini, crie o `.env` na hora com a chave do evento; a chave
nunca vai para o GitHub. O roteiro da fala está em `docs/roteiro_demo.md`.

## Refazer os prints

Os valores vêm do simulador: se as taxas mudarem, refaça os prints. Com a tela em modo demo, abra
`/?roteiro=ana`, `/?roteiro=carla` ou `/?roteiro=protecoes` (com `&pausa=3000`) e capture cada passo.
O vídeo de reserva fica fora do Git (pesado): guarde no Google Drive ou num pendrive.
