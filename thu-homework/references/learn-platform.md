# 网络学堂操作

## 运行环境

两种环境任选一种，不依赖其他已安装技能。运行时把命令中的路径换成实际绝对路径；工作目录位于技能目录之外。

普通 Python（3.10+）：

```bash
python3 -m venv /absolute/path/workspace/.thu-homework.private/venv
/absolute/path/workspace/.thu-homework.private/venv/bin/python -m pip install -r /absolute/path/thu-homework/requirements.txt
/absolute/path/workspace/.thu-homework.private/venv/bin/python -m playwright install chromium
```

Linux 若缺少 Chromium 的系统依赖，按 Playwright 提示安装；不要把依赖问题当作登录失败。

Nix（已附版本锁，适合 NixOS）：

```bash
nix develop path:/absolute/path/thu-homework -c python /absolute/path/thu-homework/scripts/credentials.py check --env /absolute/path/workspace/.thu-homework.private/profile.env
nix develop path:/absolute/path/thu-homework -c python -i /absolute/path/thu-homework/scripts/learn_browser.py --env /absolute/path/workspace/.thu-homework.private/profile.env
```

默认缓存目录不可写时，为命令设置 `XDG_CACHE_HOME=/tmp/thu-homework-nix-cache`。Nix 会复制源码到 store，真实个人资料必须留在技能目录之外。

## 登录

普通 Python 环境运行：

```bash
python -i /absolute/path/thu-homework/scripts/learn_browser.py --env /absolute/path/workspace/.thu-homework.private/profile.env
```

用可持续交互的终端会话保留 Python 进程，返回后可操作 `page`、`context`、`browser`、`pw`。脚本只登录，不选作业、不上传、不提交。`--headed` 需要图形会话，用于人工处理验证。不要打印 `profile` 的字段、认证页 HTML、Cookie 或完整带令牌的 URL。

账号只填入 **HTTPS 的 `id.tsinghua.edu.cn`**；密码加密交给认证页面自身的 JavaScript。默认临时会话，不保存 storage state，不启用 180 天信任。

- 主凭证缺失：先运行 `credentials.py init/check`，让用户在给出的实际文件中补齐。
- 需要 TOTP：文件内填写 `totp`，兼容历史 `topt`。支持 Base32 或 `otpauth://totp/...`；从文件读取，不在聊天中索要密钥。用户不愿保存密钥时，可在可用的有界面浏览器中自行完成验证，再继续检查登录结果。
- 脚本暴露 `resume_login()`：用户本地补齐资料或完成验证后在原会话调用。TOTP 首次失败最多等下一周期重试一次；两次失败即停，修正种子/时钟前不再尝试。二维码、短信、图形验证码等额外验证按实际页面请求用户处理，不猜答案或循环尝试密码。
- 登录选择器和提交选择器来自现有网络学堂流程；页面变化时检查实际控件再调整。不要靠自动刷新、连续重登绕过验证。

## 查找作业

1. 等待课程数据真正加载；读取当前学期，核对课程全名、课程号和教师。同名不同班的课程分别处理。遍历分页与折叠分组；空白、超时或加载失败不是“无作业”。
2. 从页面读取真实课程链接，通常形如 `/f/wlxt/index/course/student/course?wlkcid=...`；不要硬编码 ID 或自己拼作业地址。
3. 进入“课程作业”，检查“未提交”“已提交未批改”“已批改”，必要时翻页，按实际作业 ID 去重。“未提交”中也可能包含已截止项，读取截止和补交入口后再给用户候选。
4. 打开作业详情，阅读线上说明及教师附件。通过 `context.request.get(页面真实下载链接)` 获取需登录的附件；URL 含令牌时只在内存使用，文件保存到当前作业目录。避免把失败页或登录页保存成 PDF 后当作题目。
5. PDF 可用 `pypdf.PdfReader` 提取文字；扫描件需结合页面图像/OCR。教师附件与页面截止时间冲突时把两者告诉用户，按较早时间安排；页面已关闭且无补交入口的作业不能承诺提交。

选择后以实际作业 ID、课程和标题定位，不能只凭“作业 3”操作。等待用户回答期间若平台内容改变，重新核对所选项，新增作业不自动加入。

## 提交和回执

先检查本地交付物：命名、格式、大小和必交文件与题目一致。ZIP 用 `zipfile.ZipFile.testzip()` 核验 CRC，并看内容清单；记录每个实际上传文件的字节数及 SHA-256。

每次先检查页面；当前已知控件：

| 页面 / 控件 | 用途 |
| --- | --- |
| `viewZy` 的 `#saveBtn`，值为“去提交” | 进入提交表单 |
| `#fileupload` | 作业附件上传控件 |
| `#inputImage` | 头像上传，不能用作作业附件 |
| `#s_documention` | 可选说明，题目无要求则留空 |
| `#goBtn`，值为“提交” | 最终提交 |

```python
page.locator('#fileupload').set_input_files(str(artifact_path))
# 检查表单显示目标文件，且课程、作业和授权范围正确。
page.locator('#goBtn').click()
```

若题目要求多个附件，先核对当前表单是否支持多文件及平台数量限制，再逐项验证；不擅自改成 ZIP。附件大小限制以当前页面为准。

文件名出现在表单不等于上传成功。点击“提交”之后才可能显示上传进度或“文件正在上传请稍等”；等待上传和页面内容变化，不能连续点击。提交后 URL 可能仍在 `/student/tijiao`，仅凭 URL 不足以判断成功。

1. 返回课程作业列表，在“已提交未批改”（或实际更新后的状态）找到准确作业。
2. 打开 `viewTj`，确认“本人提交的作业”、平台提交日期及全部附件名/大小。
3. 从“上交作业附件”处下载本人的提交文件，不能误取教师题目附件。比较本地与回读文件的字节数和 SHA-256；散列不同只说明平台有提交，不能称“附件一致”。重新下载核验后仍不匹配时报告问题，不擅自覆盖。
4. 在作业工作目录保存简短 `submission-receipt.md`：课程和作业、平台提交时间（北京时间）、每个文件名/大小/散列、当前状态、回读核验结果。不要记录密码、Cookie、原始 HTML 或带令牌下载地址；回执留本地，不进入作业附件。
5. 结束调用 `close_browser()`（等同于关闭浏览器并停止 Playwright）；中断也尽量清理。

超时或断网：先只读查看列表和已交附件，确认成功则补回执；能明确确认没有提交且仍有授权、截止未过时，修正问题后最多重试一次。状态不明时停在“待核验”。已有不同附件仅在明确获得替换该项的授权后才重交，不撤回其他作业。
