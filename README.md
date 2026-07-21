# GovMatch V2｜公务员岗位智能匹配与报考决策助手

GovMatch V2 是一个基于 **Streamlit + Pandas + 规则引擎 + 可选 OpenAI API** 的公务员岗位表分析工具。

它将“资格匹配”与“录取概率”明确区分：系统只根据用户填写的学历、专业、政治面貌、户籍、基层经历等条件进行机器初筛，不预测报名竞争、进面或录取概率。

> 本项目仅用于辅助筛选，不构成官方报考资格认定。最终必须以当年度招录公告、专业指导目录和招录单位答复为准。

## V2 新增与优化

- 手机端主页面四步式流程，不再依赖侧边栏
- 一键加载虚构示例岗位，无需先上传文件
- 支持“报考学历 + 补充学历”两段教育经历
- 区分主学历专业匹配与其他学历专业匹配
- 增加户籍/生源条件检查
- 增加国考、浙江省考、上海市考、事业单位解析模板入口
- 将“稳妥/冲刺”改为资格匹配标签，避免误导为录取概率
- 推荐岗位卡片、完整结果、岗位对比、咨询话术四个视图
- 自动生成招录单位资格咨询话术
- Excel 报告同时导出岗位结果与个人条件
- AI 解读仍为可选配置；没有 API Key 也能完整使用核心功能
- 核心规则拆分到 `govmatch_core.py`，便于测试与后续维护

## 项目结构

```text
GovMatch_V2/
├── app.py
├── govmatch_core.py
├── requirements.txt
├── requirements-dev.txt
├── sample_jobs.xlsx
├── README.md
├── .gitignore
├── .streamlit/
│   └── secrets.toml.example
└── tests/
    └── test_core.py
```

## 替换现有 GitHub 项目

将以下文件上传到你现有的 `GovMatch` 仓库根目录并覆盖旧文件：

```text
app.py
govmatch_core.py
requirements.txt
README.md
sample_jobs.xlsx
```

Streamlit Community Cloud 通常会检测 GitHub 更新并自动重新部署。Main file path 仍然是：

```text
app.py
```

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 可选：配置 OpenAI API

在 Streamlit Cloud 的 App settings → Secrets 中添加：

```toml
OPENAI_API_KEY = "你的 OpenAI API Key"
OPENAI_MODEL = "你的账户可用模型名称"
```

不要把真实 Key 写入代码或上传到 GitHub。

## 测试

```bash
pip install -r requirements-dev.txt
pytest -q
```

## 下一阶段建议

- 接入官方本科与研究生专业目录数据
- 增加专业代码与新旧专业名称映射
- 为真实浙江省考岗位表建立专项回归测试
- 增加收藏岗位与用户本地配置保存
- 接入历年报名人数、进面分数后，再单独建立“竞争风险”模块
