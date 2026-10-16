#ifndef MYTEMPERATURE_H
#define MYTEMPERATURE_H

#include <Arduino.h>

// 一条 1-Wire 总线(GPIO4)上挂 2 个 DS18B20：index0=温度1，index1=温度2
void MyTemperature_Init();
bool MyTemperature_Read(float &temp1, float &temp2);

#endif
