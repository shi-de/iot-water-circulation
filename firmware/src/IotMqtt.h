#ifndef IOTMQTT_H
#define IOTMQTT_H

#include <Arduino.h>

void IotMqtt_Init();
void IotMqtt_Loop();
bool IotMqtt_IsConnected();
void IotMqtt_PublishSensor(float t1, float t2, float pressure, float flow);
void IotMqtt_PublishAck(const char *device, const char *action, bool state, const char *result);

#endif
