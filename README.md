# isekaijouchou Codex 桌宠

以普遍体 Nemophila I 的角色特征为基础制作的日式二次元 Q 版 Codex 桌宠。

![动画总览](contact-sheet.png)

## 桌宠规格

- Codex 桌宠协议：v2
- 图集：`1536 × 2288` WebP，单格 `192 × 208`
- 动画：9 种标准状态
- 注视方向：16 个，按 22.5° 顺时针排列
- 背景：RGBA 透明
- 桌宠 ID：`nemo-dango`

## 安装

1. 下载并解压 `dist/nemo-dango-codex-pet.zip`。
2. 将解压得到的 `nemo-dango` 文件夹复制到 `%USERPROFILE%\.codex\pets\`。
3. 确保最终存在以下两个文件：

   ```text
   %USERPROFILE%\.codex\pets\nemo-dango\pet.json
   %USERPROFILE%\.codex\pets\nemo-dango\spritesheet.webp
   ```

## 内容

- `pet.json`：Codex 桌宠配置。
- `spritesheet.webp`：完整 v2 动画图集。
- `previews/`：九种动画状态预览。
- `look-directions.png`：16 个注视方向检查图。
- `contact-sheet.png`：完整动画帧总览。
- `validation.json`：图集结构验证结果。
- `direction-blind-validation.json`、`direction-semantics.json`、`look-continuity.json`：方向与连续性验收记录。

## 验收结果

- v2 图集尺寸、透明度和空闲格验证通过。
- 上、下、左、右四个基准方向匿名多数判定通过。
- 16 方向循环无明显反转、裁切、比例突变或注册跳动。
- 最终独立视觉验收通过。

## 说明

这是非官方的个人桌宠作品，仅用于私人使用。原角色及相关设定的权利归其原权利人所有。
