#include <Arduino.h>

#define FLOW_PIN 27
#define PULSES_PER_LITER 1658.0f          // 实测 1L=1658 脉冲
#define FLOW_HZ_PER_LPM (PULSES_PER_LITER / 60.0f)   // ≈27.63
#define FLOW_EDGE RISING
#define MIN_PULSE_INTERVAL_US 1000UL      // >1000Hz 判噪声
#define FLOW_MAX_LPM 8.0f                 // 超 8 L/min 判噪声

volatile unsigned long pulseCount = 0;
volatile unsigned long lastPulseUs = 0;
unsigned long lastCalcTime = 0;
float totalLiters = 0.0f;
unsigned long totalPulses = 0;

void IRAM_ATTR flowISR()
{
    unsigned long nowUs = micros();
    if (nowUs - lastPulseUs >= MIN_PULSE_INTERVAL_US)
    {
        lastPulseUs = nowUs;
        pulseCount++;
    }
}

void YFS401_Init()
{
    pinMode(FLOW_PIN, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(FLOW_PIN), flowISR, FLOW_EDGE);
    lastCalcTime = millis();
    Serial.println("Flow sensor start");
}

float YFS401()
{
    unsigned long now = millis();
    float flowLMin = 0.0f;
    if (now - lastCalcTime >= 1000)
    {
        noInterrupts();
        unsigned long pulses = pulseCount;
        pulseCount = 0;
        interrupts();

        float seconds = (now - lastCalcTime) / 1000.0f;
        lastCalcTime = now;
        totalPulses += pulses;

        if (pulses > 0)
        {
            float frequency = pulses / seconds;
            flowLMin = frequency / FLOW_HZ_PER_LPM;
            if (flowLMin > FLOW_MAX_LPM || flowLMin < 0)
                flowLMin = 0.0f;               // 噪声 -> 丢弃
            else
                totalLiters += pulses / PULSES_PER_LITER;
        }

        Serial.print("Pulses: "); Serial.print(pulses);
        Serial.print(", TotalPulses: "); Serial.print(totalPulses);
        Serial.print(", Flow: "); Serial.print(flowLMin, 3);
        Serial.print(" L/min, Total: "); Serial.print(totalLiters, 3);
        Serial.println(" L");
    }
    return flowLMin;
}