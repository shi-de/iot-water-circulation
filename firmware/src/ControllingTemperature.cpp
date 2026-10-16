#include <Arduino.h>
#include "Config.h"
#include "ControllingTemperature.h"

#define RELAY_PIN  23    // 加热模块继电器控制脚

// 触发电平由 Config.h 里的 RELAY_ACTIVE_LOW 决定
#if RELAY_ACTIVE_LOW
#define RELAY_ON   LOW
#define RELAY_OFF  HIGH
#else
#define RELAY_ON   HIGH
#define RELAY_OFF  LOW
#endif

static bool heaterState = false;   // 加热实际状态：true=开

void ControllingTemperature_Init()
{
    pinMode(RELAY_PIN, OUTPUT);
    digitalWrite(RELAY_PIN, RELAY_OFF);   // 开机默认关闭加热
    Serial.println("[加热] 初始化完成，默认关闭");
}

// MQTT 指令入口：true 开加热，false 关加热
void ControllingTemperature_Set(bool on)
{
    if (heaterState == on)
    {
        return;
    }
    heaterState = on;
    digitalWrite(RELAY_PIN, heaterState ? RELAY_ON : RELAY_OFF);
    Serial.println(heaterState ? "[加热] ON" : "[加热] OFF");
}

bool ControllingTemperature_GetState()
{
    return heaterState;
}
