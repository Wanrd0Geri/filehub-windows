# FileHub 0.2.2 包装记录

元数据准备完成，尚未构建；等待导演确认源码冻结。不得把本记录当成安装器验收通过。

版本输入：pyproject.toml、installer.iss、version-info.txt、verify-inputs.py 与 components.json 统一为 0.2.2；固定 PE 版本为 0.2.2.0。依赖、原生插件、源码 ZIP 与许可内容保持原 pin；第三方许可仅改当前版本标题。构建命令沿用 packaging/build.ps1。

UI 原生 Windows 验证：两个天数框 NoButtons，1–365 范围、输入与上下键保留；质量框箭头保持。深浅主题滚动条 8px，末端按钮为空，键盘／滚轮／拖动断言通过。实际窗口 DPR 为 1.0 与 1.99999999995；不能将 QT_SCALE_FACTOR 当作 Windows 缩放百分比。四张代表截图、脚本及结果见 docs/evidence/rules-022。转换 UI 既有 26 项回归通过；未重复全套测试。

历史安装器保留：0.2.1 为 143130835 字节，SHA256 9268a5c324d311476bca00538321166d42b18f45bfb167442c45e70b7b544f07；0.2.0 为 143135555 字节，SHA256 a36ac5a9f21e319d3a35c6aaf31a8a16dcad44254e997688a738659943053735。历史文档及证据不修改。

本任务仅构建和隔离便携验收；最终独立审核及交付复制由 root 负责。未执行 live install、注册表写入、现有程序停止、用户文件／状态／监控修改、pip、push 或关机。Git 由导演管理。
