#include "MyWIFI.h"
#include "Config.h"

#include <WiFi.h>
#include <WiFiMulti.h>

static WiFiMulti wifiMulti;

void MyWIFI_Init()
{
    Serial.println("[WiFi] 正在连接: " + String(WIFI_SSID));
    WiFi.mode(WIFI_STA);//把 ESP32 的 WiFi 设为工作站（Station）模式
    wifiMulti.addAP(WIFI_SSID, WIFI_PASSWORD);
}

void MyWIFI_Loop()
{
    static unsigned long lastTry = 0;      // 实际发起连接尝试的时间
    static unsigned long lastHint = 0;     // 未连接时串口提示的时间
    static bool lastState = false;         // 上一次的连接状态，用于检测变化

    bool connected = (WiFi.status() == WL_CONNECTED);//WiFi.status()   读取当前 WiFi 状态，

    // 连接状态发生变化时打印提示
    if (connected != lastState)
    {
        lastState = connected;
        if (connected)
        {
            Serial.print("[WiFi] 已连接，IP: ");
            Serial.println(WiFi.localIP());
        }
        else
        {
            Serial.println("[WiFi] 连接断开，开始自动重连...");
            lastTry = 0;
            lastHint = 0;
        }
    }

    if (connected)
    {
        return;
    }

    // 未连接时每 5 秒在串口提示一次，避免看起来像死机
    if (millis() - lastHint >= 5000)
    {
        lastHint = millis();
        Serial.println("[WiFi] 未连接，正在尝试连接 " + String(WIFI_SSID) + " ...");
    }

    // 每 3 秒实际发起一次连接尝试
    if (millis() - lastTry >= 3000)
    {
        lastTry = millis();
        if (wifiMulti.run(3000) == WL_CONNECTED)
        {
            Serial.print("[WiFi] 已连接，IP: ");
            Serial.println(WiFi.localIP());
        }
    }
}

bool MyWIFI_IsConnected()
{
    return WiFi.status() == WL_CONNECTED;
}
