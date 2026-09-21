# 参与贡献

感谢改进涅莫团子。提交前请确认改动属于代码、文档或你有权再分发的美术内容；不要加入官方原画、网页下载参考图、密钥、本机绝对路径或临时生成图片。

## 开发流程

1. 从最新 `main` 创建职责单一的分支。
2. 安装 Python 3.12 与开发依赖：`python -m pip install -e ".[dev]"`。
3. 修改源码，而不是直接修改派生产物；美术改动以 `source/rows/` 的完整行条带为单位。
4. 更新 `source/generation-manifest.json` 的相对路径、SHA-256、提示词和派生关系。
5. 运行 `python -m nemo_pet_builder build`、`python -m pytest`、`python -m nemo_pet_builder validate --strict` 与 `python -m nemo_pet_builder check-release`。
6. 提交 Pull Request，逐项说明改动、权利来源和实际运行的验证。

Row 2 必须从 Row 1 逐帧水平镜像并保留时间顺序。Row 9–10 的任一方向不合格时，应重新生成包含它的完整八帧行；不得直接修补最终图集单格或让相邻方向来自不一致的生成系列。

## 提交与合并

使用简短的 Conventional Commits 风格消息，例如 `fix: correct look-direction row`。将许可证、构建、素材、行为修复、测试、CI、文档和发布准备拆成可独立审阅的提交。维护者合并发布分支时应保留逻辑提交，不使用 squash，也不改写已经公开的历史。

## 许可

- 代码、构建工具、schema、测试和文档贡献按 MIT License 提供。
- 你有权授权的美术贡献按 CC BY-NC-SA 4.0 提供。
- 提交美术即表示你确认有权以该许可贡献它；第三方角色、商标和官方素材的权利不会因提交而转让。

Pull Request 的通过条件由 `.github/workflows/ci.yml` 定义。Windows 与 Ubuntu 均必须通过 schema 测试、可复现构建、严格方向 QA、打包和发布检查。
