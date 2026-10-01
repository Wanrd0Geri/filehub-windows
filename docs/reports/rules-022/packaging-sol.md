# FileHub 0.2.2 包装记录

实际构建和隔离便携验收通过，产物已冻结。构建源码 commit `681bc6965617f7791bf22635b7045f36c15689c5`，managed filehub-rules worktree，branch feature/filehub-rules-020。最终产物独立审核与交付复制由 root 负责。

## 实际产物

| 文件 | 字节 | SHA256 |
| --- | ---: | --- |
| `dist/FileHub/FileHub.exe` | 2566737 | `1bd22a1ee6574dbd5ed63c7c243c378dd66414c6e9c1ef4ce3bbd98203a272af` |
| `dist/installer/FileHub-0.2.2-windows-x64-setup.exe` | 143140953 | `705bf74f3567c73fe152e907d0726a438a1784b0f1ffac58c83886c74b7fc33f` |

便携使用必须保留整个 `dist/FileHub/`。`dist/artifacts.json` 与 `docs/evidence/rules-022/packaging-artifact-hashes.json` 记录实际大小与哈希。

## 验证范围

- 版本输入 0.2.2／PE 固定版本 0.2.2.0 一致。freeze-input-manifest 后 verify-inputs exit0，228 个冻结文件、4 个源码 ZIP；依赖、原生插件、源码、工具与导入 pin 不变，变化仅为当前许可标题及版本资源哈希。`packaging-input-audit.json` 为构建输入证据。
- 原命令 `& packaging/build.ps1 -ISCC 'F:/Hazel Windows/sandbox/tools/inno-6.7.3/{app}/ISCC.exe'`，PYTHONDONTWRITEBYTECODE=1，exit0；Inno 编译 21.469 秒。完整日志 `packaging-build.log`；日志未出现 WARNING／ERROR。构建脚本隔离开发 PYTHONPATH／Qt 覆盖，filehub.spec 指向工作树源码。
- 实际 `dist/FileHub/FileHub.exe --self-test --state-dir <owned UUID>/portable-state`：exit0，23/23 项 true，runtime_frozen=true，2.032 秒。隐藏子进程，清除 Python／PySide／Qt 开发覆盖，PATH 仅 Windows／System32，120 秒边界。进程正常退出；实际仅执行一次 EXE 自测。启动器先出现 SYSTEMROOT 大小写取值错误，在创建子进程前失败；仅修正 UUID 内启动器，没有改产品代码。命令、环境与全部结果见 `packaging-portable-selftest.json`。
- 原 21 项保留：真实 PNG 归档／撤销、bundled ffprobe 64px、两段不同内容的 1920px 视频归档命名／序号／撤销；JPEG／PNG／WebP 往返、透明及 native 42B WebP；JPEG 背景、保留原图／撤销、同路径／跨扩展名替换及完整备份／撤销；无同步普通自动规则、复制→转换→移动的历史／撤销、导入规则默认关闭持久化、自定义模板路由持久化／撤销。
- 新增两项真实冻结运行时验收：占用 006 与 019 后续接为 020、跨格式替换备份／撤销；预览后目标被占用时拒绝执行并保留已占用内容。这是实际 EXE 结果，并非 source Python API 替代。
- UI 原生 Windows 源码验证：两个天数框 NoButtons，1–365、输入及上下键保留，质量框箭头保持；滚动条 8px、末端按钮为空、键盘／滚轮／拖动通过。四张代表截图含 960×640 小窗 DPR1 和 1200×800 设置窗实际 DPR1.99999999995。深浅主题文字可读、滑块细圆角且无棋盘格。`check.py`／`ui-results.txt` 记录源 UI 证据，不宣称是 EXE UI 验收。
- root 唯一全套源码测试：**733 passed in 61.91s，exit0**，原始输出 `root-full-suite.txt`；独立 Astra 源码／测试／UI 证据审查无 blocker，见 `docs/reports/rules-022/root-astra-review.md`。本包装任务没有重复全套测试或穷举 PYZ 审核；root 的最终产物审核另行记录。

## 保留与边界

旧 0.2.1 安装器 143130835 字节，SHA256 `9268a5c324d311476bca00538321166d42b18f45bfb167442c45e70b7b544f07`；旧 0.2.0 为 143135555 字节，SHA256 `a36ac5a9f21e319d3a35c6aaf31a8a16dcad44254e997688a738659943053735`。构建后再次核对一致。历史报告、交付说明及证据保持原字节。

本包装任务仅修改当前版本 metadata／说明／证据，构建授权后不改产品源码或 pin。未执行 live install、升级、卸载、注册表、用户文件／状态／监控／同步、pip、现有程序停止、push 或关机。原 F 工作区与 junction runtime 只读；Git 由导演负责。用户自行升级。最终独立产物审核、F 交付复制由 root 负责，本任务不执行。

图片元数据可能丢失、备份不会自动清理；Windows 10、全新虚拟机、Mac 与真实双机同步未验证。实际自测仅代表上述 23 项，安装／卸载矩阵未重做。产物与产品源码已冻结，无活动 owned 子进程。

最终 root 审核已完成：47 个 FileHub 模块的打包 PYZ 与冻结源码一致，EXE／安装器 PE 版本 0.2.2.0、固定材料／manifest、唯一 qwebp 与旧安装器保留均通过，见 `docs/evidence/rules-022/root-final-artifact-audit.json`。root 已将安装器与安装说明保存至 `F:/FileHub交付/0.2.2`，并校验安装器 SHA256 一致。完整最终范围见 [最终审查](final-astra-review.md)。
