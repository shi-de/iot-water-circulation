# 上传前验证

- 后端：`python -m pytest -q --disable-warnings`，39 passed、2 warnings。
- 前端：`node --test test_frontend_logic.cjs`，通过。
- 固件：`test/test_pressure_sensor_contract.ps1`，通过。
- 固件未进行完整 PlatformIO 编译，本次也没有传感器、继电器、泵或加热器实物联调。
- 实际 Wi-Fi 配置已在上传副本替换为占位值，数据库和本地 `config.json` 不纳入版本控制。
- 默认局域网地址已替换为文档示例地址，相关测试断言已同步。
- 固件和后端的 MQTT 主题及消息协议仍需对齐，详见 README。测试通过不代表现有两端已经兼容。
