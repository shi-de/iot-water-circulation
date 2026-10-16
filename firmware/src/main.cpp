#include "Config.h"
#include "ControlThePump.h"
#include "ControllingTemperature.h"
#include "IotMqtt.h"
#include "MyTemperature.h"
#include "MyWIFI.h"
#include "PressureSensor.h"
#include "YFS401.h"

static unsigned long lastSensorPublish = 0;

void setup()
{
    Serial.begin(115200);
    delay(300);
    Serial.println("\n===== 水循环系统 ESP32 启动 =====");

    MyTemperature_Init();        // DS18B20 x2 (GPIO4)
    PressureSensor_Init();       // NSA2302 压力传感器 (SDA=GPIO21, SCL=GPIO22)
    YFS401_Init();               // 流量传感器 (GPIO27)
    ControllingTemperature_Init(); // 加热继电器 (GPIO23)
    ControlThePump_Init();       // 水泵继电器 (GPIO26)

    MyWIFI_Init();
    IotMqtt_Init();
}

void loop()
{
    MyWIFI_Loop();       // 维持 WiFi 连接
    IotMqtt_Loop();      // 维持 MQTT 连接 + 处理收到的指令
    ControlThePump();    // 本地按钮控制水泵（消抖）

    // 周期采集传感器；网络只决定是否发布，不影响本地采集
    if (millis() - lastSensorPublish >= SENSOR_PUB_INTERVAL_MS)
    {
        lastSensorPublish = millis();

        float temp1 = 0.0f, temp2 = 0.0f;
        MyTemperature_Read(temp1, temp2);

        float pressure = PressureSensor();
        float flow = YFS401();

        if (IotMqtt_IsConnected())
        {
            IotMqtt_PublishSensor(temp1, temp2, pressure, flow);
        }
        else
        {
            Serial.printf("[采集] T1=%.2fC T2=%.2fC P=%.3fMPa F=%.2fL/min [MQTT OFF]\n",
                          temp1, temp2, pressure, flow);
        }
    }
}
