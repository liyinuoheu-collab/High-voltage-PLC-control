# 上位机 V2 验证报告

验证日期：2026-07-21（Asia/Shanghai）

## 自动测试

命令：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m unittest discover -s tests -v
```

结果：35 项通过。覆盖 V3/V4 解析、有限/持续时长显示、首帧前元数据回退、原始字节保留、简化 CSV、简化导出失败隔离、断线封存、丢帧检测、十分钟等效数据流和 V4/V3 混合端到端会话。

端到端会话确认：原始串口字节完全一致，完整 CSV 与简化 CSV 行数一致，简化文件只有四列，时间为 `HH:mm:ss.fff`，V3 回退标记正确，元数据记录最后一帧时长。

## Windows 打包与启动

- PyInstaller：6.21.0
- Python：3.11.15
- 构建命令：`powershell -ExecutionPolicy Bypass -File .\build_exe.ps1`
- 构建结果：成功
- EXE：`C:\Users\Asus\AppData\Local\DonutHASELMonitorBuild\dist\Donut-HASEL-Drive-Monitor-V2\Donut-HASEL-Drive-Monitor-V2.exe`
- 冒烟测试：启动后 4 s 仍在 Qt 事件循环中；随后只终止该测试实例。

PyInstaller 的 OpenGL/跨平台串口提示来自未使用的可选模块，不影响本程序的 PySide6 二维界面和 Windows 串口功能。

## 源目录隔离

将 V1 源目录中 25 个基线跟踪文件逐一与 V2 仓库基线提交 `84a3fa0` 的 Git blob 比较，差异为 0。V2 修改只存在于新目录。

## 尚需联机验证

自动测试不能替代真实 USB-TTL 长时连接、电脑睡眠/磁盘空间检查以及与 SG3150 文件的实际粗对齐。上位机保持只读，软件退出不会关闭板端高压。
