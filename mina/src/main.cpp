// Mina — hello de hardware, envio do microfone e reprodução da resposta.
//
// Sem include/secrets.h o aparelho só faz o loopback de 3 s.
// Com secrets.h, os primeiros 2,5 s aceitam um toque para o loopback;
// sem toque, conecta no Wi-Fi e manda PCM16 24 kHz em blocos de 20 ms.
// Quadros {"t":"play"} entram num buffer circular e saem no speaker.
// Mic e speaker do CoreS3 dividem o I2S: um end() antes do begin() do outro.
// Por isso a interrupção é um toque na tela, não o microfone durante a fala.
// Nada disto foi testado no dispositivo.

#include "face.h"

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
constexpr size_t kRingSamples = kSampleRateHz * 3;
constexpr size_t kInboxSlots = 6;
// O WebSockets.h do firmware fixa 15 KB. O backend parte a resposta para caber.
constexpr size_t kInboxBytes = 15 * 1024;
constexpr size_t kPcmScratchBytes = 12 * 1024;

struct CaptureSlot {
  int16_t* samples = nullptr;
  std::atomic<bool> queued{false};
  std::atomic<bool> ready{false};
};

struct InboxSlot {
  char* data = nullptr;
  size_t len = 0;
  std::atomic<bool> full{false};
};

struct SampleRing {
  int16_t* data = nullptr;
  size_t capacity = 0;
  size_t read = 0;
  size_t write = 0;
  size_t count = 0;
};

CaptureSlot gSlots[2];
InboxSlot gInbox[kInboxSlots];
SampleRing gRing;
int16_t* gPlayA = nullptr;
int16_t* gPlayB = nullptr;
bool gUsePlayA = true;
uint8_t* gPcmScratch = nullptr;
char* gFrame = nullptr;
size_t gFrameCap = 0;
WebSocketsClient gSocket;
bool gSocketReady = false;
bool gSpeaking = false;
bool gPlayEnd = false;
bool gDiscardReady = false;
bool gIgnorePlay = false;
bool gLatencyPending = false;
bool gTouchHeld = false;
char gState[16] = "ouvindo";
char gErrorReason[41] = "";
uint8_t gMouth = 0;
uint32_t gHeardMs = 0;
uint32_t gErrorUntil = 0;
uint32_t gWifiRetryMs = 0;
std::atomic<uint32_t> gAcks{0};
uint32_t gSeq = 0;
uint32_t gSendErrors = 0;
uint32_t gInboxDrops = 0;
uint32_t gPlayDrops = 0;
uint32_t gLastUiMs = 0;
uint32_t gLastMouthMs = 0;

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
    presenceShow(PresenceMood::Listening, 0);
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
    if (gSocketReady) {
      gSocket.loop();
    }
    delay(1);
  }
  M5.Mic.end();
  M5.Speaker.begin();
  M5.Speaker.setVolume(kSpeakerVolume);
}

size_t ringWrite(const int16_t* src, size_t count) {
  size_t room = gRing.capacity - gRing.count;
  if (count > room) {
    gPlayDrops += count - room;
    count = room;
  }
  for (size_t i = 0; i < count; ++i) {
    gRing.data[gRing.write] = src[i];
    gRing.write = (gRing.write + 1) % gRing.capacity;
  }
  gRing.count += count;
  return count;
}

void clearRing() {
  gRing.read = 0;
  gRing.write = 0;
  gRing.count = 0;
}

void ringRead(int16_t* dst, size_t count) {
  for (size_t i = 0; i < count; ++i) {
    dst[i] = gRing.data[gRing.read];
    gRing.read = (gRing.read + 1) % gRing.capacity;
  }
  gRing.count -= count;
}

bool extractQuoted(const char* json, size_t len, const char* key, const char** out,
                   size_t* outLen) {
  char pattern[24];
  int written = snprintf(pattern, sizeof(pattern), "\"%s\":\"", key);
  if (written < 0 || static_cast<size_t>(written) >= sizeof(pattern)) {
    return false;
  }
  size_t patternLen = static_cast<size_t>(written);
  const char* found = nullptr;
  for (size_t i = 0; i + patternLen <= len; ++i) {
    if (memcmp(json + i, pattern, patternLen) == 0) {
      found = json + i + patternLen;
      break;
    }
  }
  if (found == nullptr) {
    return false;
  }
  const char* end = found;
  const char* limit = json + len;
  while (end < limit && *end != '"') {
    ++end;
  }
  if (end >= limit) {
    return false;
  }
  *out = found;
  *outLen = static_cast<size_t>(end - found);
  return true;
}

bool sameToken(const char* text, size_t len, const char* literal) {
  size_t n = strlen(literal);
  return len == n && memcmp(text, literal, n) == 0;
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

void onWsEvent(WStype_t type, uint8_t* payload, size_t length) {
  if (type != WStype_TEXT || payload == nullptr || length == 0) {
    return;
  }
  for (auto& slot : gInbox) {
    if (slot.full.load(std::memory_order_acquire)) {
      continue;
    }
    if (length >= kInboxBytes) {
      ++gInboxDrops;
      return;
    }
    memcpy(slot.data, payload, length);
    slot.data[length] = '\0';
    slot.len = length;
    slot.full.store(true, std::memory_order_release);
    return;
  }
  ++gInboxDrops;
}

void sendReadyChunks() {
  for (auto& slot : gSlots) {
    if (!slot.ready.load(std::memory_order_acquire)) {
      continue;
    }
    if (gDiscardReady) {
      slot.ready.store(false, std::memory_order_release);
      slot.queued.store(false, std::memory_order_release);
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
  gDiscardReady = false;
}

bool micStillQueued() {
  for (auto& slot : gSlots) {
    if (slot.queued.load(std::memory_order_acquire) &&
        !slot.ready.load(std::memory_order_acquire)) {
      return true;
    }
  }
  return M5.Mic.isRecording() != 0;
}

void beginSpeaking() {
  if (gSpeaking) {
    return;
  }
  gSpeaking = true;
  uint32_t start = millis();
  while (micStillQueued() && millis() - start < 300) {
    if (gSocketReady) {
      gSocket.loop();
    }
    sendReadyChunks();
    delay(1);
  }
  useSpeaker();
  gDiscardReady = true;
  snprintf(gState, sizeof(gState), "falando");
  Serial.println("speaker: inicio da resposta");
}

void finishSpeaking() {
  gPlayEnd = false;
  gSpeaking = false;
  gDiscardReady = true;
  useMicrophone();
  M5.Mic.setBufferReleaseCallback(nullptr, onBufferRelease);
  snprintf(gState, sizeof(gState), "ouvindo");
  Serial.println("mic: volta a ouvir");
}

void dropPlayback() {
  gIgnorePlay = true;
  gLatencyPending = false;
  gMouth = 0;
  if (gRing.data != nullptr) {
    clearRing();
  }
  if (M5.Speaker.isEnabled()) {
    M5.Speaker.stop();
  }
  if (gSpeaking) {
    finishSpeaking();
  } else {
    snprintf(gState, sizeof(gState), "ouvindo");
  }
}

void interruptByTouch() {
  dropPlayback();
  if (gSocket.isConnected()) {
    gSocket.sendTXT("{\"t\":\"cancel\"}");
  }
  Serial.println("interrupcao por toque");
}

void enqueuePcm(const char* b64, size_t b64Len) {
  size_t decoded = 0;
  int rc = mbedtls_base64_decode(gPcmScratch, kPcmScratchBytes, &decoded,
                                 reinterpret_cast<const unsigned char*>(b64), b64Len);
  if (rc != 0 || decoded < 2 || (decoded % 2) != 0) {
    ++gPlayDrops;
    return;
  }
  gPlayEnd = false;
  if (!gSpeaking) {
    beginSpeaking();
  }
  ringWrite(reinterpret_cast<int16_t*>(gPcmScratch), decoded / sizeof(int16_t));
  snprintf(gState, sizeof(gState), "falando");
}

void pumpSpeaker() {
  while (gRing.count > 0 && M5.Speaker.isPlaying(0) < 2) {
    size_t count = gRing.count;
    if (count < kChunkSamples && !gPlayEnd && M5.Speaker.isPlaying(0) > 0) {
      break;
    }
    if (count > kChunkSamples) {
      count = kChunkSamples;
    }
    int16_t* dest = gUsePlayA ? gPlayA : gPlayB;
    gUsePlayA = !gUsePlayA;
    ringRead(dest, count);
    uint32_t level = rmsInt(dest, count);
    if (level > 6000) {
      level = 6000;
    }
    gMouth = static_cast<uint8_t>(level * 255 / 6000);
    if (!M5.Speaker.playRaw(dest, count, kSampleRateHz, false, 1, 0, false)) {
      ++gPlayDrops;
      break;
    }
  }
  if (gPlayEnd && gRing.count == 0 && !M5.Speaker.isPlaying()) {
    finishSpeaking();
  }
}

void handleText(const char* json, size_t len) {
  const char* type = nullptr;
  size_t typeLen = 0;
  if (!extractQuoted(json, len, "t", &type, &typeLen)) {
    return;
  }
  if (sameToken(type, typeLen, "ack")) {
    gAcks.fetch_add(1, std::memory_order_relaxed);
    return;
  }
  if (sameToken(type, typeLen, "cancelled")) {
    dropPlayback();
    return;
  }
  if (sameToken(type, typeLen, "play_end")) {
    if (gIgnorePlay) {
      return;
    }
    gPlayEnd = true;
    return;
  }
  if (sameToken(type, typeLen, "play")) {
    if (gIgnorePlay) {
      return;
    }
    const char* pcm = nullptr;
    size_t pcmLen = 0;
    if (extractQuoted(json, len, "pcm", &pcm, &pcmLen)) {
      if (gLatencyPending) {
        Serial.printf(
            "espera depois do fim de fala detectado: %lu ms\n",
            static_cast<unsigned long>(millis() - gHeardMs));
        gLatencyPending = false;
      }
      enqueuePcm(pcm, pcmLen);
    }
    return;
  }
  if (sameToken(type, typeLen, "state")) {
    const char* name = nullptr;
    size_t nameLen = 0;
    if (!extractQuoted(json, len, "name", &name, &nameLen)) {
      return;
    }
    if (sameToken(name, nameLen, "thinking")) {
      gIgnorePlay = false;
      if (!gSpeaking) {
        snprintf(gState, sizeof(gState), "pensando");
      }
      return;
    }
    if (sameToken(name, nameLen, "heard")) {
      gHeardMs = millis();
      gLatencyPending = true;
    }
    return;
  }
  if (sameToken(type, typeLen, "error")) {
    const char* reason = nullptr;
    size_t reasonLen = 0;
    if (extractQuoted(json, len, "reason", &reason, &reasonLen) && reasonLen > 0) {
      size_t copy = reasonLen < sizeof(gErrorReason) - 1 ? reasonLen : sizeof(gErrorReason) - 1;
      memcpy(gErrorReason, reason, copy);
      gErrorReason[copy] = '\0';
    } else {
      snprintf(gErrorReason, sizeof(gErrorReason), "erro");
    }
    gErrorUntil = millis() + 2500;
    Serial.printf("erro do backend: %s\n", gErrorReason);
  }
}

void drainInbox() {
  for (auto& slot : gInbox) {
    if (!slot.full.load(std::memory_order_acquire)) {
      continue;
    }
    handleText(slot.data, slot.len);
    slot.full.store(false, std::memory_order_release);
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

PresenceMood currentMood() {
  if (millis() < gErrorUntil) {
    return PresenceMood::Error;
  }
  if (!gSocketReady || !gSocket.isConnected()) {
    return PresenceMood::Thinking;
  }
  if (strcmp(gState, "falando") == 0 || gSpeaking) {
    return PresenceMood::Speaking;
  }
  if (strcmp(gState, "pensando") == 0) {
    return PresenceMood::Thinking;
  }
  return PresenceMood::Listening;
}

void refreshStreamUi() {
  const uint32_t now = millis();
  if (now - gLastMouthMs >= 40) {
    gLastMouthMs = now;
    if (gMouth > 28) {
      gMouth -= 28;
    } else {
      gMouth = 0;
    }
  }
  if (presenceReady()) {
    presenceShow(currentMood(), gMouth);
  } else if (!gSocket.isConnected()) {
    showScreen("socket caiu", gState, TFT_RED);
  }
  if (now - gLastUiMs < 2000) {
    return;
  }
  gLastUiMs = now;
  Serial.printf("estado %s seq %lu fila %u err %lu\n", gState,
                static_cast<unsigned long>(gSeq), static_cast<unsigned>(gRing.count),
                static_cast<unsigned long>(gSendErrors + gInboxDrops + gPlayDrops));
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

void keepWifi() {
#if MINA_HAS_SECRETS
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  const uint32_t now = millis();
  if (now - gWifiRetryMs < 5000) {
    return;
  }
  gWifiRetryMs = now;
  Serial.println("Wi-Fi caiu, reconectando");
  WiFi.reconnect();
#endif
}

void connectSocket() {
#if MINA_HAS_SECRETS
  gSocket.begin(MINA_WS_HOST, MINA_WS_PORT, MINA_WS_PATH);
  gSocket.onEvent(onWsEvent);
  gSocket.setReconnectInterval(3000);
  gSocketReady = true;
  Serial.printf("WebSocket ws://%s:%d%s\n", MINA_WS_HOST, MINA_WS_PORT, MINA_WS_PATH);
#endif
}

bool allocStreamBuffers() {
  const size_t pcmBytes = kChunkSamples * sizeof(int16_t);
  const size_t b64Bytes = 4 * ((pcmBytes + 2) / 3) + 4;
  gFrameCap = 96 + b64Bytes;
  gFrame = static_cast<char*>(allocPsram(gFrameCap));
  gRing.data = static_cast<int16_t*>(allocPsram(kRingSamples * sizeof(int16_t)));
  gRing.capacity = kRingSamples;
  gPlayA = static_cast<int16_t*>(allocPsram(pcmBytes));
  gPlayB = static_cast<int16_t*>(allocPsram(pcmBytes));
  gPcmScratch = static_cast<uint8_t*>(allocPsram(kPcmScratchBytes));
  if (gFrame == nullptr || gRing.data == nullptr || gPlayA == nullptr || gPlayB == nullptr ||
      gPcmScratch == nullptr) {
    return false;
  }
  for (auto& slot : gSlots) {
    slot.samples = static_cast<int16_t*>(allocPsram(pcmBytes));
    if (slot.samples == nullptr) {
      return false;
    }
    memset(slot.samples, 0, pcmBytes);
  }
  for (auto& slot : gInbox) {
    slot.data = static_cast<char*>(allocPsram(kInboxBytes));
    if (slot.data == nullptr) {
      return false;
    }
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
    presenceShow(PresenceMood::Listening, 0);
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

    useSpeaker();
    M5.Speaker.playRaw(buffer, kLoopbackSamples, kSampleRateHz, false, 1, 0);
    while (M5.Speaker.isPlaying()) {
      M5.update();
      if (M5.Touch.getCount() > 0) {
        M5.Speaker.stop();
        Serial.println("loopback interrompido por toque");
        break;
      }
      const uint8_t pulse = 70 + static_cast<uint8_t>((millis() / 90) % 2) * 150;
      presenceShow(PresenceMood::Speaking, pulse);
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
    const bool touched = M5.Touch.getCount() > 0;
    if (touched && !gTouchHeld && (gSpeaking || strcmp(gState, "pensando") == 0)) {
      interruptByTouch();
    }
    gTouchHeld = touched;
    keepWifi();
    gSocket.loop();
    drainInbox();
    if (gSpeaking) {
      pumpSpeaker();
    } else {
      sendReadyChunks();
      queueEmptySlots();
    }
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
  presenceBegin();

  if (chooseLoopback()) {
    runLoopback();
  }
  runStream();
}

void loop() {}
