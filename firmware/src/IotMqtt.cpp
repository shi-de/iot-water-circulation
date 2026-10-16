#include "IotMqtt.h"
#include "Config.h"//broker IP/端口/主题/客户端 ID
#include "ControlThePump.h"
#include "ControllingTemperature.h"
#include "MyWIFI.h"

#include <PubSubClient.h>// MQTT 客户端库
#include <WiFi.h>

static WiFiClient wifiClient;//负责底层的 TCP 网络连接
static PubSubClient mqttClient(wifiClient);//把“这个 MQTT 客户端”和“这个 TCP 连接”绑在一起
static unsigned long lastReconnectTry = 0;//记录上一次尝试重连的时间（毫秒）
const unsigned long RECONNECT_INTERVAL_MS = 3000;

// ---------------- 简易 JSON 取值 ----------------
// 从 {"device":"pump","action":"on"} 里取指定 key 的字符串值
static String getJsonValue(const String &json, const char *key)
{
    String pattern = String("\"") + key + "\"";
    int keyPos = json.indexOf(pattern);//在 json 里找 pattern  返回它第一次出现的位置下标
                                       //如果失败返回-1
    if (keyPos < 0)
    {
        return "";
    }
    int colonPos = json.indexOf(':', keyPos + pattern.length());//从 pattern 结束的位置往后找冒号 :
    if (colonPos < 0)   
    {
        return "";
    }
    int q1 = json.indexOf('"', colonPos + 1);//值的起始引号。
    int q2 = json.indexOf('"', q1 + 1);//值的结束引号。
    if (q1 < 0 || q2 < 0)
    {
        return "";
    }
    return json.substring(q1 + 1, q2);
}

// ---------------- 收到后端指令 ----------------
static void onCommand(char *topic, byte *payload, unsigned int length)//MQTT 的消息回调
//payload 是消息数据的字节数组，length 是长度
{
    String msg;
    for (unsigned int i = 0; i < length; i++)
    {
        msg += (char)payload[i];
    }

    Serial.print("[MQTT] 收到指令: ");
    Serial.println(msg);

    String device = getJsonValue(msg, "device");
    String action = getJsonValue(msg, "action");
    device.toLowerCase();
    action.toLowerCase();

    if (action != "on" && action != "off")
    {
        Serial.println("[MQTT] action 无效，忽略");
        return;
    }

    bool state = (action == "on");

    if (device == "pump")
    {
        ControlThePump_Set(state);
        IotMqtt_PublishAck("pump", action.c_str(), ControlThePump_GetState(), "ok");
    }
    else if (device == "heater")
    {
        ControllingTemperature_Set(state);
        IotMqtt_PublishAck("heater", action.c_str(), ControllingTemperature_GetState(), "ok");
    }
    else
    {
        Serial.print("[MQTT] 未知设备: ");
        Serial.println(device);
        IotMqtt_PublishAck(device.c_str(), action.c_str(), false, "error:unknown_device");
    }
}

void IotMqtt_Init()
{
    mqttClient.setServer(MQTT_BROKER_IP, MQTT_PORT);
    mqttClient.setCallback(onCommand);
    Serial.println("[MQTT] 客户端初始化完成");
}

bool IotMqtt_IsConnected()
{
    return mqttClient.connected();
}

static void connectMqtt()
{
    Serial.print("[MQTT] 尝试连接 ");
    Serial.print(MQTT_BROKER_IP);
    Serial.print(":");
    Serial.println(MQTT_PORT);

    if (mqttClient.connect(MQTT_CLIENT_ID))
    {
        mqttClient.subscribe(TOPIC_CMD);
        Serial.println("[MQTT] 连接成功，已订阅 " TOPIC_CMD);
    }
    else
    {
        Serial.print("[MQTT] 连接失败，错误码=");
        Serial.println(mqttClient.state());
    }
}

void IotMqtt_Loop()
{
    if (!MyWIFI_IsConnected())
    {
        return;
    }

    if (!mqttClient.connected())
    {
        if (millis() - lastReconnectTry >= RECONNECT_INTERVAL_MS)
        {
            lastReconnectTry = millis();
            connectMqtt();
        }
        return;
    }

    mqttClient.loop();
}

// 传感器 JSON: 与后端约定的小写字段，另附 pump/heater 真实状态
void IotMqtt_PublishSensor(float t1, float t2, float pressure, float flow)
{
    char buf[220];
    snprintf(buf, sizeof(buf),
             "{\"temp1\":%.2f,\"temp2\":%.2f,\"pressure\":%.3f,\"flow\":%.2f,"
             "\"pump\":%d,\"heater\":%d}",
             t1, t2, pressure, flow,
             ControlThePump_GetState() ? 1 : 0,
             ControllingTemperature_GetState() ? 1 : 0);

    bool ok = mqttClient.publish(TOPIC_SENSOR, buf);
    Serial.print("[MQTT] 发布传感器: ");
    Serial.print(buf);
    Serial.println(ok ? "  [OK]" : "  [FAIL]");
}

void IotMqtt_PublishAck(const char *device, const char *action, bool state, const char *result)
{
    char buf[180];
    snprintf(buf, sizeof(buf),
             "{\"device\":\"%s\",\"action\":\"%s\",\"status\":%d,\"result\":\"%s\"}",
             device, action, state ? 1 : 0, result);

    bool ok = mqttClient.publish(TOPIC_STATUS, buf);
    Serial.print("[MQTT] 发布回执: ");
    Serial.print(buf);
    Serial.println(ok ? "  [OK]" : "  [FAIL]");
}
