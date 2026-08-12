# Donut-HASEL 相位差高压驱动监控上位机 V3

本程序配合驱动板固件 V6，通过同一个 USB-TTL 串口持续读取约 50 Hz 遥测，并在待机状态下设置电压、波形、频率、占空比、左右相位差、总驱动时长和末端清荷。界面同时显示 Vcmd、Vreal 以及 LEFT/RIGHT 路由时序。

## 快速连接

- 驱动板继续使用独立 7.4 V 电源。
- 板端 PB6/TX 接 USB-TTL RX，PB7/RX 接 USB-TTL TX，GND 接 GND。
- USB-TTL 使用 3.3 V TTL、115200 baud、8N1。
- 不要连接 USB-TTL 的 VCC。
- CLK/IO 是 ST-Link 的 SWCLK/SWDIO，不是运行串口。

打开 `run_monitor.bat` 或 `dist\Donut-HASEL-Drive-Monitor-V3.exe`，刷新并选择 COM 口，然后连接。详细步骤见 [上位机操作说明](docs/UPPER_COMPUTER_V3_GUIDE.md)。

## 数据

每次记录建立独立 `session_...` 文件夹，记录时长没有软件上限：

- `serial_raw.log`
- `telemetry_raw.csv`
- `events.csv`
- `metadata.json`
- `simple_export.csv`

所有逐帧数据带电脑接收时间，可与 SG3150 导出数据按时分秒粗对齐；这不是硬件触发同步。显示平滑不会改变原始文件。

## 安全边界

板端硬保护始终独立工作。上位机“疑似击穿自动停机”默认开启，但仅在电脑和串口正常连接时有效；关闭它不会关闭板端硬保护。软件异常、串口断开或窗口关闭不代表高压已经关闭，紧急情况仍应切断板卡 7.4 V 电源并按规程安全泄放，禁止直接短接高压端。

## 测试与构建

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m unittest discover -s tests -v
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

固件原档和旧版上位机均不在本仓库内修改。
