#pragma once

#include <stdint.h>

// Rosto desenhado na tela. Não é o vídeo 3D da referência: é a presença
// (piscar, olhar, boca) no display do CoreS3.

enum class PresenceMood : uint8_t { Listening, Thinking, Speaking, Error };

void presenceBegin();
bool presenceReady();
void presenceShow(PresenceMood mood, uint8_t mouth);
