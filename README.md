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

通过环境变量配置 OpenAI 兼容接口：

```bash
set LLM_API_KEY=your_api_key
set LLM_BASE_URL=https://api.openai.com/v1   # 可选，默认 OpenAI
set LLM_MODEL=gpt-4o-mini                     # 可选
```

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

## Web 版（本地应用）

基于 FastAPI + 原生前端，在浏览器中完成上传、解读、问答与导出：

```bash
python -m webapp.main
```

启动后访问 <http://127.0.0.1:8000> 即可使用。解读与问答同样需要配置 `LLM_API_KEY`。

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
webapp/
├── main.py          # FastAPI 后端（上传/解读/问答/导出）
└── static/          # 前端页面（HTML/CSS/JS）
```

