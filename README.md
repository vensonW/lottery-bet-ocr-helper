# 批量投注图片识别小帮手

## 功能

- 批量识别文件夹里的投注图片
- 支持 `job=N` 并发处理
- 读取 `skills/lottery_ocr/SKILL.md` 中的玩法规则
- 调用 OpenAI 视觉模型返回结构化 JSON
- 自动生成 Excel
- 需人工核查的行会写原因，并在右侧独立“核查截图”列贴局部截图
- 正常行备注为空

## 1. 先配置 API Key

复制示例配置：

```powershell
Copy-Item .\config.example.ini .\config.ini
```

然后打开 `config.ini`，填写：

```ini
[openai]
api_key = 你的OpenAI_API_Key
model = gpt-5.5
base_url = https://api.codexzh.com/v1
proxy =

[app]
job = 5
output_dir = outputs
max_image_side = 2048
retries = 2
ai_timeout_seconds = 120
```

`config.ini` 已加入 `.gitignore`，不要发给别人。

如果不使用转发地址，把 `base_url` 留空即可。当前你使用的是：

```ini
base_url = https://api.codexzh.com/v1
```

## 2. 安装命令行轻量版

```powershell
.\install.bat
```

只安装：

```text
openai
Pillow
openpyxl
```

不会安装 PySide6。

## 3. 命令行批量处理

先测试 OpenAI 接口是否连通：

```powershell
.\run_cli.bat --test-api
```

读取 `config.ini` 中的 API Key：

```powershell
.\run_cli.bat --input "D:\venson\投注小帮手\2026-06" --job 5
```

打印详细日志，包括发送给 AI 的 prompt 摘要、图片尺寸、调用重试和 AI 原始返回：

```powershell
.\run_cli.bat --input "D:\venson\投注小帮手\2026-06" --job 5 --verbose
```

如果网络慢，可以把单次 AI 请求超时时间调大：

```powershell
.\run_cli.bat --input "D:\venson\投注小帮手\2026-06" --job 5 --verbose --timeout 300
```

也可以临时覆盖 API Key：

```powershell
.\run_cli.bat --input "D:\venson\投注小帮手\2026-06" --job 5 --api-key "你的OpenAI_API_Key"
```

离线演示 Excel 效果，不调用 OpenAI：

```powershell
.\run_cli.bat --input "D:\venson\投注小帮手\2026-06" --job 5 --mock
```

只重新识别 Excel 中已经标记为 `需人工核查=是` 的图片，并用新结果替换这些图片旧记录：

```powershell
.\run_cli.bat --input "D:\venson\投注小帮手\2026-05" --job 2 --verbose --timeout 300 --reprocess-review
```

## 4. 输出

默认统一输出到项目 `outputs` 目录下，并按输入图片文件夹名分组：

```text
outputs\图片文件夹名\识别结果\投注识别统计_图片文件夹名.xlsx
```

例如输入目录是 `2026-05`，输出为：

```text
outputs\2026-05\识别结果\投注识别统计_2026-05.xlsx
```

如果文件已存在，程序会先读取 `识别明细` sheet 的 `图片文件名` 列：

- 已经存在记录的图片：跳过，不再发送给 AI
- 不存在记录的新图片：发送给 AI 识别，并追加写入同一个 Excel
- 不再覆盖清空旧 Excel 内容

注意：运行时请先关闭目标 Excel 文件，否则程序会在发送 AI 前提示文件被占用，避免识别完成后保存失败。

如果命令行指定 `--output`，则输出到指定目录下。

Excel 包含：

- `统计总览`
- `识别明细`
- `截图核对`

`识别明细` 列包括：

```text
序号 | 原图识别内容 | 玩法判定 | 标准化结果 | 金额(元) | 需人工核查 | 核查原因/备注 | 核查截图 | 图片文件名
```

## 5. 桌面界面稍后启用

等命令行测试没问题后，再安装 GUI：

```powershell
.\install_gui.bat
.\run_gui.bat
```

## 6. 说明

AI 不直接生成截图文件。AI 返回需要核查区域的坐标，程序从原图裁剪截图并贴入 Excel。这样截图一定来自原图，避免 AI 改写或幻觉。

截图裁剪会在 AI 返回坐标的基础上自动向四周扩大边距，避免手写数字贴边或被裁掉；Excel 中“核查截图”列会加宽显示。
