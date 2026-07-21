from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from govmatch_core import (
    APP_VERSION,
    DEGREE_RANK,
    EDU_RANK,
    FIELD_LABELS,
    SERVICE_PROJECTS,
    Check,
    Profile,
    auto_map_columns,
    dataframe_to_excel_bytes,
    evaluate_dataframe,
    generate_consultation_script,
    job_label,
    list_excel_sheets,
    load_demo_file,
    load_tabular_file,
    pending_summary,
    profile_as_dict,
    readable_checks,
    split_terms,
    text,
    value_from_row,
)

APP_NAME = "GovMatch"
APP_SUBTITLE = "公务员岗位智能匹配与报考决策助手"
TEMPLATES = ["自动识别（通用）", "国考", "浙江省考", "上海市考", "事业单位"]


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {max-width: 1120px; padding-top: 1.15rem; padding-bottom: 3rem;}
        h1 {letter-spacing: -0.035em; margin-bottom: .2rem;}
        h2, h3 {letter-spacing: -0.02em;}
        [data-testid="stMetric"] {
            border: 1px solid rgba(49, 51, 63, 0.15);
            border-radius: 14px;
            padding: 0.75rem 0.85rem;
            background: rgba(248, 249, 251, 0.72);
        }
        .hero-note {
            border: 1px solid rgba(49, 51, 63, 0.12);
            border-radius: 14px;
            padding: .85rem 1rem;
            margin: .75rem 0 1.2rem 0;
            background: rgba(240, 246, 255, .65);
        }
        .step-kicker {font-size: .83rem; font-weight: 700; opacity: .72; margin-bottom: .15rem;}
        .job-meta {font-size: .9rem; opacity: .75;}
        .status-good {font-weight: 700;}
        @media (max-width: 640px) {
            .block-container {padding-left: .8rem; padding-right: .8rem; padding-top: .75rem;}
            h1 {font-size: 2.15rem !important;}
            h2 {font-size: 1.55rem !important;}
            h3 {font-size: 1.22rem !important;}
            [data-testid="stMetric"] {padding: .6rem .7rem;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_secret(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, "")


def generate_ai_explanation(profile: Profile, row: dict[str, Any], checks: list[Check]) -> str:
    api_key = get_secret("OPENAI_API_KEY")
    model = get_secret("OPENAI_MODEL")
    if not api_key or not model:
        return "尚未配置 OPENAI_API_KEY 或 OPENAI_MODEL。规则筛选、咨询话术和结果导出不受影响。"

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        payload = {
            "用户条件": profile_as_dict(profile),
            "岗位信息": {key: text(value) for key, value in row.items()},
            "规则检查": [check.__dict__ for check in checks],
        }
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "你是公务员岗位资格初筛助手。只能依据用户提供的岗位表与规则检查结果进行解读，"
                        "不得声称用户一定具备报考资格。请用中文输出：资格结论、匹配依据、待核对事项、"
                        "报考前行动清单。避免讨论录取概率，控制在500字以内。"
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        return response.output_text
    except Exception as exc:
        return f"AI解读暂时失败：{exc}"


def render_profile() -> Profile:
    st.markdown('<div class="step-kicker">STEP 1</div>', unsafe_allow_html=True)
    st.header("填写个人报考条件")
    st.caption("按你准备使用的学历填写主记录；本科与研究生专业不同，可补充第二段学历。")

    with st.container(border=True):
        st.markdown("#### 拟报考学历")
        col1, col2 = st.columns(2)
        education = col1.selectbox("学历", list(EDU_RANK), index=2)
        default_degree = min(max(list(EDU_RANK).index(education), 0), len(DEGREE_RANK) - 1)
        degree = col2.selectbox("学位", list(DEGREE_RANK), index=default_degree)

        major = st.text_input("专业名称", value="行政管理", placeholder="例如：行政管理")
        category = st.text_input("专业类别/一级学科（可填多个）", value="公共管理类", placeholder="例如：公共管理类、公共管理学")

        add_prior = st.toggle("补充另一段学历经历", value=True)
        prior_education = prior_degree = prior_major = prior_category = ""
        if add_prior:
            st.markdown("#### 补充学历")
            p1, p2 = st.columns(2)
            prior_education = p1.selectbox("补充学历层次", list(EDU_RANK), index=1)
            prior_degree = p2.selectbox("补充学位", list(DEGREE_RANK), index=1)
            prior_major = st.text_input("补充学历专业", value="公共事业管理", placeholder="例如：公共事业管理")
            prior_category = st.text_input("补充学历专业类别", value="公共管理类", placeholder="例如：公共管理类")

    with st.container(border=True):
        st.markdown("#### 其他资格条件")
        row1 = st.columns(3)
        political = row1[0].selectbox("政治面貌", ["中共党员", "中共预备党员", "共青团员", "群众", "其他"], index=2)
        gender = row1[1].selectbox("性别", ["男", "女"])
        grassroots_years = row1[2].number_input("基层工作经历（年）", min_value=0, max_value=30, value=0, step=1)

        row2 = st.columns(2)
        service_project = row2[0].selectbox("服务基层项目经历", SERVICE_PROJECTS)
        fresh_graduate = row2[1].toggle("属于公告口径下的应届毕业生", value=True)

        household = st.text_input("户籍/生源地", value="浙江省", placeholder="例如：浙江省嘉兴市；不确定可暂时留空")
        extra_conditions_text = st.text_input(
            "已具备的证书或附加条件",
            placeholder="例如：英语四级、法律职业资格、接受值班（多个用逗号分隔）",
        )
        strict_major = st.toggle(
            "严格专业匹配",
            value=False,
            help="关闭时，未直接匹配会保留为待核对；开启后会直接判为不符合。",
        )

    return Profile(
        education=education,
        degree=degree,
        majors=split_terms(major),
        major_categories=split_terms(category),
        political=political,
        grassroots_years=int(grassroots_years),
        service_project=service_project,
        fresh_graduate=fresh_graduate,
        gender=gender,
        household=household.strip(),
        extra_conditions=split_terms(extra_conditions_text),
        strict_major=strict_major,
        prior_education=prior_education if add_prior else "",
        prior_degree=prior_degree if add_prior else "",
        prior_majors=split_terms(prior_major) if add_prior else [],
        prior_major_categories=split_terms(prior_category) if add_prior else [],
    )


def render_data_source() -> tuple[bytes, str, str] | None:
    st.markdown('<div class="step-kicker">STEP 2</div>', unsafe_allow_html=True)
    st.header("选择岗位数据")

    template = st.selectbox("岗位表类型", TEMPLATES, index=0)
    mode = st.radio(
        "数据来源",
        ["示例数据（立即体验）", "上传官方岗位表"],
        horizontal=True,
    )

    if mode == "示例数据（立即体验）":
        file_bytes, filename = load_demo_file(PROJECT_DIR)
        st.success("已加载12条虚构示例岗位，可直接体验完整流程。")
        st.download_button(
            "下载示例岗位表",
            data=file_bytes,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        return file_bytes, filename, template

    uploaded = st.file_uploader(
        "上传国考、省考、事业单位岗位表",
        type=["xlsx", "xls", "csv"],
        help="支持常见 Excel/CSV。复杂合并表头可在读取后手动校正字段。",
    )
    if uploaded is None:
        st.info("上传官方岗位表后，系统会自动识别表头与字段。")
        return None
    return uploaded.getvalue(), uploaded.name, template


def render_mapping_editor(df: pd.DataFrame, detected: dict[str, str | None]) -> dict[str, str | None]:
    options = ["— 不使用此字段 —", *list(df.columns)]
    final_mapping: dict[str, str | None] = {}
    with st.expander("字段识别与手动校正", expanded=False):
        st.caption("自动识别不准确时，在这里指定岗位表中的真实列名。")
        columns = st.columns(3)
        for index, role in enumerate(FIELD_LABELS):
            detected_column = detected.get(role)
            default_index = options.index(detected_column) if detected_column in options else 0
            selected = columns[index % 3].selectbox(
                FIELD_LABELS[role], options, index=default_index, key=f"mapping_{role}"
            )
            final_mapping[role] = None if selected.startswith("—") else selected
    return final_mapping


def load_dataframe(file_bytes: bytes, filename: str, template: str) -> tuple[pd.DataFrame, str | int] | None:
    sheet_name: str | int = 0
    try:
        sheets = list_excel_sheets(file_bytes, filename)
        if sheets:
            sheet_name = st.selectbox("选择工作表", sheets)
        df = load_tabular_file(file_bytes, filename, sheet_name=sheet_name, template=template)
    except Exception as exc:
        st.error(f"岗位表读取失败：{exc}")
        return None

    if df.empty:
        st.error("岗位表中没有识别到有效数据。")
        return None
    st.success(f"已读取 {len(df):,} 条记录、{len(df.columns)} 个字段。")
    return df, sheet_name


def apply_text_filter(df: pd.DataFrame, column: str | None, keyword: str) -> pd.DataFrame:
    if not keyword or not column:
        return df
    return df[df[column].astype(str).str.contains(keyword, case=False, na=False, regex=False)]


def build_label_index(df: pd.DataFrame, mapping: dict[str, str | None]) -> dict[str, int]:
    labels: dict[str, int] = {}
    for index, row in df.iterrows():
        base = job_label(row, mapping, fallback=f"第{index + 1}行")
        label = base
        counter = 2
        while label in labels:
            label = f"{base}（{counter}）"
            counter += 1
        labels[label] = index
    return labels


def render_job_card(row: pd.Series, checks: list[Check], mapping: dict[str, str | None]) -> None:
    title = text(value_from_row(row, mapping, "job_title")) or "未命名岗位"
    department = text(value_from_row(row, mapping, "department")) or "未识别招录机关"
    location = text(value_from_row(row, mapping, "location")) or "地点未识别"
    count = text(value_from_row(row, mapping, "recruit_count")) or "1"
    code = text(value_from_row(row, mapping, "job_code"))

    with st.container(border=True):
        st.markdown(f"#### {title}")
        st.markdown(
            f'<div class="job-meta">{department} · {location}{f" · {code}" if code else ""}</div>',
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("资格匹配度", f"{int(row['资格匹配度'])}%")
        c2.metric("招考人数", count)
        c3.metric("待核对项", int(row["待核对项数"]))
        st.write(f"**{row['资格标签']}**｜{pending_summary(checks)}")


def render_results(
    result_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    details: dict[int, list[Check]],
    mapping: dict[str, str | None],
    profile: Profile,
) -> None:
    st.markdown('<div class="step-kicker">STEP 4</div>', unsafe_allow_html=True)
    st.header("查看匹配结果")

    total = len(summary_df)
    matched = int((summary_df["资格结论"] == "资格初筛匹配").sum())
    pending = int((summary_df["资格结论"] == "存在待核对项").sum())
    failed = int((summary_df["资格结论"] == "明确不符合").sum())
    metrics = st.columns(4)
    metrics[0].metric("参与匹配", total)
    metrics[1].metric("初筛匹配", matched)
    metrics[2].metric("待人工核对", pending)
    metrics[3].metric("明确不符合", failed)

    st.caption("资格匹配度仅反映已填写条件的规则匹配情况，不代表报名竞争、进面概率或录取概率。")

    tab_cards, tab_table, tab_compare, tab_contact = st.tabs(["推荐岗位", "完整结果", "岗位对比", "咨询话术"])

    with tab_cards:
        candidates = result_df[result_df["资格结论"] != "明确不符合"].head(6)
        if candidates.empty:
            st.warning("当前条件下没有非明确不符合岗位。可检查专业、学历或筛选条件。")
        else:
            st.markdown("#### 优先查看")
            for index, row in candidates.iterrows():
                render_job_card(row, details[index], mapping)

    with tab_table:
        front = ["资格结论", "资格匹配度", "资格标签", "待核对项数", "不符合项数"]
        job_columns = [
            mapping.get("department"), mapping.get("job_title"), mapping.get("job_code"),
            mapping.get("location"), mapping.get("recruit_count"), mapping.get("major"),
            mapping.get("education"), mapping.get("remarks"),
        ]
        ordered = front + [column for column in job_columns if column and column not in front]
        ordered += [column for column in result_df.columns if column not in ordered and column != "匹配说明"]
        st.dataframe(
            result_df[ordered],
            width="stretch",
            hide_index=True,
            height=520,
            column_config={
                "资格匹配度": st.column_config.ProgressColumn("资格匹配度", min_value=0, max_value=100, format="%d%%"),
                "待核对项数": st.column_config.NumberColumn("待核对项", format="%d"),
                "不符合项数": st.column_config.NumberColumn("不符合项", format="%d"),
            },
        )

        export_bytes = dataframe_to_excel_bytes(result_df, profile)
        st.download_button(
            "下载完整匹配报告 Excel",
            data=export_bytes,
            file_name="GovMatch_V2_岗位匹配报告.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )

        labels = build_label_index(result_df, mapping)
        selected_label = st.selectbox("查看单个岗位的逐项判断", list(labels), key="detail_job")
        selected_index = labels[selected_label]
        st.dataframe(readable_checks(details[selected_index]), width="stretch", hide_index=True)

        if st.button("生成 AI 岗位解读", width="stretch"):
            with st.spinner("正在生成岗位解读……"):
                selected_row = result_df.loc[selected_index]
                explanation = generate_ai_explanation(
                    profile,
                    {key: selected_row[key] for key in selected_row.index if key not in {"匹配说明"}},
                    details[selected_index],
                )
            st.markdown(explanation)

    with tab_compare:
        labels = build_label_index(result_df, mapping)
        selected = st.multiselect("选择2—3个岗位进行对比", list(labels), max_selections=3)
        if selected:
            rows = []
            for label in selected:
                index = labels[label]
                row = result_df.loc[index]
                rows.append({
                    "岗位": label,
                    "招录机关": text(value_from_row(row, mapping, "department")),
                    "工作地点": text(value_from_row(row, mapping, "location")),
                    "招考人数": text(value_from_row(row, mapping, "recruit_count")),
                    "学历要求": text(value_from_row(row, mapping, "education")),
                    "专业要求": text(value_from_row(row, mapping, "major")),
                    "资格标签": row["资格标签"],
                    "资格匹配度": f"{int(row['资格匹配度'])}%",
                    "待核对项": pending_summary(details[index]),
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        else:
            st.info("从上方选择岗位后，这里会并排展示关键条件。")

    with tab_contact:
        labels = build_label_index(result_df, mapping)
        selected_label = st.selectbox("选择需要咨询的岗位", list(labels), key="contact_job")
        selected_index = labels[selected_label]
        script = generate_consultation_script(
            profile, result_df.loc[selected_index], mapping, details[selected_index]
        )
        st.text_area("招录单位咨询话术", value=script, height=280)
        st.download_button(
            "下载咨询话术 TXT",
            data=script.encode("utf-8"),
            file_name="GovMatch_招录单位咨询话术.txt",
            mime="text/plain",
            width="stretch",
        )


def main() -> None:
    st.set_page_config(page_title=f"{APP_NAME}｜公务员岗位匹配", page_icon="🏛️", layout="wide")
    inject_css()

    st.title(f"🏛️ {APP_NAME}")
    st.subheader(APP_SUBTITLE)
    st.caption(f"V{APP_VERSION} · 手机端优化 · 多学历专业匹配 · 咨询话术生成")
    st.markdown(
        """
        <div class="hero-note">
        本工具用于资格机器初筛，不构成官方报考资格认定。专业目录、应届身份、户籍生源和备注条件，
        必须以当年度招录公告、专业指导目录及招录单位答复为准。
        </div>
        """,
        unsafe_allow_html=True,
    )

    profile = render_profile()
    st.divider()

    source = render_data_source()
    if source is None:
        st.stop()
    file_bytes, filename, template = source

    loaded = load_dataframe(file_bytes, filename, template)
    if loaded is None:
        st.stop()
    df, _ = loaded

    detected = auto_map_columns(df.columns, template=template)
    mapping = render_mapping_editor(df, detected)
    missing = [FIELD_LABELS[role] for role in ["job_title", "major", "education"] if not mapping.get(role)]
    if missing:
        st.error(f"至少需要识别这些字段：{'、'.join(missing)}。请展开“字段识别与手动校正”进行指定。")
        st.stop()

    st.divider()
    st.markdown('<div class="step-kicker">STEP 3</div>', unsafe_allow_html=True)
    st.header("设置筛选范围")
    f1, f2, f3 = st.columns(3)
    location_keyword = f1.text_input("工作地点包含", placeholder="例如：杭州、浙江")
    department_keyword = f2.text_input("招录机关包含", placeholder="例如：税务、街道")
    general_keyword = f3.text_input("职位/备注关键词", placeholder="例如：综合管理、文字")

    working_df = apply_text_filter(df, mapping.get("location"), location_keyword)
    working_df = apply_text_filter(working_df, mapping.get("department"), department_keyword)

    if general_keyword:
        searchable = [
            column for column in [mapping.get("job_title"), mapping.get("remarks"), mapping.get("major")]
            if column
        ]
        if searchable:
            mask = pd.Series(False, index=working_df.index)
            for column in searchable:
                mask = mask | working_df[column].astype(str).str.contains(
                    general_keyword, case=False, na=False, regex=False
                )
            working_df = working_df[mask]

    if working_df.empty:
        st.warning("当前筛选范围内没有岗位。")
        st.stop()

    full_result_df, details = evaluate_dataframe(working_df, mapping, profile)
    result_df = full_result_df.copy()

    status_filter = st.multiselect(
        "显示哪些资格结论",
        ["资格初筛匹配", "存在待核对项", "明确不符合"],
        default=["资格初筛匹配", "存在待核对项"],
    )
    if status_filter:
        result_df = result_df[result_df["资格结论"].isin(status_filter)].copy()
    result_df = result_df.sort_values(
        ["不符合项数", "待核对项数", "资格匹配度"], ascending=[True, True, False]
    )

    if result_df.empty:
        st.warning("没有符合当前资格结论筛选的岗位。")
        st.stop()

    st.divider()
    render_results(result_df, full_result_df, details, mapping, profile)

    with st.expander("项目说明与 AI 配置"):
        st.write(
            "GovMatch V2 将资格判断与录取概率明确分开：系统只做资格条件匹配，不预测竞争比或进面概率。"
        )
        st.code(
            'OPENAI_API_KEY = "你的 OpenAI API Key"\nOPENAI_MODEL = "你的账户可用模型名称"',
            language="toml",
        )
        st.caption("AI 为可选功能；不配置时，规则筛选、岗位对比、咨询话术和 Excel 报告均可正常使用。")


if __name__ == "__main__":
    main()
