# GovMatch V3｜公务员岗位资格初筛助手

GovMatch 是一个基于 Streamlit、Pandas 和可解释规则引擎的公务员岗位表筛选工具。它把“已通过的规则”“尚未识别的字段”和“仍需人工核对的条件”分开呈现，不把文本相似度包装成录取概率。

> 本项目仅用于辅助初筛，不构成官方报考资格认定。最终请以当年度招录公告、专业目录和招录单位答复为准。

## V3 重点改进

- 修复“法学”误匹配“非法学类 / 不含法学”等专业排除条件
- 修复同省不同地市被错误判为符合户籍限制
- 修复“不限应届毕业生”被识别为仅限应届生
- 新增规则覆盖率；缺少资格字段时不再给出“高度匹配”
- 上传限制为 20 MB、100,000 行、200 列和 30 个工作表
- 导出前中和 `= + - @` 开头的单元格，降低 Excel 公式注入风险
- AI 解读改为明确同意后才发送，并仅发送当前岗位字段与规则检查结果
- 所有岗位表字段在 HTML 展示前转义，避免注入页面
- 重新设计桌面端和移动端界面，默认不预填个人敏感信息
- 提供 12 条无乱码的虚构示例岗位、13 个回归测试和 GitHub Actions CI

## 结果怎么读

- **规则通过度**：全部检查项中，已经由规则判定通过的比例。
- **规则覆盖率**：岗位表中成功识别到的资格字段比例。
- **待核对项**：无法自动判断、字段缺失或需要按官方目录确认的条件。

这些指标都不是报名竞争、进面或录取概率。

## 本地运行

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

也可以直接选择页面中的“示例数据（立即体验）”。示例岗位完全虚构，仅用于验证流程。

## 测试与质量检查

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
ruff format --check .
python -m py_compile app.py govmatch_core.py
```

## 可选 AI 配置

复制 `.streamlit/secrets.toml.example` 为 `.streamlit/secrets.toml`，再填写：

```toml
OPENAI_API_KEY = "你的 OpenAI API Key"
OPENAI_MODEL = "你的账户可用模型名称"
```

不配置 AI 时，规则筛选、岗位对比、咨询话术和 Excel 报告仍可正常使用。不要提交真实密钥。

## 项目结构

```text
GovMatch/
├── app.py
├── govmatch_core.py
├── assets/styles.css
├── sample_jobs.xlsx
├── scripts/build_sample.py
├── tests/test_core.py
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
└── .github/workflows/ci.yml
```

规则集版本当前为 `2026.1`。官方规则来源同时展示在页面和导出的“规则与来源”工作表中；专业名称、代码及应届身份仍应按目标考试当年度口径核对。
