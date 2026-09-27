# Racional de experiência — Aplicaí

> Entregável 3. Peso: Design & Experiência (20%). Pergunta da banca: "essa solução realmente mudaria o comportamento do usuário?"

## 1. Momento de atuação
- Gatilho proativo D-5 (configurável) quando `saldo_projetado < fatura`. Antes disso é ruído; depois é tarde.
- Canal preferido do cliente (app, WhatsApp, voz). Mensagem de abertura curta, com o valor que falta e a economia.

## 2. Fluxo conversacional (3 passos, sem fricção)
1. Diagnóstico em uma frase: "vence em 5 dias, vai faltar R$ 1.240".
2. Três opções, em reais, começando pela recomendada, com "quanto economiza vs. rotativo".
3. Escolha → confirmação explícita com o valor exato → comprovante → o que muda no próximo mês.

## 3. Linguagem
- Frases curtas, sem jargão (nada de CET, Price, amortização para letramento baixo).
- Sem julgamento: nunca "você gastou demais"; sempre "aqui está a saída mais barata".
- Sempre diz o que acontece se a pessoa não fizer nada.

## 4. Acessibilidade
- Uma informação por linha; listas curtas; compatível com leitor de tela.
- Resumo em áudio para baixa visão (Live API/voz como próximo passo).
- Linguagem simples para baixa alfabetização; números arredondados na abertura.

## 5. Influência e transparência
- Recomendação explicada em uma frase ("é a mais barata que cabe no seu caixa").
- Comparação sempre contra o rotativo, que é o comportamento padrão a evitar.
- Nunca promete aprovação de crédito; nunca esconde o custo total.

## 6. Comportamento esperado do usuário
- Métrica de comportamento: escolhe parcelamento/pagamento em vez de mínimo; retorna no mês seguinte com preferência lembrada.

## 7. Situações-limite
- Angústia, agiota, nem o mínimo cabe → acolhimento e encaminhamento humano, sem executar nada.
- Pedido de dado de terceiro → recusa educada (LGPD).
- Tentativa de manipulação → recusa e volta à fatura.

## 8. Protótipo
- Link/prints do protótipo clicável (Figma/Stitch) e do `adk web` com a conversa da Ana.
