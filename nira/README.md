# NIRA

Experimento de voz no M5Stack CoreS3. Este passo grava pelo microfone e manda o áudio para um backend na rede local. A OpenAI Realtime API ainda não entra, e nenhuma chave fica no firmware.

O CoreS3 não foi gravado a partir deste ambiente. O resultado de `pio run` e dos testes do backend está no final deste arquivo, quando a verificação rodou.

## O que o firmware faz

Nos primeiros 2,5 s a tela pede um toque.

- Toque: grava 3 s e toca de volta. O serial imprime quantos milissegundos a captura levou (a conta espera cerca de 3000 ms em 24 kHz).
- Sem toque, e com `include/secrets.h`: entra no Wi-Fi e envia blocos de 20 ms, PCM16 little-endian, 24 kHz, em base64.
- Sem `include/secrets.h`: só o teste de 3 s.

Mic e speaker alternam. Os buffers saem de `heap_caps_malloc` com `MALLOC_CAP_SPIRAM`.

Cada bloco é um texto:

```json
{"t":"audio","sr":24000,"n":480,"seq":1,"pcm":"<base64>"}
```

O backend responde `{"t":"ack","seq":1,"samples":480,"rms":0.0}`. A tela mostra `seq`, `ack` e `err`.

## Firmware

Na pasta `nira`:

```bash
cp include/secrets.h.example include/secrets.h
pio run
pio run -t upload
pio device monitor
```

`include/secrets.h` fica fora do git.

## Backend

O receptor só valida o quadro e devolve o ack. Não abre sessão na OpenAI.

```bash
cd nira/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn nira_backend.app:app --host 0.0.0.0 --port 8000
```

O CoreS3 precisa alcançar o IP da máquina na porta 8000. `NIRA_WS_HOST` em `secrets.h` é esse IP.

Os testes do contrato:

```bash
source .venv/bin/activate
pytest -q
```
