# Mina

Dispositivo de voz com IA: conversa voz a voz em tempo real usando a OpenAI Realtime API, com presença física e respostas expressivas. Experimento inicial.

## Stack

- Hardware: M5Stack CoreS3 (ESP32-S3, PSRAM, mic, speaker, tela touch)
- Firmware: PlatformIO + Arduino + M5Unified
- Conexão: Wi-Fi para áudio, BLE só para provisionamento (Wi-Fi, nome, voz, volume)
- IA: OpenAI Realtime API (WebSocket com PCM16 a 24 kHz em base64 para começar)
- Backend leve (FastAPI ou Cloudflare Worker): gera tokens efêmeros ou faz proxy do WebSocket

## Regras do projeto

- Nunca colocar API key no firmware ou no repositório.
- Buffers de áudio na PSRAM (`heap_caps_malloc` com `MALLOC_CAP_SPIRAM`).
- No CoreS3, mic e speaker dividem a mesma porta I2S: alternar com `Mic.begin`/`end` e `Speaker.begin`/`end`, sem uso simultâneo, a menos que o modo duplex seja validado.
- Responder e comentar em português do Brasil. Nomes de código em inglês.
- Não afirmar que algo funciona sem ter compilado e testado no dispositivo. Medir latência de ponta a ponta antes de otimizar.

## Roteiro

- [código pronto, falta testar no dispositivo] Hello hardware: gravar 3 s pelo mic e reproduzir no speaker (`src/main.cpp`, toque na tela nos 2,5 s iniciais)
- [código pronto, falta testar no dispositivo] Wi-Fi + WebSocket: conectar ao backend e enviar áudio do mic em chunks de 20 ms (PCM16 24 kHz em base64)
- [código pronto, falta testar no dispositivo] Sessão Realtime: `session.update` (voz, instruções, VAD do servidor) e reprodução com buffer circular
- [código pronto, falta testar no dispositivo] Interrupção por toque: para o speaker, esvazia o buffer e manda `{"t":"cancel"}`. O microfone continua desligado durante a fala, porque o I2S é half-duplex. O serial imprime a espera entre o `speech_stopped` do servidor e o primeiro áudio; isso não inclui o caminho do mic até o VAD.
- [código pronto, falta testar no dispositivo] Expressividade: rosto na tela que pisca, olha e abre a boca com o áudio. O alvo visual é o rosto animado do post da Sophia; isto ainda é desenho 2D, não o vídeo 3D.
- BLE de provisionamento e persistência em NVS
- [parcial, falta testar no dispositivo] Polimento: se o Wi-Fi cair, tenta de novo a cada 5 s. Erro do backend muda o rosto por 2,5 s. A espera até o primeiro áudio sai no serial. Falta a latência acústica de ponta a ponta.

## Comandos

- Simulador no computador (não é o CoreS3): `cd mina/sim && PYTHONPATH=../backend:. python -m mina_sim` e abrir `http://127.0.0.1:8765`
- Build: `pio run`
- Upload: `pio run -t upload`
- Monitor serial: `pio device monitor`

## Armadilhas conhecidas

- Eco: o mic captando o speaker causa auto-interrupção. Ajustar ganho ou usar cancelação de eco do codec.
- Latência: medir do fim da fala até o primeiro áudio de resposta.
