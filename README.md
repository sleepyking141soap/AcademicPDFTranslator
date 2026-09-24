# AcademicPDFTranslator

面向科研论文的原生 PDF 翻译与理解实验项目。当前版本为 **v0.2.0 alpha 1**；v0.1 的可检查核心链路之上，已经加入本地缓存和断点续译：

```text
PDF → Native PDF Parsing → PIR → AcademicGuard → 上下文翻译
    → TransCheck → PIR JSON + 双语 HTML → 按需 PaperExplain
```

**This project is currently in an early experimental stage.**

## 与普通 PDF 翻译工具的区别

| 模块 | 当前已实现 | 当前边界 |
| --- | --- | --- |
| Hybrid-ready PDF Parsing | 原生文本层优先；保留页码、bbox、字体、行、block；单/双栏启发式排序 | 预留 OCR、MinerU、Docling、Vision、融合协议，尚未实现这些后端 |
| AcademicGuard | 用独立占位符保护数值、百分比、常见单位、引用、图表编号、缩写、变量及 LaTeX 公式 | 正则规则不能识别所有学术符号和排版公式 |
| TransCheck | 比较数字、单位、引用、图表编号、受保护项的**多重集**；额外检查数值与单位组合 | 规则通过不等于语义正确；risk_score 是启发式分数，不是错误概率 |
| PaperExplain | 按需结合摘要、节标题、前后段，生成通俗解释、论文作用和术语解释 | LLM 解释需复核；不会自动解释全文 |
| Incremental Translation | 只缓存规则校验通过的模型原始输出；支持从 PIR 续传以及按失败/风险选择重试 | 缓存为本地文件，不含跨设备同步、并发锁或容量回收 |

项目没有复刻其他工具的代码，也没有实现 PDF 原版式回写。输出以可审查的 PIR 和双语阅读 HTML 为主。

## 安装（Python 3.11+）

Windows PowerShell：

```powershell
cd C:\academicPDFtranslator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

如果已存在配置好的 `.venv`，直接使用即可，无须重新创建。`dev` 包含 pytest、ruff 和生成测试 PDF 所用的 reportlab。只运行程序可用 `pip install -r requirements.txt`。

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

以下命令假定已激活虚拟环境。Windows 也可以把 `python` 替换成 `.\.venv\Scripts\python.exe`，避免 PowerShell 激活脚本权限问题。

编辑 `.env`：

```dotenv
APT_API_KEY=your-provider-key
APT_API_BASE_URL=https://api.openai.com/v1
APT_MODEL=your-provider-chat-model
APT_TARGET_LANGUAGE=Simplified Chinese
```

模型名由实际服务提供商决定，不内置可能失效的默认模型。也支持 `OPENAI_API_KEY` 作为备用环境变量。Base URL 应包含服务要求的前缀，例如 `/v1`，**不要**附加 `/chat/completions`。本地兼容服务如要求任意非空 key，可在环境变量中填写该服务指定的占位值。

翻译接口采用 [OpenAI Chat Completions 消息格式](https://developers.openai.com/api/reference/resources/chat)，通过 `httpx` 调用，支持自定义模型与端点。不同兼容服务的模型特性仍可能不同。

## 快速运行

### 无 API key 的离线流程验证

仓库带有合成的两页学术 PDF：第一页单栏、第二页双栏，含数值、单位、图注、表注、引用及参考文献。可以重建：

```powershell
python examples/create_sample.py
python cli.py examples/sample_paper.pdf --demo
```

输出：

```text
output/document.json
output/document.html
```

**`--demo` 仅回显原文，不做真实翻译，所有结果明确标记 DEMO，不会显示 verified。** 没有配置 API 时不会悄悄降级为演示模式。

只检查解析：

```powershell
python cli.py examples/sample_paper.pdf --parse-only --output output/parsed
```

### 调用真实模型翻译

```powershell
python cli.py paper.pdf
python cli.py paper.pdf --model your-model --api-base-url https://provider.example/v1 --target-language "Simplified Chinese" --glossary examples/glossary.json --output output/my-paper
```

`--glossary` 是源术语到首选译法的 JSON 映射，作为上下文提示使用；当前版本不强制校验术语译法。

默认启用本地翻译缓存，位置为 `.apt-cache/translations`。缓存键覆盖模型、API 端点指纹、目标语言、当前段落、上下文和术语表；不包含 API key。只有占位符恢复完整且 TransCheck 通过的结果才会写入。缓存文件包含模型输出，可能含论文内容，不应把 `.apt-cache` 提交到仓库或同步到不受信任的位置。

```powershell
# 禁用缓存，强制向服务商请求全部段落
python cli.py paper.pdf --no-cache

# 从上次 PIR 继续，默认只请求 failed/pending 段落
python cli.py paper.pdf --resume output/document.json

# 重新请求 failed 及 TransCheck 未通过的段落
python cli.py paper.pdf --resume output/document.json --retry risky

# 忽略旧段落与缓存，全部重新请求
python cli.py paper.pdf --resume output/document.json --retry all
```

续传前会核对 PDF 内容哈希、目标语言、模型名和 live 模式。设置不一致时会停止并说明原因，不会混用结果。`--retry risky` 针对翻译校验失败；版面低置信度属于解析问题，重新调用翻译模型通常不能修复。

CLI 返回码：`0` 表示处理完成（或解析模式完成）；`1` 表示输入/配置/导出等致命错误；`2` 表示有翻译失败、校验风险、OCR 缺页或不确定版面，已保留可用结果。返回 `0` 不代表语义正确。输出目录内的 `document.json/html` 每次运行会更新；不同论文请使用不同 `--output`。

### Web UI

```powershell
python app.py
```

打开 [本地界面](http://localhost:8501)：

1. 在侧栏设置 Model、API base URL、Target language。API key 从环境读取。
2. `Translate` 上传 PDF，点击翻译并观察逐块进度。
3. 查看双语结果，下载 PIR JSON 和 HTML。
4. 在 `Paragraph Detail` 选择文本块，查看 Original、Translation、TransCheck。
5. 可选择缓存及断点策略；导入旧 PIR 后上传同一 PDF，即可续传。
6. 点击 `Explain / 重新解释` 获取 Plain Explanation、Role in Paper、关键术语。解释会写回导出结果。

UI 结果存于 `output/<document_id>/`。同一 PDF 以不同模型/目标语言重跑会覆盖该目录；下载副本可以保留不同版本。

HTML 的 `Explain` 链接连接到本地 UI，并定位对应段落。先运行 `python app.py`；默认 CLI 输出和 UI 输出可自动载入。自定义目录的结果可通过侧栏导入 `document.json`，再切换 `Paragraph Detail`。纯静态 HTML 本身不会调用模型，也不携带 API key。若改变 UI 端口，请手动进入新端口并导入 PIR。

只有主动翻译或解释时，相关论文内容才会发送给配置的 API 服务。UI 默认仅监听 `127.0.0.1`，不包含账户系统或云部署配置。

### 命令行解释某段

先在 JSON/HTML 中找到 `block_id`，然后执行：

```powershell
python cli.py --pir output/document.json --explain p0001-b0005-0 --output output/explained
```

解释使用 `.env` 中的模型配置；原文、既有译文、校验结果均保留。解释完成后重新导出 JSON 和 HTML。

## PIR 与扩展接口

`Document → Page → Block → Line → Span` 使用 Pydantic 定义；新输出包含 `schema_version: "0.2"`，仍可读取 v0.1 PIR。

```json
{
  "document_id": "PDF内容哈希前20位",
  "page": 1,
  "block_id": "p0001-b0005-0",
  "block_type": "paragraph",
  "bbox": [54.0, 299.2, 456.7, 330.8],
  "section": "1 Introduction",
  "source": "native",
  "text": "...",
  "confidence": 0.85,
  "protected_items": [],
  "translation": "...",
  "warnings": []
}
```

上例为 block 字段示意，完整输出还保留 `lines/spans`、原始 block 编号、受保护文本、模型原始输出、恢复后的译文、翻译状态和校验结果。bbox 使用未旋转页面坐标，单位为 PDF point，原点左上；page 从 1 开始。block ID 在同一解析结果中稳定，不承诺跨解析器版本完全不变。

结构遵循 PyMuPDF 的 [TextPage DICT 文本层格式](https://pymupdf.readthedocs.io/en/latest/textpage.html)。页面缺少有效文字层时设置 `requires_ocr=true`，并保留原生可读部分。

| 后续能力 | 扩展点 |
| --- | --- |
| OCR / MinerU / Docling | `parser/base.py: PaperParser / PageEnricher`，统一返回 PIR |
| Native + Vision | `PageFusion`，保留来源、坐标、置信度 |
| 其他翻译后端 | `translation/base.py: BaseTranslator` |
| 其他模型传输协议 | `CompletionClient`，同时供 Translator / PaperExplain 使用 |
| 语义校验 | `verification/transcheck.py: SemanticVerifier`，仅协议，尚未接入执行链 |
| Web 阅读器 / 手机 APP | 版本化 PIR JSON；后续独立服务层，不与 Streamlit 绑定 |

更详细的设计与取舍见 [架构说明](docs/architecture.md)。

## AcademicGuard 与失败处理

- 每个受保护项的每次出现都有独立 token，例如 `<AP8d2f..._NUM_001>`；命名空间避开源文本中的字面占位符。
- 优先识别完整 LaTeX、引用、图表编号，再识别百分比、单位、符号和数字，避免重叠替换。
- 恢复前检查出现次数；缺失、重复和陌生 token 都生成 warning。重复 token 留在输出中，不擅自补全或重复恢复。
- 保存模型原始输出和失败译文便于排查。API 超时/429/5xx 有限重试；401/403/404 等错误中止后续 API 调用并记录未完成段落。
- 参考文献、检测到的独立公式、页眉页脚以及被标记为 table 的块保留原文，明确标记 `retained`，不会冒充校验通过的译文。
- 前后段限定在相同 section；上下文有字符总预算。当前段超长时明确失败，不静默截断。`APT_CONTEXT_CHARS` 是字符预算，**不是 token 预算**。

`verified` 仅表示：当前块经过翻译、确定性检查通过、没有块级 warning，且版面置信度达到阈值。它不证明译文完整、语义正确或研究结论真实。

## 测试和开发

```powershell
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

测试覆盖保护/恢复、重复/缺失 token、数字/单位/引用变更、数值单位错配、单双栏解析、缺文本层、失败输出、HTTP 兼容接口、PaperExplain JSON 校验、HTML 转义和 Streamlit 页面。测试使用合成 PDF 与模拟服务，不依赖 API key，不验证真实模型质量。

若 Windows 上历史 `pytest-of-<user>` 目录不可访问，可以给本次测试设置独立临时目录，无须更改全局权限：

```powershell
New-Item -ItemType Directory -Force tmp/test-runtime | Out-Null
$env:TEMP = (Resolve-Path tmp/test-runtime).Path
$env:TMP = $env:TEMP
python -m pytest -q
```

GitHub Actions 配置了 Windows/Linux、Python 3.11–3.14 的测试矩阵；本地验证记录见 [validation.md](docs/validation.md)，不把尚未运行的 CI 当作已验证结果。

## 已知限制

1. 版面分析采用启发式。复杂浮动图表、三栏、旋转文字、跨页段落、嵌套小标题和异常字体编码可能误排序或误分类；置信度也未经统计校准。
2. 无 OCR、视觉识别、图片中文字翻译和精确表格单元格恢复。`table` 为预留类型，当前 native parser 不自动识别完整表格结构。缺文字页只标记待 OCR。
3. 原生 PDF 行与段落边界不总相同；保留原始行，不自动猜测行尾断词。内嵌公式识别仅覆盖明确符号/LaTeX，不能保证复杂排版公式完整。
4. Guard/TransCheck 保护已知标记，不能发现全部否定、因果、限定词、语义遗漏和术语误译。相同数字对调不同实验的含义仍可能漏检。风险分数只是规则计数的启发式。
5. 已有文件缓存与断点续译，但没有并发锁、容量回收、跨设备同步、自动纠错重翻译或 tokenizer 精确预算。API 兼容性与生成质量需要用你自己的服务和论文验证。
6. PaperExplain 可能误判段落作用或补充不可靠解释；解释本身没有经过语义验证。HTML 是阅读输出，不是双语 PDF。

## v0.2 优先建议

1. **真实论文评测集**：覆盖不同出版格式，标注阅读顺序、公式和翻译错误，建立可量化回归指标。
2. **成本控制继续完善**：tokenizer 精确预算、缓存容量策略、并发锁和可审查的自动重译策略。
3. **版面增强**：跨页段落拼接、可审查断词处理、表格/公式识别及坐标联动阅读。
4. **小范围后端补充**：通过现有协议接入 Docling/MinerU 或按页 OCR，仅处理原生解析不足的页面。
5. **语义与术语校验**：保护否定、比较关系和实验对象关联；以真实评测集决定是否引入独立 verifier。

## 开源与许可证

采用 **AGPL-3.0-or-later**，完整条款见 [LICENSE](LICENSE)。原生解析依赖 PyMuPDF。示例 PDF 是本项目生成的合成数据；未包含第三方论文。`.env`、虚拟环境、输出和临时文件均被 Git 忽略。
