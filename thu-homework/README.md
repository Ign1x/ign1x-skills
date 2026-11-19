# 清华网络学堂作业助手

一个可独立安装的 Codex skill：检查网络学堂作业，让你选择要做的项目，完成后提交并核验回执。报告按题目写，内容完整、简洁，排版清晰。

## 安装

将本目录 `thu-homework` 放入 `${CODEX_HOME:-$HOME/.codex}/skills/`，或保留源码位置并建立链接：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s /absolute/path/thu-homework "${CODEX_HOME:-$HOME/.codex}/skills/thu-homework"
```

若同名技能已存在，先检查它，不要直接覆盖。新会话中使用：

```text
$thu-homework 检查当前学期作业，先问我要做哪几项，再完成并提交。
```

也可要求“只检查”“先做好给我看，不提交”或指定准确课程和作业。需要 Python 3.10+ 与 Playwright Chromium；普通 Python 和 Nix 的准备命令见[运行环境](references/learn-platform.md#运行环境)。

## 首次使用

在独立的作业工作目录运行，助手会创建 `.thu-homework.private/profile.env` 并指出缺少的字段。只在本地文件填写：

```dotenv
name=
number=
password=
totp=
```

前三项必填。`totp` 用于需要二次验证的账号，也支持旧键名 `topt`；可使用密钥或 `otpauth://totp/...` URI。特殊字符值可用单引号括起，文件按 dotenv 语法读取，不执行 shell，也不展开 `${...}`。不要把真实值发进聊天或放在技能源码目录。

默认只报告缺失字段，不回显个人信息。填完后回复“已填写”。已在使用本地凭证文件时，可直接告诉助手其路径，缺少的键会被追加，已有值保留。

## 选择与交付

助手检查当前学期各课程，列出作业、北京时间截止日期和提交状态，再通过可用的 question / 用户输入工具让你选。支持回复多个编号、全部可提交或暂不处理。对“完成并提交”问题的选择即授权相应提交；只检查或只制作的请求不会上传。

只交题目需要的文件。代码作业不自动附加报告；需要报告时只保留必答内容、必要结果和分析。提交后核对平台记录和附件，保存本地回执。已有不同提交需要明确的替换授权；状态不清时停止重试。

## 本地验证与发布

凭证检查和离线回归测试不连接网络学堂：

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m unittest discover -s tests -v
```

如果安装了 Codex 的 `skill-creator`，还可以运行其 `scripts/quick_validate.py` 检查本目录。

本仓库只存技能、脚本和离线测试；真实资料、课程附件、作业成品和回执放在仓库外。`.gitignore` 提供额外排除规则，发布前仍应核对 `git diff --cached --stat` 与实际暂存文件。创建技能本身不会登录账号或提交作业。

## 许可证

Copyright 2026 Ign1x。本技能采用 [Apache License 2.0](LICENSE)。
