# FileHub Windows 0.1.0

把视频、图片与角色／场景素材按项目口令收进同步项目，先预览，再执行，并在统一历史中撤销。

## 开始使用

1. 运行 `dist/installer/FileHub-0.1.0-windows-x64-setup.exe`。按当前用户安装，无需另装 Python 或 ffprobe。
2. 从开始菜单打开 **FileHub 演示（隔离示例）**，先在独立示例里试归档和撤销。
3. 打开普通 **FileHub**，选择同步根目录与独立监控目录，保存设置。首次启动没有目录配置，自动整理保持暂停。
4. 先用“送进项目”预览目标，再执行。确认设置后取消暂停；高级全局任务默认关闭。

Windows 10 22H2 x64 及以上为安装器目标；本轮在 Windows 11 x64 build 26200 实测。Windows 10、全新虚拟机、Mac 与真实双机百度同步尚未验证。

关闭主窗口会继续在托盘运行。升级／卸载前，从托盘选择“退出 FileHub”，等整理结束。

- [使用说明](docs/使用说明.md)：口令、目录、缓冲期、撤销与卸载保留。
- [验收结果](docs/验收结果.md)：Windows 实测、模拟与未验证范围。
- [第三方许可](docs/第三方许可.md)：离线源码、版权及动态库替换。
- [Task6 报告](docs/reports/task-6-sol.md)：固定依赖、构建、诊断与最终证据。

便携版为完整 `dist/FileHub/` 目录，不能只复制 `FileHub.exe`。构建方法见 `packaging/build.ps1`。
