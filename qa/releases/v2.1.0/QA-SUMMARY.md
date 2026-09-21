# v2.1.0 QA 摘要

- 图集 SHA-256：`d0f685c7cfc6eef2d3075a9c106bcdaaf0f3a9cdc92c0323e1ffcb7df2059ae2`
- 结构：1536×2288、8×11、单格 192×208、RGBA、Codex pet v2。
- 动画：9 行均通过帧变化、循环闭合、基线和面积变化门禁；Row 1–2 使用同一帧序和固定 90 ms 预览节奏。
- 注视：16 方向顺时针连续性通过，`reviewRequired=false`。
- 盲测：3 名互相隔离的匿名审核者完成 7 组水平轴和 7 组垂直轴判断，共 28 个 A/B 分类；结果 28/28 符合预期，零 warning、零 unconfirmed。
- 旧版证据：v2.0.0 的含 warning 报告已移至 `qa/archive/v2.0.0/`，不作为本版本合格证明。

本摘要只证明已执行的源文件、构建产物和图像 QA。Codex 桌面端对 Row 3、Row 4、Row 7 与 Row 9–10 的触发和循环限制属于应用运行时行为，不由宠物包改变。
