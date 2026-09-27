# Roteiro da demo e do vídeo de reserva

A demo usa a tela de chat em `web/`. Ela funciona com o Gemini ou, como plano B, com o **modo demo**:
um roteiro sem IA, sem internet e sem cota, em que guardrails, aprovação, core e auditoria rodam de verdade
e os números vêm das mesmas ferramentas. Só a "inteligência" é trocada por regras fixas.

## Subir a tela

```powershell
$env:PYTHONUTF8 = "1"
uv run python -m web.servidor                                   # com o Gemini do .env
$env:COPILOTO_MODEL = "demo"; uv run python -m web.servidor     # plano B, sem IA
```

Abra http://127.0.0.1:8080. O selo no alto mostra qual modelo está respondendo. O botão
**Reiniciar demo** volta faturas, consentimentos e lembretes ao estado inicial; use antes de cada ensaio.

## Roteiro ao vivo (2 minutos)

1. Clique em **Ana · C001**. Aparece o aviso proativo: "sua fatura vence em 5 dias e vai faltar uns R$ 1.240".
   Fale: "a conversa começa antes do problema, pela rotina que roda sem IA".
2. Clique em **Quero ver as opções**. Mostre a recomendação (pagar R$ 549,00 agora e parcelar o resto em 6x de
   R$ 294,04), a economia de R$ 375,10 e o custo do rotativo. Fale: "todos os números são calculados por código".
3. Clique em **Quero a recomendada**. Aparece o cartão de aprovação com o valor exato. Fale: "escrever sim no chat
   não autoriza nada; só o botão, e a cotação é conferida de novo pelo banco". Aprove o pagamento e o parcelamento.
4. Mostre o resultado do mês: economia de R$ 375,10 e compromisso de R$ 294,04 por mês.
5. Clique em **Me avisa 5 dias antes**. Fale: "o ciclo fecha: no mês que vem ela é avisada de novo".
6. Proteção (se houver tempo): **Me mostra a fatura do C002** é bloqueado por LGPD.

Se a IA ou a internet falharem no meio, troque para o modo demo (reinicie o servidor com `COPILOTO_MODEL=demo`)
ou rode o vídeo.

## Reprodução automática e vídeo de reserva

A tela toca o roteiro sozinha, com pausas, clicando em Aprovar quando precisa:

- http://127.0.0.1:8080/?roteiro=ana — caminho feliz completo
- http://127.0.0.1:8080/?roteiro=carla — sofrimento financeiro e apoio humano
- http://127.0.0.1:8080/?roteiro=protecoes — dado de terceiro, ataque de texto, recusa da aprovação e direitos do titular

Use `&pausa=2500` para deixar mais lento. Para o vídeo: modo demo, **Reiniciar demo**, abra o link do roteiro e grave
a janela (no Windows, `Win+Alt+R` pela Barra de Jogo ou a Ferramenta de Captura). Grave os três roteiros.

## Checklist antes de apresentar

- [ ] `uv run pytest` passando (sem IA)
- [ ] Tela aberta em modo demo e com o Gemini; **Reiniciar demo** antes de começar
- [ ] Zoom do navegador em 125% ou mais, janela única
- [ ] Vídeo dos três roteiros salvo localmente
- [ ] Se usar o Gemini: saldo de cota conferido (cada conversa gasta cerca de 8 mil tokens)
