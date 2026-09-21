# 美术源素材

这里保存涅莫团子的可修改源：角色基准图、完整高分辨率栅格条带、生成提示词、布局模板和 16 方向注视设计。项目没有 PSD、Live2D 或分层绘画工程，因此不会虚构这些文件；当前可编辑源就是 PNG 栅格条带。

## 许可范围

贡献者有权授权的 `source/` 内容采用 CC BY-NC-SA 4.0，完整条款见仓库根目录 `LICENSE-ASSETS`。再发布或改作时必须：

1. 仅用于非商业目的；
2. 标注本项目和相应贡献者，并链接许可证；
3. 说明是否做过修改；
4. 以 CC BY-NC-SA 4.0 或兼容许可证共享改作。

原角色、名称、设定、标识、商标和官方原画不属于贡献者可授权的范围，具体边界见根目录 `NOTICE`。仓库不包含从网页下载的官方原画或权利不明的参考图。

## 修改与重建

- 角色外观基准：`canonical-base.png`
- 动画与注视条带：`rows/`
- 生成提示词：`prompts/`
- 排版参考：`layout-guides/`
- 注视机制：`look-mechanics.md`
- 文件哈希和派生关系：`generation-manifest.json`

Row 2（`running-left`）由 Row 1（`running-right`）逐帧水平镜像得到；只镜像每一帧，不反转帧的时间顺序。构建器会按该派生关系重新生成 Row 2。

在仓库根目录运行：

```powershell
python -m nemo_pet_builder build
python -m nemo_pet_builder validate --strict
python -m nemo_pet_builder package
```
