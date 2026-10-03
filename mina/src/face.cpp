#include "face.h"

#include <M5Unified.h>

namespace {

M5Canvas gCanvas(&M5.Display);
bool gReady = false;
uint32_t gLastMs = 0;

int sx(int v, int w) { return v * w / 320; }
int sy(int v, int h) { return v * h / 240; }

void drawEye(int x, int y, int rx, int ry, int lookX, int lookY, bool closed) {
  if (closed || ry < 2) {
    gCanvas.fillRoundRect(x - rx, y - 1, rx * 2, 3, 1, gCanvas.color565(40, 24, 32));
    return;
  }
  gCanvas.fillEllipse(x, y, rx, ry, gCanvas.color565(236, 244, 248));
  gCanvas.fillCircle(x + lookX, y + lookY, rx / 3, gCanvas.color565(20, 40, 70));
  gCanvas.fillCircle(x + lookX - rx / 6, y + lookY - ry / 5, 1, TFT_WHITE);
}

void drawFace(PresenceMood mood, uint8_t mouth) {
  const int w = gCanvas.width();
  const int h = gCanvas.height();
  const uint16_t bg = gCanvas.color565(6, 16, 36);
  const uint16_t grid = gCanvas.color565(12, 48, 72);
  gCanvas.fillScreen(bg);
  for (int x = 0; x < w; x += sx(14, w)) {
    gCanvas.drawFastVLine(x, 0, h, grid);
  }
  for (int y = 0; y < h; y += sy(14, h)) {
    gCanvas.drawFastHLine(0, y, w, grid);
  }

  const int cx = w / 2;
  const int cy = sy(118, h);
  const uint16_t suit = gCanvas.color565(18, 28, 42);
  const uint16_t cyan = gCanvas.color565(70, 220, 230);
  const uint16_t skin = gCanvas.color565(232, 186, 164);
  const uint16_t hair = gCanvas.color565(18, 16, 24);

  gCanvas.fillRoundRect(cx - sx(78, w), cy + sy(28, h), sx(156, w), sy(90, h), sx(24, w), suit);
  gCanvas.drawRoundRect(cx - sx(78, w), cy + sy(28, h), sx(156, w), sy(90, h), sx(24, w), cyan);
  gCanvas.fillRect(cx - sx(14, w), cy + sy(18, h), sx(28, w), sy(22, h), skin);

  gCanvas.fillEllipse(cx, cy - sy(6, h), sx(48, w), sy(56, h), skin);
  gCanvas.fillEllipse(cx, cy - sy(34, h), sx(50, w), sy(34, h), hair);
  gCanvas.fillRoundRect(cx - sx(50, w), cy - sy(24, h), sx(18, w), sy(58, h), sx(8, w), hair);
  gCanvas.fillRoundRect(cx + sx(32, w), cy - sy(24, h), sx(18, w), sy(58, h), sx(8, w), hair);
  gCanvas.drawEllipse(cx, cy - sy(6, h), sx(48, w), sy(56, h), cyan);

  const uint32_t now = millis();
  const bool blink = (now % 3400) < 130;
  const bool rest = mood != PresenceMood::Speaking && (now % 9000) > 8600;
  const bool closed = blink || rest;
  const int lookX = mood == PresenceMood::Thinking ? -sx(4, w) : 0;
  const int lookY = mood == PresenceMood::Thinking ? -sy(3, h) : 0;
  const int eyeY = cy - sy(12, h);
  const int eyeRy = closed ? 2 : sy(8, h);
  drawEye(cx - sx(16, w), eyeY, sx(11, w), eyeRy, lookX, lookY, closed);
  drawEye(cx + sx(16, w), eyeY, sx(11, w), eyeRy, lookX, lookY, closed);

  int mouthH = sy(3, h);
  if (mood == PresenceMood::Speaking) {
    mouthH = sy(3, h) + (mouth * sy(16, h)) / 255;
  }
  const int mouthY = cy + sy(18, h);
  gCanvas.fillEllipse(cx, mouthY, sx(11, w), mouthH, gCanvas.color565(120, 48, 58));
  gCanvas.drawEllipse(cx, mouthY, sx(12, w), mouthH + 1, gCanvas.color565(90, 40, 50));
}

}  // namespace

void presenceBegin() {
  gCanvas.setPsram(true);
  gCanvas.setColorDepth(16);
  gReady = gCanvas.createSprite(M5.Display.width(), M5.Display.height()) != nullptr;
  if (!gReady) {
    Serial.println("sprite do rosto nao coube na PSRAM");
  }
}

bool presenceReady() { return gReady; }

void presenceShow(PresenceMood mood, uint8_t mouth) {
  if (!gReady) {
    return;
  }
  const uint32_t now = millis();
  if (now - gLastMs < 70) {
    return;
  }
  gLastMs = now;
  drawFace(mood, mouth);
  gCanvas.pushSprite(0, 0);
}
