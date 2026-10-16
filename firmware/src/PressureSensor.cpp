/*
 * NSA2302 pressure sensor over hardware I2C.
 *
 * The supplied materials use two address conventions:
 *   - module guide: 7-bit address 0x00
 *   - vendor 8051 source: 8-bit 0xFE/0xFF, or 7-bit 0x7F
 *
 * Probe both addresses because 0x00 is not normally reported by a standard
 * I2C scanner. SDA/SCL still require external pull-ups to 3.3 V.
 */
#include <Arduino.h>
#include <Wire.h>
#include "PressureSensor.h"

#define PS_SDA_PIN    21
#define PS_SCL_PIN    22
#define PS_I2C_ADDR   0x00
#define PS_VENDOR_ADDR 0x7F
#define PS_DRDY_REG   0x02
#define PS_COMMAND_REG 0x30
#define PS_PRESSURE_REG 0x06
#define PS_DRDY_TIMEOUT_MS 500UL
#define PRESSURE_MAX  1.6f

static float         lastPressure = 0.0f;
static unsigned long lastReadMs   = 0;
static uint8_t       sensorAddr   = PS_I2C_ADDR;
static bool          sensorPresent = false;

static bool I2C_ReadRegisters(uint8_t address, uint8_t reg, uint8_t *data, uint8_t length)
{
    Wire.beginTransmission(address);
    Wire.write(reg);
    uint8_t txError = Wire.endTransmission(false);
    if (txError != 0)
    {
        Serial.printf("[压力] I2C寄存器地址失败 addr=0x%02X reg=0x%02X err=%u\n",
                      address, reg, txError);
        return false;
    }

    uint8_t received = Wire.requestFrom((int)address, (int)length, true);
    if (received != length)
    {
        Serial.printf("[压力] I2C读取长度错误 addr=0x%02X reg=0x%02X got=%u want=%u\n",
                      address, reg, received, length);
        while (Wire.available()) Wire.read();
        return false;
    }

    for (uint8_t i = 0; i < length; i++)
    {
        data[i] = Wire.read();
    }
    return true;
}

static bool I2C_WriteRegister(uint8_t address, uint8_t reg, uint8_t value)
{
    Wire.beginTransmission(address);
    Wire.write(reg);
    Wire.write(value);
    uint8_t txError = Wire.endTransmission(true);
    if (txError != 0)
    {
        Serial.printf("[压力] I2C写入失败 addr=0x%02X reg=0x%02X data=0x%02X err=%u\n",
                      address, reg, value, txError);
        return false;
    }
    return true;
}

static bool ProbeAddress(uint8_t address)
{
    uint8_t status = 0;
    return I2C_ReadRegisters(address, PS_DRDY_REG, &status, 1);
}

void PressureSensor_Init()
{
    Wire.begin(PS_SDA_PIN, PS_SCL_PIN);
    Wire.setClock(100000);
    delay(50);

    Serial.println("[压力] 硬件 I2C 探测地址 0x00/0x7F...");
    const uint8_t knownAddresses[] = {PS_I2C_ADDR, PS_VENDOR_ADDR};
    for (uint8_t i = 0; i < sizeof(knownAddresses); i++)
    {
        if (ProbeAddress(knownAddresses[i]))
        {
            sensorAddr = knownAddresses[i];
            sensorPresent = true;
            Serial.printf("[压力] 发现 NSA2302 @ 0x%02X\n", sensorAddr);
            break;
        }
    }

    if (!sensorPresent)
    {
        Serial.println("[压力] 未发现 NSA2302，请检查供电、共地、SDA/SCL线序和上拉电阻");
    }
}

float PressureSensor_Read()
{
    if (!sensorPresent)
    {
        Serial.println("[压力] 传感器未连接，跳过本次读取");
        return lastPressure;
    }

    // 1) 触发采集：写 0x30 = 0x0B
    if (!I2C_WriteRegister(sensorAddr, PS_COMMAND_REG, 0x0B))
    {
        sensorPresent = false;
        return lastPressure;
    }

    // 2) DRDY=1 表示忙，DRDY=0 表示采集完成
    unsigned long t0 = millis();
    uint8_t drdy = 0x01;
    while ((drdy & 0x01) && (millis() - t0 < PS_DRDY_TIMEOUT_MS))
    {
        if (!I2C_ReadRegisters(sensorAddr, PS_DRDY_REG, &drdy, 1))
        {
            sensorPresent = false;
            return lastPressure;
        }
        delay(5);
    }
    if (drdy & 0x01)
    {
        Serial.printf("[压力] 等待采集完成超时 DRDY=0x%02X\n", drdy);
        return lastPressure;
    }

    // 3) 读 5 字节（0x06 起）
    uint8_t data[5] = {0, 0, 0, 0, 0};
    if (!I2C_ReadRegisters(sensorAddr, PS_PRESSURE_REG, data, sizeof(data)))
    {
        sensorPresent = false;
        return lastPressure;
    }

    // 4) 24 位有符号 -> 归一化 [-1,1]
    long raw = ((long)data[0] << 16) | ((long)data[1] << 8) | (long)data[2];
    float value = (raw & 0x800000L)
                    ? (float)(raw - 16777216L) / 8388608.0f
                    : (float)raw / 8388608.0f;

    // 5) 0.2~0.9 -> 0~1，再乘量程
    if (value <= 0.2f) value = 0.0f;
    else if (value >= 0.9f) value = 1.0f;
    else value = (value - 0.2f) / 0.7f;

    float pressure = value * PRESSURE_MAX;
    if (pressure < 0.0f)         pressure = 0.0f;
    if (pressure > PRESSURE_MAX) pressure = PRESSURE_MAX;

    Serial.printf("addr=0x%02X DRDY=0x%02X raw=%ld val=%.3f P=%.3f MPa\n",
                  sensorAddr, drdy, raw, value, pressure);
    lastPressure = pressure;
    return pressure;
}

float PressureSensor()
{
    if (millis() - lastReadMs >= 1000)
    {
        lastReadMs = millis();
        lastPressure = PressureSensor_Read();
    }
    return lastPressure;
}
