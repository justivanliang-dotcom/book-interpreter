# 书籍解读器（MVP）

基于 LLM 的书籍解读工具：导入 TXT/Markdown 书籍，自动生成章节摘要、全书解读、核心观点与金句摘录，并支持基于内容的问答。

## 功能

- **章节解析**：自动识别 Markdown 标题或常见章节格式（第X章 / Chapter X）

- **章节摘要 + 全书解读**：逐章摘要、全书概述、核心观点提炼

- **金句摘录**：自动提取书中代表性金句

- **内容问答**：基于 TF-IDF 检索 + LLM 生成答案（RAG）

- **结果导出**：Markdown / HTML 报告

## 安装

```bash
pip install -r requirements.txt
```

## 配置 LLM

通过环境变量或项目根目录的 `.env` 文件配置 OpenAI 兼容接口：

```bash
# 方式一：环境变量
set LLM_API_KEY=your_api_key
set LLM_BASE_URL=https://api.deepseek.com   # 可选，默认 OpenAI
set LLM_MODEL=deepseek-chat                 # 可选

# 方式二：.env 文件（推荐，持久保存）
Copy-Item .env.example .env
# 然后编辑 .env，填入 LLM_API_KEY
```

`.env` 文件已被 `.gitignore` 忽略，密钥不会提交到仓库。

## 使用

解读书籍并导出报告：

```bash
python -m book_interpreter.cli interpret sample/sample_book.md -o report.md
python -m book_interpreter.cli interpret sample/sample_book.md --format html -o report.html
```

基于书籍内容提问：

```bash
python -m book_interpreter.cli ask sample/sample_book.md "刻意练习的核心是什么？"
```

## 测试

```bash
python -m pytest tests -v
```

## 项目结构

```
book_interpreter/
├── models.py        # 数据模型（Book / Chapter / Interpretation）
├── parser.py        # TXT/Markdown 章节解析
├── llm.py           # LLM 客户端（OpenAI 兼容）
├── interpreter.py   # 章节摘要、全书解读、金句摘录
├── retriever.py     # TF-IDF 检索（RAG 召回）
├── qa.py            # 内容问答
├── exporter.py      # Markdown/HTML 导出
└── cli.py           # 命令行入口
```

