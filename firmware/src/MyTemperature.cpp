#include <Arduino.h>
#include <DallasTemperature.h>
#include <OneWire.h>

#include "MyTemperature.h"//包含本模块的头文件，让这里定义的函数和外部（main.cpp 等）声明的接口对上。

#define TEMP_BUS_PIN 4

static OneWire oneWire(TEMP_BUS_PIN);//使用 OneWire 库管理 GPIO4 上的一根数据线
static DallasTemperature dallas(&oneWire);//DallasTemperature 库负责和 DS18B20 打交道

static float lastT1 = 0.0f;
static float lastT2 = 0.0f;   

void MyTemperature_Init()
{
    dallas.begin();
    int count = dallas.getDeviceCount();//让 DallasTemperature 库在总线上开始工作（扫描设备、设置好通信）。这之后才能读取传感器数量。
    Serial.print("[温度] 1-Wire 总线 GPIO");
    Serial.print(TEMP_BUS_PIN);
    Serial.print("，检测到 DS18B20 数量: ");
    Serial.println(count);
}

// 读取两个 DS18B20；读取失败时保持上一次有效值
bool MyTemperature_Read(float &temp1, float &temp2)
{
    dallas.requestTemperatures();   //让总线上所有 DS18B20 开始一次温度转换       // 阻塞等待转换完成

    float c1 = dallas.getTempCByIndex(0); //取第 1 个传感器的温度
    //如果这个地址没有传感器，会返回库定义的“断开”值 DEVICE_DISCONNECTED_C（通常是 -127）。
    float c2 = dallas.getTempCByIndex(1);

    if (c1 != DEVICE_DISCONNECTED_C)
    {
        lastT1 = c1;
    }
    
    if (c2 != DEVICE_DISCONNECTED_C)
    {
        lastT2 = c2;
    }

    if (c1 == DEVICE_DISCONNECTED_C && c2 == DEVICE_DISCONNECTED_C)
    {
        Serial.println("[温度] 两个 DS18B20 均未检测到");
        return false;
    }

    temp1 = lastT1;
    temp2 = lastT2;

    Serial.print("[温度] t1=");
    Serial.print(temp1, 2);
    Serial.print(" ℃  t2=");
    Serial.print(temp2, 2);
    Serial.println(" ℃");
    return true;
}
