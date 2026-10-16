#include <Arduino.h>
#include "Config.h"
#include "ControlThePump.h"

#define BUTTON_PIN 13   // 本地按钮（可选）
#define RELAY_PIN  26   // 水泵继电器控制脚

// 触发电平由 Config.h 里的 RELAY_ACTIVE_LOW 决定
#if RELAY_ACTIVE_LOW
#define RELAY_ON   LOW
#define RELAY_OFF  HIGH
#else
#define RELAY_ON   HIGH
#define RELAY_OFF  LOW
#endif

static bool pumpState = false;              // 水泵实际状态：true=开
static bool lastButtonReading = HIGH;       // 上一次读取到的按键状态
static bool stableButtonState = HIGH;       // 去抖后的稳定按键状态
static unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 50;

void ControlThePump_Init()
{
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    pinMode(RELAY_PIN, OUTPUT);
    digitalWrite(RELAY_PIN, RELAY_OFF);     // 开机默认关闭水泵
    Serial.println("[水泵] 初始化完成，默认关闭");
}

// MQTT 指令入口：true 开水泵，false 关水泵
void ControlThePump_Set(bool on)
{
    if (pumpState == on)
    {
        return;
    }
    pumpState = on;
    digitalWrite(RELAY_PIN, pumpState ? RELAY_ON : RELAY_OFF);
    Serial.println(pumpState ? "[水泵] ON" : "[水泵] OFF");
}

bool ControlThePump_GetState()
{
    return pumpState;
}

// 本地按钮控制（含消抖），主循环调用
void ControlThePump()
{
    bool buttonReading = digitalRead(BUTTON_PIN);

    if (buttonReading != lastButtonReading)
    {
        lastDebounceTime = millis();
    }

    if (millis() - lastDebounceTime > debounceDelay)
    {
        if (buttonReading != stableButtonState)
        {
            stableButtonState = buttonReading;

            if (stableButtonState == LOW)
            {
                ControlThePump_Set(!pumpState);
            }
        }
    }

    lastButtonReading = buttonReading;
}
