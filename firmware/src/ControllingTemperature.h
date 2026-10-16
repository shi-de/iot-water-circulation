#ifndef CONTROLLINGTEMPERATURE_H
#define CONTROLLINGTEMPERATURE_H

#include <Arduino.h>

// 加热模块继电器控制（手动开/关；需要恒温闭环控制时可在此基础上加 PID/滞回逻辑）
void ControllingTemperature_Init();
void ControllingTemperature_Set(bool on);
bool ControllingTemperature_GetState();

#endif
