# ign1x-skills

个人 Codex 技能集合，每个技能放在独立目录中。

| 技能 | 用途 |
| --- | --- |
| [thu-homework](thu-homework/README.md) | 检查清华网络学堂作业，让用户选择，按要求完成、提交并核验附件。 |

## 安装 thu-homework

克隆仓库，将技能目录链接到 Codex 的 skills 目录：

```bash
git clone https://github.com/Ign1x/ign1x-skills.git
cd ign1x-skills
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$PWD/thu-homework" "${CODEX_HOME:-$HOME/.codex}/skills/thu-homework"
```

若同名技能已存在，先检查它，不要直接覆盖。依赖安装和首次配置见 [thu-homework 使用说明](thu-homework/README.md)。在新会话中使用：

```text
$thu-homework 检查当前学期作业，问我要做哪些，再完成并提交。
```

个人资料保存在作业工作目录的 `.thu-homework.private/profile.env`，作业工作目录应位于本仓库之外。

## 许可证

[Apache License 2.0](LICENSE)。
