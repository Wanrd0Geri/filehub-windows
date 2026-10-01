# FileHub Windows 0.1.1 合并包装报告

基线 `3f159740e7be97db0402006af39a1e6ce3e3efb2`。本轮合并 Explorer 右键图标、持久口令历史标签和底部提示区，不改归档引擎、路由规则、监控范围或整理日志 schema。产品冻结后的最终合并构建完成；此前 icon-only 0.1.1 候选是诊断包，不是当前交付。

## 验证与范围

- Icon 回归 RED：6 个展开 case 中 4 failed、2 passed；失败点为缺少 Icon 及外部图标被覆盖。GREEN：`tests/test_integration.py tests/test_app_runtime.py`，36 passed in 3.85s。均使用 fake Registry，没有实时 HKCU 修改。[RED](../evidence/packaging-011/icon-red.txt) / [GREEN](../evidence/packaging-011/icon-focused-green.txt)。
- History/footer 实现代理最后 changed-area gate 为 44 passed，Astra 与 root 已审查隔离 Windows 原生截图。[源码与视觉审查](release-011-astra-review.md)、[实现报告](task011-history-footer-sol.md)。主窗／小窗口共享当前 state 的 `tag-history.sqlite`；只记有效且未过期的预览，trim 后完全同串去重、最近优先、没有自动数量上限。删除／清空只改口令库；demo 隔离；点击只填入并使旧预览失效。文件 IO 全在既有 serial worker。
- 原生 UI 截图为 source Qt、Windows、隔离 demo state，DPR 1.5，覆盖 dark/light 的 1000×700、800×620，归档 dialog、settings footer，以及 59 个标签／3 条最近记录／4,559 字符长消息。没有真实用户 state 或物理 Explorer 菜单截图声明。长 footer 高度最多 144 logical pixels，完整消息可滚动、选择或看 tooltip。[原生状态](../evidence/ui/history-011-native-state.txt)。
- Root 独占最终 pytest 全 suite，使用独立 basetemp：**276 passed in 23.18s，exit0**。[原始输出](../evidence/root-011-final-pytest.txt)。没有重复跑全套或旧版广泛 native QA。
- 最终 `packaging/build.ps1` 完成 clean PyInstaller 与 Inno 编译，Inno **24.375s**。[构建日志](../evidence/packaging-011/combined-build.log)。PYZ 明确收集 `filehub.tag_history`、`filehub.ui.tag_history`、`filehub.ui.status_footer`。manifest app_version 0.1.1，212 个固定材料 hash 验证通过；仅将本机自有 components.json 规范为 LF，上游 notice 字节未改。
- 最终 portable `--self-test` 在新的自有 UUID sandbox、clean child 环境执行，**exit0，10 checks true**，实际 bundled probe 与 1920 视频命名／撤销仍通过。[自测](../evidence/packaging-011/portable-selftest.json)。没有启动普通状态或访问当前运行的用户程序。
- EXE 的 RT_GROUP_ICON / RT_ICON 包含现有 `resources/app.ico` 的相同暖黄 PNG 字节，256×256 解码成功；Inno PE ProductVersion 去掉字段补空格后为 **0.1.1**。首次 icon-only 审计未去掉 Inno 固定长度补空格，造成验收断言误报；修正读取方法后通过，无产品变更。[本轮资源与产物核对](../evidence/packaging-011/artifact-audit.json)、[root 独立核对](../evidence/root-011-artifact-audit.json)。

## 当前交付

| 文件 | bytes | SHA256 |
| --- | --- | --- |
| `dist/installer/FileHub-0.1.1-windows-x64-setup.exe` | 139,814,259 | `bacd74379bc38e02d924f381aad8980f07bd738e68800668cc4b699f68d37f1a` |
| `dist/FileHub/FileHub.exe`（须带完整目录） | 2,342,150 | `ff8a4183bbbe44bba023d1d36ae5b77afd6c2491adba6602990169e31cc17963` |
| 保留的 `dist/installer/FileHub-0.1.0-windows-x64-setup.exe` | 139,798,744 | `0de7a4cf0c246087318a60c9f77c782c1d05d684bc6d6ea22b7cc39efcb422f8` |

本轮没有安装／卸载／更改真实注册表／停止现有应用／重启 Explorer／操作真实监控、同步或状态目录。实时入口没有被直接修复；用户需先从托盘退出旧版，再运行 0.1.1 安装器并勾选 Explorer 右键菜单。当前 0.1.1 安装／升级／卸载矩阵未重测；0.1.0 的历史广泛验收保留在 [验收结果](../验收结果.md) 和 [Task6 报告](task-6-sol.md)，不得借用为新版本重复执行声明。Windows 10／全新 VM／Mac／真实双机百度同步仍未验证。

无 stage / commit / push / merge；等待控制方独占 index 窗口。
