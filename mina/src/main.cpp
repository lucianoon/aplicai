// Mina — hello de hardware e envio do microfone por WebSocket.
//
// Sem include/secrets.h o aparelho só faz o loopback de 3 s.
// Com secrets.h, os primeiros 2,5 s aceitam um toque para o loopback;
// sem toque, conecta no Wi-Fi e manda PCM16 24 kHz em blocos de 20 ms.
//
// Mic e speaker do CoreS3 dividem o I2S: um end() antes do begin() do outro.
// Nada disto foi testado no dispositivo.

#include <M5Unified.h>
#include <WebSocketsClient.h>
#include <WiFi.h>
#include <esp_heap_caps.h>
#include <mbedtls/base64.h>

#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstring>

#if __has_include("secrets.h")
#include "secrets.h"
#define MINA_HAS_SECRETS 1
#else
#define MINA_HAS_SECRETS 0
#endif

namespace {

constexpr uint32_t kSampleRateHz = 24000;
constexpr uint32_t kChunkMs = 20;
constexpr size_t kChunkSamples = (kSampleRateHz * kChunkMs) / 1000;  // 480
constexpr uint32_t kLoopbackMs = 3000;
constexpr size_t kLoopbackSamples = (kSampleRateHz * kLoopbackMs) / 1000;
constexpr uint32_t kBootChoiceMs = 2500;
constexpr int kSpeakerVolume = 100;

struct CaptureSlot {
  int16_t* samples = nullptr;
  std::atomic<bool> queued{false};
  std::atomic<bool> ready{false};
};

CaptureSlot gSlots[2];
char* gFrame = nullptr;
size_t gFrameCap = 0;
WebSocketsClient gSocket;
std::atomic<uint32_t> gAcks{0};
uint32_t gSeq = 0;
uint32_t gSendErrors = 0;
uint32_t gLastUiMs = 0;

void* allocPsram(size_t bytes) {
  return heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
}

void showScreen(const char* line1, const char* line2, uint16_t accent) {
  M5.Display.fillScreen(TFT_BLACK);
  M5.Display.setCursor(8, 16);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.setTextSize(3);
  M5.Display.println("Mina");
  M5.Display.setTextSize(2);
  M5.Display.setTextColor(accent, TFT_BLACK);
  M5.Display.println(line1);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.println(line2);
}

void onBufferRelease(void* /*args*/, void* data, size_t /*length*/) {
  for (auto& slot : gSlots) {
    if (slot.samples == data) {
      slot.ready.store(true, std::memory_order_release);
      return;
    }
  }
}

bool recordBlocking(int16_t* data, size_t samples, uint32_t rateHz) {
  if (!M5.Mic.record(data, samples, rateHz, false)) {
    return false;
  }
  while (M5.Mic.isRecording()) {
    M5.update();
    delay(1);
  }
  return true;
}

void useMicrophone() {
  if (M5.Speaker.isEnabled()) {
    M5.Speaker.end();
  }
  M5.Mic.begin();
}

void useSpeaker() {
  while (M5.Mic.isRecording()) {
    delay(1);
  }
  M5.Mic.end();
  M5.Speaker.begin();
  M5.Speaker.setVolume(kSpeakerVolume);
}

uint32_t rmsInt(const int16_t* samples, size_t count) {
  if (count == 0) {
    return 0;
  }
  uint64_t acc = 0;
  for (size_t i = 0; i < count; ++i) {
    int32_t sample = samples[i];
    acc += static_cast<uint64_t>(sample * sample);
  }
  return static_cast<uint32_t>(sqrt(static_cast<double>(acc / count)));
}

// O texto tem de bater com build_audio_frame() em mina/backend.
bool buildFrame(const int16_t* samples, size_t count, uint32_t seq, size_t* outLen) {
  int header = snprintf(gFrame, gFrameCap,
                        "{\"t\":\"audio\",\"sr\":%u,\"n\":%u,\"seq\":%u,\"pcm\":\"",
                        static_cast<unsigned>(kSampleRateHz),
                        static_cast<unsigned>(count), seq);
  if (header < 0 || static_cast<size_t>(header) >= gFrameCap) {
    return false;
  }

  size_t encoded = 0;
  int rc = mbedtls_base64_encode(reinterpret_cast<unsigned char*>(gFrame + header),
                                 gFrameCap - static_cast<size_t>(header) - 3, &encoded,
                                 reinterpret_cast<const unsigned char*>(samples),
                                 count * sizeof(int16_t));
  if (rc != 0) {
    return false;
  }

  size_t end = static_cast<size_t>(header) + encoded;
  if (end + 3 > gFrameCap) {
    return false;
  }
  gFrame[end] = '"';
  gFrame[end + 1] = '}';
  gFrame[end + 2] = '\0';
  *outLen = end + 2;
  return true;
}

bool payloadHasAck(const uint8_t* payload, size_t length) {
  static constexpr char kNeedle[] = "\"t\":\"ack\"";
  constexpr size_t n = sizeof(kNeedle) - 1;
  if (payload == nullptr || length < n) {
    return false;
  }
  for (size_t i = 0; i + n <= length; ++i) {
    if (memcmp(payload + i, kNeedle, n) == 0) {
      return true;
    }
  }
  return false;
}

void onWsEvent(WStype_t type, uint8_t* payload, size_t length) {
  if (type == WStype_TEXT && payloadHasAck(payload, length)) {
    gAcks.fetch_add(1, std::memory_order_relaxed);
  }
}

void sendReadyChunks() {
  for (auto& slot : gSlots) {
    if (!slot.ready.load(std::memory_order_acquire)) {
      continue;
    }
    size_t frameLen = 0;
    bool built = buildFrame(slot.samples, kChunkSamples, ++gSeq, &frameLen);
    bool sent = false;
    if (built && gSocket.isConnected()) {
      sent = gSocket.sendTXT(gFrame, frameLen);
    }
    if (!sent) {
      ++gSendErrors;
    }
    slot.ready.store(false, std::memory_order_release);
    slot.queued.store(false, std::memory_order_release);
  }
}

void queueEmptySlots() {
  if (!gSocket.isConnected()) {
    return;
  }
  for (auto& slot : gSlots) {
    if (slot.queued.load(std::memory_order_acquire)) {
      continue;
    }
    if (M5.Mic.record(slot.samples, kChunkSamples, kSampleRateHz, false)) {
      slot.queued.store(true, std::memory_order_release);
    }
  }
}

void refreshStreamUi() {
  uint32_t now = millis();
  if (now - gLastUiMs < 500) {
    return;
  }
  gLastUiMs = now;
  char line1[48];
  char line2[64];
  const bool up = gSocket.isConnected();
  snprintf(line1, sizeof(line1), "%s", up ? "ouvindo" : "socket caiu");
  snprintf(line2, sizeof(line2), "seq %lu  ack %lu  err %lu",
           static_cast<unsigned long>(gSeq),
           static_cast<unsigned long>(gAcks.load(std::memory_order_relaxed)),
           static_cast<unsigned long>(gSendErrors));
  showScreen(line1, line2, up ? TFT_GREEN : TFT_RED);
}

bool connectWifi() {
#if !MINA_HAS_SECRETS
  return false;
#else
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(MINA_WIFI_SSID, MINA_WIFI_PASSWORD);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    M5.update();
    showScreen("conectando wi-fi", MINA_WIFI_SSID, TFT_YELLOW);
    delay(200);
  }
  if (WiFi.status() != WL_CONNECTED) {
    showScreen("wi-fi falhou", "nova tentativa", TFT_RED);
    Serial.println("Wi-Fi sem conexao");
    return false;
  }
  Serial.print("Wi-Fi ");
  Serial.println(WiFi.localIP());
  showScreen("wi-fi ok", WiFi.localIP().toString().c_str(), TFT_GREEN);
  return true;
#endif
}

void connectSocket() {
#if MINA_HAS_SECRETS
  gSocket.begin(MINA_WS_HOST, MINA_WS_PORT, MINA_WS_PATH);
  gSocket.onEvent(onWsEvent);
  gSocket.setReconnectInterval(3000);
  Serial.printf("WebSocket ws://%s:%d%s\n", MINA_WS_HOST, MINA_WS_PORT, MINA_WS_PATH);
#endif
}

bool allocStreamBuffers() {
  const size_t pcmBytes = kChunkSamples * sizeof(int16_t);
  const size_t b64Bytes = 4 * ((pcmBytes + 2) / 3) + 4;
  gFrameCap = 96 + b64Bytes;
  gFrame = static_cast<char*>(allocPsram(gFrameCap));
  if (gFrame == nullptr) {
    return false;
  }
  for (auto& slot : gSlots) {
    slot.samples = static_cast<int16_t*>(allocPsram(pcmBytes));
    if (slot.samples == nullptr) {
      return false;
    }
    memset(slot.samples, 0, pcmBytes);
  }
  return true;
}

void runLoopback() {
  int16_t* buffer = static_cast<int16_t*>(allocPsram(kLoopbackSamples * sizeof(int16_t)));
  if (buffer == nullptr) {
    showScreen("sem PSRAM", "loopback parado", TFT_RED);
    Serial.println("heap_caps_malloc do loopback falhou");
    while (true) {
      delay(1000);
    }
  }

  useMicrophone();
  while (true) {
    M5.update();
    showScreen("gravando 3 s", "mic", TFT_RED);
    uint32_t started = millis();
    bool ok = recordBlocking(buffer, kLoopbackSamples, kSampleRateHz);
    uint32_t elapsed = millis() - started;
    Serial.printf("loopback: %u amostras em %lu ms (esperado ~%lu ms), rms %lu, ok %d\n",
                  static_cast<unsigned>(kLoopbackSamples),
                  static_cast<unsigned long>(elapsed),
                  static_cast<unsigned long>(kLoopbackMs),
                  static_cast<unsigned long>(rmsInt(buffer, kLoopbackSamples)), ok);
    if (!ok) {
      showScreen("mic falhou", "nova tentativa", TFT_RED);
      delay(1000);
      continue;
    }

    showScreen("tocando 3 s", "speaker", TFT_CYAN);
    useSpeaker();
    M5.Speaker.playRaw(buffer, kLoopbackSamples, kSampleRateHz, false, 1, 0);
    while (M5.Speaker.isPlaying()) {
      M5.update();
      delay(1);
    }
    useMicrophone();
    delay(400);
  }
}

bool chooseLoopback() {
#if !MINA_HAS_SECRETS
  showScreen("sem secrets.h", "so o teste do mic", TFT_YELLOW);
  Serial.println("include/secrets.h ausente: loopback de 3 s");
  delay(1200);
  return true;
#else
  uint32_t start = millis();
  while (millis() - start < kBootChoiceMs) {
    M5.update();
    showScreen("toque = teste mic", "ou espere o stream", TFT_YELLOW);
    if (M5.Touch.getCount() > 0) {
      Serial.println("toque: loopback de 3 s");
      return true;
    }
    delay(20);
  }
  return false;
#endif
}

void runStream() {
  if (!allocStreamBuffers()) {
    showScreen("sem PSRAM", "stream parado", TFT_RED);
    Serial.println("heap_caps_malloc do stream falhou");
    while (true) {
      delay(1000);
    }
  }

  while (!connectWifi()) {
    delay(2000);
  }
  connectSocket();
  useMicrophone();
  // O callback só pode ser registrado antes do primeiro record().
  M5.Mic.setBufferReleaseCallback(nullptr, onBufferRelease);

  Serial.printf("stream: %u Hz, %u ms, %u amostras, PCM16 LE base64\n",
                static_cast<unsigned>(kSampleRateHz), static_cast<unsigned>(kChunkMs),
                static_cast<unsigned>(kChunkSamples));

  while (true) {
    M5.update();
    gSocket.loop();
    sendReadyChunks();
    queueEmptySlots();
    refreshStreamUi();
  }
}

}  // namespace

void setup() {
  auto cfg = M5.config();
  cfg.clear_display = true;
  M5.begin(cfg);
  Serial.begin(115200);
  M5.Display.setRotation(1);
  M5.Display.setTextWrap(false);

  if (!psramFound()) {
    showScreen("PSRAM ausente", "firmware parado", TFT_RED);
    Serial.println("psramFound() == false");
    while (true) {
      delay(1000);
    }
  }
  Serial.printf("PSRAM livre: %u bytes\n",
                static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)));

  if (chooseLoopback()) {
    runLoopback();
  }
  runStream();
}

void loop() {}
