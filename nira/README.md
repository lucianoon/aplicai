# NIRA

Experimento de voz no M5Stack CoreS3. Este passo grava pelo microfone e manda o áudio para um backend na rede local. A OpenAI Realtime API ainda não entra, e nenhuma chave fica no firmware.

## Verificação neste ambiente

`pio run` concluiu com PlatformIO espressif32 7.1.3, M5Unified 0.2.25 e WebSockets 2.7.3. O binário usa 22960 bytes de RAM (7,0%) e 517453 bytes de flash (7,9%). O perfil de memória foi `qio_qspi`, o mesmo da PSRAM quad de 8 MB descrita na ficha do CoreS3.

No backend, com o venv ativo, `pytest -q` passou 9 testes.

O CoreS3 não foi gravado daqui. Loopback, Wi-Fi e WebSocket continuam sem confirmação no aparelho. No teste de 3 s, o serial imprime a duração da captura: o esperado em 24 kHz fica perto de 3000 ms.

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
