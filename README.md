# GovMatch｜公务员岗位智能匹配与报考决策助手

GovMatch 是一个基于 **Streamlit + Pandas + 规则引擎 + 可选 OpenAI API** 的岗位表分析工具。

它可以读取国考、省考、事业单位等 Excel/CSV 岗位表，根据用户填写的学历、专业、政治面貌、基层经历、应届身份等条件，对岗位进行机器初筛。

> 重要说明：本项目只用于辅助筛选，不构成官方报考资格认定。最终必须以当年度招录公告、专业指导目录和招录单位答复为准。

## 已实现功能

- 上传 `.xlsx`、`.xls`、`.csv` 岗位表
- 自动识别标题行和常见字段
- 特殊格式可手动校正字段映射
- 学历、学位、专业、政治面貌、基层经历等规则匹配
- 输出“初筛可报 / 需人工确认 / 不可报”
- 生成匹配分和相对候选分层
- 按工作地点、招录机关继续筛选
- 查看单个岗位每一项的判断理由
- 导出 Excel 匹配结果
- 可选接入 OpenAI Responses API 生成岗位解读
- 未配置 OpenAI Key 时仍可完整使用规则筛选

## 项目结构

```text
GovMatch/
├── app.py
├── requirements.txt
├── requirements-dev.txt
├── sample_jobs.xlsx
├── README.md
├── .gitignore
├── .streamlit/
│   └── secrets.toml.example
└── tests/
    ├── conftest.py
    └── test_core.py
```

## 本地运行

需要 Python 3.11 或更高版本。

```bash
pip install -r requirements.txt
streamlit run app.py
```

浏览器会自动打开本地页面。也可以用项目附带的 `sample_jobs.xlsx` 测试。

## 部署到 Streamlit Community Cloud

1. 在 GitHub 新建仓库，例如 `GovMatch`
2. 上传本项目全部文件
3. 打开 Streamlit Community Cloud
4. 选择 GitHub 仓库
5. Main file path 填写：

```text
app.py
```

6. 点击 Deploy

部署成功后，手机浏览器也能直接使用。

## 可选：配置 OpenAI API

规则筛选不需要 API。只有“生成 AI 岗位解读”功能需要。

在 Streamlit Cloud 的 **App settings → Secrets** 中添加：

```toml
OPENAI_API_KEY = "你的 OpenAI API Key"
OPENAI_MODEL = "你的账户可用模型名称"
```

不要把真实 Key 直接写入 `app.py` 或上传到 GitHub。

## 测试

```bash
pip install -r requirements-dev.txt
pytest -q
```

## 匹配逻辑说明

GovMatch 将每个岗位拆分为以下检查项：

- 学历
- 学位
- 专业
- 政治面貌
- 基层工作经历
- 服务基层项目经历
- 应届身份
- 性别
- 备注中的额外条件

其中专业匹配最容易受到官方专业目录、专业代码和上位专业类别影响。因此默认模式下，未直接匹配的专业会标记为“需人工确认”；开启“严格专业匹配”后才会直接判为“不可报”。

“稳妥候选 / 重点候选 / 冲刺候选”仅是项目内部的相对分层，不代表真实报名人数、竞争比或录取概率。

## 后续升级方向

- 接入历年岗位库和报名人数数据
- 保存个人画像和收藏岗位
- 对比不同年份、地区的岗位数量变化
- 自动读取公告 PDF 与专业指导目录
- 增加国考、浙江省考、上海市考专用规则模板
- 增加多智能体：资格审查、岗位推荐、报考策略、面试规划
