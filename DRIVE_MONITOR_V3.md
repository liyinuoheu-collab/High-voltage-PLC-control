# 驱动监控上位机 V3 协议摘要

上位机使用 PB6/PB7、115200 baud、8N1 与固件 V6 双向通信。详细连接、控制和安全说明见 `docs/UPPER_COMPUTER_V3_GUIDE.md`。

典型遥测：

```text
D,v=6,seq=12,t_ms=840,run=1,wave=1,mode=2,state=2,route=1,left=1,right=1,v_set=7000,v_cmd=7000,v_real=6840,adc_mv=1368,period_ms=2500,duty=50,phase_deg=90,duration_ms=20000,clear=1,cycle=0,fault=0,locked=0,stable=1,hard_protect=1
```

上位机保存原始帧，并加入电脑 ISO 时间、`HH:mm:ss.fff` 和单调时钟。`simple_export.csv` 用于与 SG3150 导出结果做电脑时间粗对齐。

上位机可发送 `START`、`STOP`、`UNLOCK`、`FAULT,PC_ARC` 以及待机 `SET,...` 命令。遥测而不是编辑框是板端实际状态的最终可信来源。

疑似击穿筛选属于电脑端辅助判据；板端硬保护始终独立启用。软件关闭或串口断开不等于高压关闭。
