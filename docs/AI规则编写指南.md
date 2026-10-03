# FileHub 0.3.1：AI 规则编写指南

本指南是独立、离线的格式说明。把它和同目录的 `filehub-rules-v1.schema.json`、`examples` 文件夹交给你使用的外部 AI，即可让 AI 按你的需求编写 JSON。也可以只附上本指南：下文已经包含五份完整文件。无需访问任何 GitHub 仓库、登录服务或提供 API Key。

FileHub 负责导入、校验、绑定本机文件夹、预览和执行规则；规则由你或外部 AI 编写。示例只是格式参考，不会被自动安装、启用或执行，也不是应用内的情景/模板库。独立图片转换和历史记录不要求安装规则。

已有项目配置的 Explorer 右键请求直接打开“手动标签”，沿用项目代码/目的地输入和最近口令。旧定义尚未迁移时，可在该窗口明确确认一次“恢复手动标签归档”，无需重写规则。恢复只新增手动权限，自动规则与观察目录不会因此启用；通用规则仍从主界面“文件处理”使用。

## 可以直接交给 AI 的要求

> 请根据我的文件处理需求，只输出一份完整的 UTF-8 JSON 规则文件。使用本指南的 `filehub.rules` 整数版本 1；不要输出注释、Markdown 围栏、解释或绝对路径。先声明符号目录绑定，再通过 `{ "binding": "ID", "relative": "相对子目录" }` 引用它们。使用有限条件和动作，不发明字段、脚本、正则捕获或命名 token。缺少具体文件夹信息时用可读 label，由我在 FileHub 中选择本机目录。如果是在修改已存在文件，请保留 package id 和未删除 rule id；新增规则用新 id。普通需求不添加 compatibility；我明确要求个人项目归档时，按本指南完整编码 compatibility，不另加 JSON 外解释。

把自己的处理需求接在这段话后面。更新规则时，附上 FileHub 导出的旧文件，让 AI 保留身份和未要求修改的字段。保存 AI 返回的纯 JSON，例如 `my-rules.json`，然后在 FileHub 导入。

## 文件结构与严格限制

顶层必需字段只有 `format`、`version`、`id`、`name`、`bindings`、`variables`、`rules`。可选字段只有 `compatibility`，用于下文单独介绍的个人归档方言。

| 字段 | 要求 |
| --- | --- |
| `format` | 固定字符串 `filehub.rules` |
| `version` | 整数 `1`；布尔值 `true`、字符串 `"1"` 均无效 |
| `id` | 稳定的文件身份；不是磁盘文件名 |
| `name` | 非空白名称，最多 256 个字符 |
| `bindings` | 至多 100 个符号声明；每项必需 `label`，可选 `description`；不包含路径或默认路径 |
| `variables` | 至多 100 个字面量文字变量；不包含表达式或环境变量 |
| `rules` | 有序数组，每条恰好有 `id`、`name`、`scope`、`condition`、`actions`；可为空 |
| `compatibility` | 可选完整 `filehub.archive.v1` 档案；普通规则不需要 |

文件/package、rule、binding、variable 和兼容 template 的 ID 使用 `[A-Za-z0-9_-]{1,128}`。同一文件的 rule id 不可重复。binding label 最多 256 字符，description 最多 512 字符。UTF-8 文件最多 **2,000,000 字节**，并非 2 MiB。JSON 不接受重复对象键、注释、NaN、Infinity、未知字段、错误类型、未知动作或版本。各层对象都封闭，不能添加 `enabled`、脚本、路径默认值等自定义字段。

每条规则有 1–20 个顺序动作；scope 至多 100 个不重复引用；条件组最多 4 层（根组算第 1 层），整棵条件树最多 100 个叶子。一个文件最多 1000 条规则；本机安装总量最多 100 个文件、1000 条规则；本机目录册最多 16,000,000 字节。这些是上限，不建议把不相关任务塞入巨型文件。

## 目录绑定、手动范围与观察授权

声明形式为 `"input": {"label": "来源文件夹", "description": "可选说明"}`。引用恰好为 `{"binding":"input","relative":""}` 或 `{"binding":"input","relative":"交付/PNG"}`。binding 必须已声明；relative 只能用 `/` 分隔安全的相对目录组件。

禁止绝对路径、盘符、UNC/设备路径、`..`、`.`、内部空段、反斜线、ADS 冒号、Windows 保留名、非法字符以及末尾空格/点。每个完整展开组件最多 255 个 UTF-16 单元；原始/展开相对路径和最后组合路径都必须小于 32767 个 UTF-16 单元。符号链接/junction、逃出绑定目录以及与应用状态重叠的路径也会被拒绝。中文可以使用；代理字符和过长名称不可使用。

导入后由使用者在本机选择每个目录。**绑定不会创建文件夹、添加观察目录、启用规则或执行文件操作**。只有实际引用的未绑定目录阻止对应规则；未使用声明可以暂不绑定。输出子目录可在获得执行授权后由现有操作引擎创建。

- `scope` 非空：只允许来源位于这些引用目录的**顶层**，手动选择也必须遵守；不会递归扩大来源。目录中的整个文件夹可以作为一个顶层对象处理。
- `scope` 为空：界面含义是“所有已配置观察目录；手动可选择文件”。手动来源仍须通过路径、状态目录、指纹等校验。
- scope 可以包含 A 和 B，但使用者只配置观察 A；A 可自动匹配，B 只在显式手动选择时处理。绑定 B 不会让应用扫描 B。
- 自动处理还要求规则本机启用、观察目录明确配置、应用运行且未暂停。导入和替换默认停用；手动可显式选择停用规则，先预览再执行。

自动匹配按本机文件顺序、文件内规则顺序选择第一条匹配规则。已经处理、被领取或第一条执行失败时，不会偷偷转给后续规则或旧收件箱。没有匹配规则默认什么也不做。

## 有限条件

叶子恰好有 `field`、`operator`、`value`。文字比较忽略大小写；glob 是有限通配匹配，不是正则表达式。

| field | operator | value |
| --- | --- | --- |
| `kind` | 仅 `equals` | `file`、`folder`、`image`、`video`、`audio`、`document`、`other`；`file` 表示任意非文件夹 |
| `extension`、`name` | `equals`、`contains`、`starts_with`、`ends_with`、`glob` | 非空文字，最多 4096 字符；扩展名建议显式带点，如 `.png` |
| `size_bytes`、`first_seen_age_seconds`、`stable_age_seconds` | `eq`、`lt`、`le`、`gt`、`ge` | 有限非负数字，至多 9223372036854775807；不是布尔值 |
| `created`、`modified` | `eq`、`lt`、`le`、`gt`、`ge` | 明确带时区的 ISO 8601，如 `2026-10-01T00:00:00+08:00` |

组恰好有 `mode` 与非空 `children`，mode 为 `all`（全部）、`any`（任一）、`none`（全部不满足）。children 可以是叶子或下一级组。例如条件片段 `{"mode":"all","children":[{"field":"kind","operator":"equals","value":"image"},{"field":"size_bytes","operator":"lt","value":10000000}]}`。

`created`/`modified` 是文件系统时间，不是图片 EXIF 拍摄日期。首次观察/稳定时长依赖已记录的观察事实，手动样本可能没有这些信息；不可用信息不会被当作匹配或凭空推算。条件中不允许 `${变量}`。

## 动作、顺序与命名

每个动作恰好有 `kind` 和 `options`。操作顺序严格保留。

| kind | options | 行为 |
| --- | --- | --- |
| `rename` | 仅 `pattern` | 在当前对象的父目录内改名 |
| `move` | 仅 `destination` 路径引用 | 移动当前对象，原名保留 |
| `copy` | 仅 `destination` 路径引用 | 保留原件；后续动作以副本作为当前对象 |
| `subfolder` | 仅 `path` 安全相对路径 | 移到当前对象父目录下的该子目录 |
| `image_convert` | 下表有限图片选项 | 转换结果成为后续动作的当前对象 |
| `project_route` | 仅 `tag` | 仅完整兼容档案允许，且必须是最后一个动作；要求其所属文件是已选择、已授予权限的档案 |

普通 move/copy/subfolder 目标已存在就拒绝覆盖，不承诺自动编号。rename 的 `{sequence}` 可以按现有规则寻找未占用名称；图片转换另有已验证的自动编号机制。预览绑定精确来源指纹、规则权限和目标；文件、绑定、规则或权限变化后必须重新预览。执行前目标突然被占用会拒绝，不能直接把旧预览改成另一个目标。

rename action 仅支持七个 token：

| token | 值 |
| --- | --- |
| `{original}` | 当前完整名称 |
| `{stem}` | 当前不带扩展名的名称 |
| `{ext}` | 当前扩展名，含点，文件夹为空 |
| `{date}` | 来源创建日期 `YYMMDD` |
| `{date_long}` | 来源创建日期 `YYYYMMDD` |
| `{period}` | 来源创建时间的 `AM` 或 `PM` |
| `{sequence}` | 从 1 起的命名序号 |

不支持 `{stem.name}`、`{date:%Y}`、`{sequence:03d}`、捕获组或其他表达式。没有在普通 rename action 中提供值的 `{prefix}`、`{note}`、`{episode}` 等不会因附带 compatibility 就变得可用。它们只在兼容模板的 naming_patterns 中有明确意义。

变量值是非空字面量组件文字，每个最多 256 字符，同时满足 255 UTF-16 组件上限；不能包含斜线、反斜线、冒号、Windows 非法字符、`$` 或花括号。`${NAME}` 只允许出现在 rename.pattern、subfolder.path、路径引用 relative；只展开一次，不递归，不读取环境变量。展开之后再验证完整名称/目录。只有 rename.pattern 使用上述运行时 token；子目录/path reference 不会把 `{date}` 等当作动态模板。

### 图片转换选项

| 选项 | 范围/默认 |
| --- | --- |
| `output_format` | 必需；`jpeg`、`png`、`webp`，不写 `jpg` |
| `mode` | `keep`（默认）或 `replace` |
| `destination` | keep 必需路径引用；replace 禁止该字段 |
| `quality` | 0–100 整数，默认 90 |
| `background` | `#RRGGBB`，默认 `#FFFFFF`，用于 JPEG 背景 |
| `lossless` | 布尔值，默认 false，WebP 无损选择 |
| `timeout_seconds` | 有限数字，大于 0、至多 3600，默认 60 |
| `max_pixels` | 1–40000000 整数，默认 40000000 |
| `kind` | 可选；只能 `image` |

keep 保留来源，在绑定目录生成结果。replace 在当前对象目录内替换；同扩展名可是真正原路径替换，跨扩展名/已占用名称可能编号为 `-1`、`-2`。替换前建立内部可恢复备份，撤销由历史记录处理。不要把实际文件占用情况或最终编号写死在 AI 的假设里。转换可能不保留元数据；本版本没有视频转换。

## 五份完整、可单独保存的 JSON

以下所有 JSON 围栏都是完整文件，未省略字段。示例分别保存为同目录 examples 中的相应文件即可；只选择你实际需要的文件导入。

### 示例 1：把文本移到交付目录

文件：`examples/01-move.json`。绑定 input、output 后，本规则只处理 input 顶层的 .txt。目标重名会拒绝。

```json
{
  "format": "filehub.rules",
  "version": 1,
  "id": "text-delivery",
  "name": "文本交付",
  "bindings": {
    "input": {
      "label": "来源文件夹"
    },
    "output": {
      "label": "交付文件夹"
    }
  },
  "variables": {},
  "rules": [
    {
      "id": "move-text",
      "name": "移动文本文件",
      "scope": [
        {
          "binding": "input",
          "relative": ""
        }
      ],
      "condition": {
        "field": "extension",
        "operator": "equals",
        "value": ".txt"
      },
      "actions": [
        {
          "kind": "move",
          "options": {
            "destination": {
              "binding": "output",
              "relative": ""
            }
          }
        }
      ]
    }
  ]
}
```

### 示例 2：复制 → 改名 → 放入子目录

文件：`examples/02-copy-rename-subfolder.json`。原件留在 input。先复制到 output，再给副本改名，最后移入 output/最终。变量由规则文件声明，目录仍由本机绑定。

```json
{
  "format": "filehub.rules",
  "version": 1,
  "id": "copy-delivery",
  "name": "保留原件并整理副本",
  "bindings": {
    "input": {
      "label": "来源文件夹"
    },
    "output": {
      "label": "副本文件夹"
    }
  },
  "variables": {
    "suffix": "交付",
    "stage": "最终"
  },
  "rules": [
    {
      "id": "copy-and-name",
      "name": "复制后重命名并移动到子目录",
      "scope": [
        {
          "binding": "input",
          "relative": ""
        }
      ],
      "condition": {
        "field": "name",
        "operator": "glob",
        "value": "*"
      },
      "actions": [
        {
          "kind": "copy",
          "options": {
            "destination": {
              "binding": "output",
              "relative": ""
            }
          }
        },
        {
          "kind": "rename",
          "options": {
            "pattern": "{stem}_${suffix}{ext}"
          }
        },
        {
          "kind": "subfolder",
          "options": {
            "path": "${stage}"
          }
        }
      ]
    }
  ]
}
```

### 示例 3：保留 JPEG → 转 PNG → 改结果名

文件：`examples/03-image-keep-ordered.json`。转换写入 output/PNG，后续 rename 处理生成的 PNG，原 JPEG 不动。

```json
{
  "format": "filehub.rules",
  "version": 1,
  "id": "png-delivery",
  "name": "JPEG 转 PNG 后命名",
  "bindings": {
    "input": {
      "label": "JPEG 来源"
    },
    "output": {
      "label": "图片交付"
    }
  },
  "variables": {
    "folder": "PNG"
  },
  "rules": [
    {
      "id": "convert-and-name",
      "name": "保留 JPEG 并生成 PNG",
      "scope": [
        {
          "binding": "input",
          "relative": ""
        }
      ],
      "condition": {
        "field": "extension",
        "operator": "glob",
        "value": ".jp*g"
      },
      "actions": [
        {
          "kind": "image_convert",
          "options": {
            "output_format": "png",
            "mode": "keep",
            "destination": {
              "binding": "output",
              "relative": "${folder}"
            }
          }
        },
        {
          "kind": "rename",
          "options": {
            "pattern": "{stem}_done{ext}"
          }
        }
      ]
    }
  ]
}
```

### 示例 4：显式选择图片并替换为 WebP

文件：`examples/04-image-replace.json`。空 scope 允许显式手动选择安全来源；它不会自行增加观察目录。replace 不包含 destination。启用自动处理前，应自行确认观察范围和替换意图。

```json
{
  "format": "filehub.rules",
  "version": 1,
  "id": "webp-replacement",
  "name": "显式选择图片转换为 WebP",
  "bindings": {},
  "variables": {},
  "rules": [
    {
      "id": "replace-image",
      "name": "转换并替换原图",
      "scope": [],
      "condition": {
        "field": "kind",
        "operator": "equals",
        "value": "image"
      },
      "actions": [
        {
          "kind": "image_convert",
          "options": {
            "output_format": "webp",
            "mode": "replace",
            "quality": 90,
            "lossless": false,
            "timeout_seconds": 60,
            "max_pixels": 40000000
          }
        }
      ]
    }
  ]
}
```

### 示例 5：单独的个人归档兼容档案

文件：`examples/05-archive-compatibility.json`。此示例是可选的旧标签方言，不是普通规则的必需配置。input 与 archive 独立绑定；archive 内项目路径可任意命名，不需要编号区域、固定“项目”层级、日期目录或网盘位置。

```json
{
  "format": "filehub.rules",
  "version": 1,
  "id": "personal-archive",
  "name": "个人项目归档兼容示例",
  "bindings": {
    "archive": {
      "label": "归档根目录"
    },
    "input": {
      "label": "待归档文件夹"
    }
  },
  "variables": {},
  "rules": [
    {
      "id": "two-shots",
      "name": "显式归档双镜视频",
      "scope": [
        {
          "binding": "input",
          "relative": ""
        }
      ],
      "condition": {
        "field": "kind",
        "operator": "equals",
        "value": "video"
      },
      "actions": [
        {
          "kind": "project_route",
          "options": {
            "tag": "XYZE02S08C22+23"
          }
        }
      ]
    }
  ],
  "compatibility": {
    "format": "filehub.archive.v1",
    "root": {
      "binding": "archive",
      "relative": ""
    },
    "projects": {
      "XYZ": {
        "binding": "archive",
        "relative": "项目档案/样例项目"
      }
    },
    "templates": [
      {
        "id": "team",
        "name": "完整镜头归档模板",
        "production_dir": "制作",
        "asset_root": "资产",
        "asset_categories": {
          "角色": "角色",
          "场景": "场景",
          "道具": "道具"
        },
        "final_dir": "交付",
        "keep_name_routes": {
          "剧本": "剧本",
          "甲方": "来稿",
          "参考": "参考"
        },
        "test_dir": "试验",
        "naming_patterns": {}
      },
      {
        "id": "preview",
        "name": "自定义预演命名模板",
        "production_dir": "制作",
        "asset_root": "资产",
        "asset_categories": {
          "角色": "角色",
          "场景": "场景",
          "道具": "道具"
        },
        "final_dir": "交付",
        "keep_name_routes": {
          "剧本": "剧本",
          "甲方": "来稿",
          "参考": "参考"
        },
        "test_dir": "试验",
        "naming_patterns": {
          "shot": "{prefix}_{shot}_{date_long}{period}_{resolution}_{sequence}{ext}",
          "asset": "{prefix}_{date}_{sequence}{ext}"
        }
      }
    ],
    "assignments": {
      "XYZ": "team",
      "DORMANT": "preview"
    },
    "default_template": "team",
    "general_test": {
      "binding": "archive",
      "relative": "公共测试"
    },
    "policies": {
      "inbox_root": {
        "binding": "archive",
        "relative": "收件箱"
      },
      "categories": {
        "image": "图片",
        "video": "视频",
        "other": "其他"
      },
      "arrival_delay_seconds": 259200,
      "expiry_delay_seconds": 259200,
      "disposable_filenames": [
        ".baiduyun.uploading.cfg"
      ],
      "sanitization_roots": [
        {
          "binding": "archive",
          "relative": ""
        }
      ]
    }
  }
}
```

## 个人归档兼容档案的边界

compatibility 必须完整包含 `format`、`root`、`projects`、`templates`、`assignments`、`default_template`、`general_test`、`policies`，format 固定 `filehub.archive.v1`。没有默认目录或模板注入；每个 template 记录必须包含上例的全部字段，即使 naming_patterns 为空。

projects 是明确的 ASCII 字母数字项目代码到路径引用的映射（至多 100 项，大小写别名不可重复），项目目录必须在已绑定 root 内。应用不会发现/自动加入后来创建的新项目；需要外部修改文件，再显式替换。assignments 可以保留暂时没有项目路径的旧项目分配，例如示例的 DORMANT，但其项目并不能被路由；template ID 必须确实存在。default_template 是明确记录中的 ID，可以不是 `default`。general_test 明确决定“通用测试”的目的地。

模板中的 production_dir、asset_root、final_dir、test_dir、类别目录和保留名称路由都是项目内的安全相对路径。asset_categories 和 keep_name_routes 中的口令不能和保留标签语法冲突。完整 naming_patterns 只接受 `shot`、`asset`、`final` 三种命名模式；留空使用已知历史命名算法，不会补入隐藏目录。

兼容模板 naming_patterns 可用完整历史 token 集合：`original`、`stem`、`ext`、`prefix`、`note`、`date`、`date_long`、`period`、`episode`、`scene`、`shot`、`sequence`、`resolution`，均写作 `{token}`。prefix/note/episode/scene/shot 来自已解析标签；resolution 来自受支持视频的实际探测，并非随便指定的宽度。不同路由缺少的值可能为空。只接受有限 token，不支持格式化、表达式或 `${变量}`。这套 token 集合不适用于普通 rename action。

保留的标签示例包括：`XYZ参考`（按记录保留名称）、`XYZ测试`（项目测试）、`通用测试`、`XYZ角色龙`（显式资产类别）、`XYZE02S08C22+23`（视频双镜）、`XYZ020822`（历史简写）、`XYZ成片E02`。具体目录都由完整项目/模板记录决定。已知双镜视频路由保留副本加移动行为；三镜及以上保留第一镜母文件并给出提醒。视频需要实际探测宽度，1920 宽视频对应已有 1080p 命名规则；不能保证不受支持的媒体输入成功。

policies 必须显式包含 inbox_root、三个不同的 image/video/other 类别名称、arrival_delay_seconds、expiry_delay_seconds、精确 disposable_filenames、sanitization_roots。延时为非负整数秒，至多 9223372036854775807；精确文件名和清理路径列表均至多 100 项。一次性文件名不是通配符，也不是文件名后缀匹配。

本机权限分开管理，导入/替换/迁移/恢复后全部关闭：

- `manual_archive`：允许个人归档入口与属于该档案文件的 project_route；自动规则仍另需启用、已配置观察目录和未暂停。
- `unmatched_inbox`：允许按显式延时归档没有匹配规则的观察目录顶层文件；不授权回收一次性文件。
- `cleanup`：另外允许回收精确一次性文件、清理过期收件箱日期目录，以及规范化明确声明的清理范围名称；cleanup 单独打开也不会归档普通未匹配文件。

只选择档案不授予以上任何权限。观察目录不能与运行中的收件箱重叠，cleanup 清理范围不能包含观察目录，收件箱过期范围不能和项目目录重叠。延时依据首次观察、稳定时间和文件/后代时间；不会把新观察到的老文件回填成早已等待完成。权限/档案变化会重新计时。

明确授予 manual_archive 的个人归档入口保留项目内去重：若找到内容相同的已有副本，应用持有并核验该副本的保护句柄，确认保留者安全后才把所选来源交给系统回收站，结果显示已有副本路径。预览后的目标突然被占用仍会拒绝，不能借去重绕过精确目标校验。去重回收的来源不能由普通“撤销移动/复制”自动重建；按历史结果到系统回收站手动恢复。这个已知手动去重行为由 manual_archive 授权；后台残留文件回收、收件箱过期和名称规范化另需 cleanup。

更新 compatibility 会废弃旧预览，但**不意味着重跑同一个已处理来源**：当 project_route 的条件、tag 和 scope 没变时，既有 Rule.revision 和已处理抑制关系保持；即使项目映射或模板变化，也不把旧来源自动当成全新工作。普通 destination/scope 等动作语义变化可以产生新语义 revision。涉及再次处理时，应显式核对历史和新来源/新规则身份，不依靠偷偷改变 ID 绕过抑制。

## 导入、更新、导出与恢复

1. 导入完整 JSON；所有规则和兼容权限默认停用。不会观察该外部文件，不会自动重读 AI 后续改写的文件。
2. 绑定本机目录；不会添加观察根或授权执行。选择样本，检查具体来源、目标、动作顺序与错误，再明确执行。
3. 若需后台规则，另外启用规则、配置观察目录并解除暂停；后台只评估已配置目录的顶层。
4. 同 id 更新使用“替换”或显式“重新载入”，先看新增/改变/移除规则与绑定变化再接受。未改变 rule id 保留稳定运行身份；新增规则才用新 id。替换后规则/兼容权限再次停用。
5. 导出只包含可移植定义，不包含本机路径、启用状态、观察配置、原文件位置、运行历史或内部备份。另一台电脑重新独立绑定。
6. 本机目录册备份的恢复是显式管理操作，只恢复定义和本机控制信息；恢复后停用并要求新预览。它不撤销已执行文件操作，也不会恢复/重放运行任务。真正的文件撤销走历史记录。

显示名称、启用开关、文件/规则排序和未变语义的替换会让旧预览失效，但不生成全新的已处理身份。删除/替换定义不抹除历史。不要要求 AI 填写内部 ext_ 运行 ID、revision、generation 或本机目录册字段。

“规则文件”页的旧版本迁移先显示只读候选，由使用者明确接受，导入后所有规则和权限关闭。“手动标签”窗的一次恢复另外新增手动标签权限，自动规则保持关闭；它不会暗中启用旧收件箱/清理。完整旧文件与原 ID 被保留。一个有界限制是：**旧普通 rename action** 若用了实际上没有值的内部专用 token（例如 prefix/note），即使旧配置有同步根也会拒绝迁移；错误指明原 rule id 和 pattern，原文件不改。应交给外部编辑者按七个实际可用 token 修改后显式导入，而不是注入新的命名语义。兼容模板 naming_patterns 的完整 token 行为仍保留。

## 校验方式与离线包内容

普通使用者：把本指南/schema/examples 交给外部 AI，保存纯 JSON，然后使用 FileHub 的导入校验和样本预览即可。标准 JSON Schema 2020-12 校验器能检查结构，但文件字节量、整棵条件叶子数、ID/引用关系、变量/token、Windows UTF-16 路径与绑定安全仍以 FileHub 共用解析器/运行时为准。

开发者若已经有 **包含 FileHub Python 包或源码的 Python 环境**，可运行：

```text
python -m filehub.rulefiles validate my-rules.json
```

该命令输出 JSON 诊断（包含字段路径），有效退出 0，无效退出 1；不会打开应用状态、创建观察或执行文件。**纯指南 ZIP 不带 FileHub Python 包**；这条命令不是要求朋友安装私有仓库，也不代表 FileHub.exe 支持某个额外验证命令参数。

离线 ZIP 固定包含本指南、版本 1 schema、五份 examples JSON 和 manifest.json。manifest 列出每个内容文件的相对路径、字节数和 SHA256；不包含个人机器路径或构建时间。示例解压、打开或被打包到 Help 都不会导入/启用任何规则。

应用打包 Help 约定：资源根目录 `help/AI规则编写指南.md`，同目录附 `filehub-rules-v1.schema.json`、`examples/`；源码环境回退到 `docs/AI规则编写指南.md`。指南是静态文件，打开/复制不会调用外部 AI。

## 不支持的能力

本版本不提供脚本、任意表达式/自定义解析器、正则捕获组、OCR、视频转换、自动联网、AI 调用、API Key、云市场、自动下载/重载规则、递归观察扩展，以及普通规则中的任意删除/回收动作。普通规则不能填写回收动作。已知兼容行为中，manual_archive 允许上述手动项目去重回收；cleanup 另外授权后台精确残留/过期收件箱清理与名称规范化。不要让 AI 发明字段或混淆这些本机权限来绕过格式校验。
