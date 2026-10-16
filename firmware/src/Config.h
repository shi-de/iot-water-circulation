// ============================================================
//  ESP32 固件配置 —— ★ 比赛现场只改这一个文件 ★
// ============================================================
#ifndef NETWORK_CONFIG_H
#define NETWORK_CONFIG_H

// ===== ① WiFi：比赛局域网（现场向裁判/网络管理员确认） =====
#define WIFI_SSID       "YOUR_WIFI_SSID"          // 局域网 WiFi 名称
#define WIFI_PASSWORD   "YOUR_WIFI_PASSWORD"             // 局域网 WiFi 密码

// ===== ② MQTT：电脑(运行后端 main.py 那台)的局域网 IPv4 =====
// 在电脑 cmd 里输入 ipconfig 查看 IPv4 地址，替换下面引号中的内容。
// 必须与 iot_water_cycle/lan_config.py 里的 MQTT_BROKER 一致。
#define MQTT_BROKER_IP  "192.0.2.10"
#define MQTT_PORT       1883

// ===== ③ MQTT 主题（与后端 lan_config.py 完全一致，区分大小写） =====
#define TOPIC_SENSOR    "iot/water/sensor"   // 本机发布：传感器数据
#define TOPIC_CMD       "iot/water/cmd"      // 本机订阅：后端下发的控制指令
#define TOPIC_STATUS    "iot/water/status"   // 本机发布：指令执行回执

#define MQTT_CLIENT_ID  "esp32_water_01"

// ===== ④ 继电器触发方式 =====
// 1 = 低电平触发（默认，IN 给低电平继电器吸合）
// 0 = 高电平触发（IN 给高电平继电器吸合）
// 以继电器模块上丝印/说明书为准，改错会导致“开变关、关变开”。
#define RELAY_ACTIVE_LOW 0

// 传感器上报周期(毫秒)
#define SENSOR_PUB_INTERVAL_MS 2000UL

#endif
