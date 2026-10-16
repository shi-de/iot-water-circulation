# 物联网水循环系统

此仓库整理了本地水循环系统的 ESP32 固件与 Python/Web 监控应用。两部分保留各自现有协议版本，部署前需要对齐主题、载荷和单位。

## 结构

- `firmware/`：ESP32 Arduino / PlatformIO 固件，包含温度、压力、流量采集，水泵与温控，Wi-Fi/MQTT 通信。
- `web/backend/`：FastAPI、Paho MQTT、SQLAlchemy/SQLite 后端与测试。
- `web/static/`：网页、图表资源和前端逻辑测试。

## 固件

安装 PlatformIO，进入 `firmware`：

```sh
pio run
pio run -t upload
pio device monitor
```

目标为 `esp32dev`，串口波特率 115200。依赖在 `platformio.ini` 中声明。

烧录前修改 `firmware/src/Config.h` 的 Wi-Fi 名称、密码、MQTT 地址及继电器触发方式。仓库中的值为占位配置，不能直接联网；不要提交实际凭据。引脚分配和传感器换算以各源文件为准。

## Web 应用

```sh
cd web/backend
python -m venv .venv
# Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
# Windows:
copy config.example.json config.json
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000`。部署前编辑本地 `config.json` 的 broker、主题及阈值，或通过 `config.py` 中声明的环境变量覆盖。另行安装并配置 MQTT broker；本仓库不包含 broker 服务。

数据库在运行时生成；仓库不包含现场数据库和本地配置。首次使用可按需执行 `python init_db.py`，具体数据库创建流程以代码为准。

## 协议版本差异

当前固件主题为 `iot/water/sensor`、`iot/water/cmd`、`iot/water/status`；后端默认主题为 `watercycle/device/telemetry`、`watercycle/device/control`。上传时没有改写业务协议。联调前应统一主题，并核对 JSON 字段、控制指令、压力/流量/温度单位及回执处理；仅修改 broker 地址不足以保证兼容。

涉及加热器、水泵和继电器，实际接线和联调须按硬件规格进行；软件示例未完成本次硬件联调验证。

## 测试

后端测试需要额外安装 `pytest` 和相关测试依赖：

```sh
cd web/backend
python -m pytest
```

前端逻辑：

```sh
cd web/static
node --test test_frontend_logic.cjs
```

本次测试执行结果与尚未完成的验证见 `VALIDATION.md`。

## 来源与上传范围

保留现有源码和第三方资源中的版权说明。前端 `chart.min.js` 为第三方图表库。未包含完整比赛资料、个人报名文件、AI 工作记录、数据库、真实网络配置、依赖缓存及编译产物；本次未新增覆盖全部内容的开源许可证。
