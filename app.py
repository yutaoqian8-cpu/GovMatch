from __future__ import annotations

import io
import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

import pandas as pd
import streamlit as st


APP_NAME = "GovMatch"
APP_SUBTITLE = "公务员岗位智能匹配与报考决策助手"

COLUMN_ALIASES: dict[str, list[str]] = {
    "department": ["招录机关", "部门名称", "单位名称", "招考单位", "机关", "部门"],
    "office": ["用人司局", "用人单位", "招录单位", "内设机构", "司局"],
    "job_title": ["招考职位", "职位名称", "岗位名称", "职位", "岗位"],
    "job_code": ["职位代码", "岗位代码", "招考职位代码", "职位编号", "岗位编号"],
    "recruit_count": ["招考人数", "计划招录人数", "招录人数", "招聘人数", "人数"],
    "major": ["专业", "专业要求", "所学专业", "专业类别", "专业限制"],
    "education": ["学历", "学历要求", "最低学历"],
    "degree": ["学位", "学位要求"],
    "political": ["政治面貌", "政治面貌要求"],
    "grassroots": ["基层工作最低年限", "基层工作年限", "基层经历年限", "工作年限"],
    "service_project": ["服务基层项目工作经历", "服务基层项目", "基层项目经历"],
    "fresh_graduate": ["是否限应届毕业生", "应届毕业生", "应届要求", "招录对象"],
    "gender": ["性别", "性别要求"],
    "location": ["工作地点", "工作地", "职位工作地点", "地区", "所在地", "落户地点"],
    "remarks": ["备注", "其他条件", "补充条件", "说明"],
}

FIELD_LABELS = {
    "department": "招录机关",
    "office": "用人司局",
    "job_title": "职位名称",
    "job_code": "职位代码",
    "recruit_count": "招考人数",
    "major": "专业要求",
    "education": "学历要求",
    "degree": "学位要求",
    "political": "政治面貌",
    "grassroots": "基层工作年限",
    "service_project": "服务基层项目",
    "fresh_graduate": "应届要求",
    "gender": "性别要求",
    "location": "工作地点",
    "remarks": "备注",
}

EDU_RANK = {"大专": 1, "本科": 2, "硕士研究生": 3, "博士研究生": 4}
DEGREE_RANK = {"无学位": 0, "学士": 1, "硕士": 2, "博士": 3}

UNLIMITED_WORDS = (
    "不限", "无限制", "无要求", "不作要求", "不限制", "均可", "否", "无",
)

SERVICE_PROJECTS = [
    "无",
    "大学生村官",
    "三支一扶",
    "西部计划",
    "特岗教师",
    "退役大学生士兵",
    "其他",
]

RISK_KEYWORDS = [
    "户籍", "生源", "资格证", "职业资格", "英语", "四级", "六级", "法律职业资格",
    "司法考试", "会计", "计算机等级", "普通话", "最低服务年限", "夜班", "值班",
    "体能", "视力", "工作经历", "相关经历", "面向", "证书",
]

CHINESE_NUMBERS = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


@dataclass
class Profile:
    education: str
    degree: str
    majors: list[str]
    major_categories: list[str]
    political: str
    grassroots_years: int
    service_project: str
    fresh_graduate: bool
    gender: str
    strict_major: bool = False


@dataclass
class Check:
    field: str
    status: str  # pass / fail / uncertain
    reason: str


def text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def compact(value: Any) -> str:
    return re.sub(r"[\s\u3000,，;；、/（）()【】\[\]：:·\-—_]+", "", text(value)).lower()


def is_unlimited(value: Any) -> bool:
    value_text = text(value)
    if not value_text:
        return True
    normalized = compact(value_text)
    return any(compact(word) == normalized for word in UNLIMITED_WORDS) or "专业不限" in value_text


def split_terms(value: str) -> list[str]:
    terms = re.split(r"[,，;；、/\n]+", value or "")
    return [item.strip() for item in terms if item.strip()]


def normalize_column_name(value: Any) -> str:
    return re.sub(r"[\s\n\r\t（）()【】\[\]：:]+", "", text(value)).lower()


def detect_header_row(raw: pd.DataFrame, max_rows: int = 20) -> int:
    keywords = {
        normalize_column_name(alias)
        for aliases in COLUMN_ALIASES.values()
        for alias in aliases
    }
    best_row = 0
    best_score = -1
    for idx in range(min(max_rows, len(raw))):
        row_values = [normalize_column_name(v) for v in raw.iloc[idx].tolist()]
        score = 0
        for cell in row_values:
            if not cell:
                continue
            if cell in keywords:
                score += 3
            elif any(k and (k in cell or cell in k) for k in keywords):
                score += 1
        if score > best_score:
            best_score = score
            best_row = idx
    return best_row


def read_csv_flexible(file_bytes: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030", "gbk", "utf-8"):
        try:
            return pd.read_csv(io.BytesIO(file_bytes), encoding=encoding)
        except Exception as exc:  # pragma: no cover - fallback chain
            last_error = exc
    raise ValueError(f"CSV读取失败：{last_error}")


def load_tabular_file(file_bytes: bytes, filename: str, sheet_name: str | int | None = 0) -> pd.DataFrame:
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix == "csv":
        df = read_csv_flexible(file_bytes)
    elif suffix in {"xlsx", "xls"}:
        buffer = io.BytesIO(file_bytes)
        raw = pd.read_excel(buffer, sheet_name=sheet_name, header=None, dtype=object)
        header_row = detect_header_row(raw)
        buffer.seek(0)
        df = pd.read_excel(buffer, sheet_name=sheet_name, header=header_row, dtype=object)
    else:
        raise ValueError("仅支持 .xlsx、.xls 和 .csv 文件。")

    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all").copy()
    df.columns = [text(c) or f"未命名列_{i+1}" for i, c in enumerate(df.columns)]
    return df.reset_index(drop=True)


def list_excel_sheets(file_bytes: bytes, filename: str) -> list[str]:
    if not filename.lower().endswith((".xlsx", ".xls")):
        return []
    excel = pd.ExcelFile(io.BytesIO(file_bytes))
    return excel.sheet_names


def auto_map_columns(columns: Iterable[str]) -> dict[str, str | None]:
    columns = list(columns)
    normalized = {col: normalize_column_name(col) for col in columns}
    mapping: dict[str, str | None] = {}
    for role, aliases in COLUMN_ALIASES.items():
        alias_norms = [normalize_column_name(a) for a in aliases]
        exact = next((col for col, norm in normalized.items() if norm in alias_norms), None)
        if exact:
            mapping[role] = exact
            continue
        fuzzy = next(
            (
                col for col, norm in normalized.items()
                if any(alias and (alias in norm or norm in alias) for alias in alias_norms)
            ),
            None,
        )
        mapping[role] = fuzzy
    return mapping


def extract_years(requirement: Any) -> int | None:
    value = text(requirement)
    if not value or is_unlimited(value):
        return 0
    digit = re.search(r"(\d+)\s*年", value)
    if digit:
        return int(digit.group(1))
    for char, number in CHINESE_NUMBERS.items():
        if f"{char}年" in value:
            return number
    return None


def check_education(requirement: Any, user_value: str) -> Check:
    req = text(requirement)
    if is_unlimited(req):
        return Check("学历", "pass", "学历不限")
    user_rank = EDU_RANK[user_value]

    min_patterns = [
        ("大专及以上", 1), ("专科及以上", 1),
        ("本科及以上", 2), ("大学本科及以上", 2),
        ("硕士研究生及以上", 3), ("研究生及以上", 3),
        ("博士研究生及以上", 4),
    ]
    for pattern, min_rank in min_patterns:
        if pattern in req:
            if user_rank >= min_rank:
                return Check("学历", "pass", f"用户学历满足“{pattern}”")
            return Check("学历", "fail", f"要求{pattern}，用户为{user_value}")

    allowed: set[int] = set()
    if "大专" in req or "专科" in req:
        allowed.add(1)
    if "本科" in req:
        allowed.add(2)
    if "硕士" in req or ("研究生" in req and "博士" not in req):
        allowed.add(3)
    if "博士" in req:
        allowed.add(4)

    if allowed:
        if user_rank in allowed:
            return Check("学历", "pass", f"用户学历在允许范围：{req}")
        return Check("学历", "fail", f"学历要求为“{req}”，用户为{user_value}")
    return Check("学历", "uncertain", f"无法自动解析学历要求“{req}”")


def check_degree(requirement: Any, user_value: str) -> Check:
    req = text(requirement)
    if is_unlimited(req):
        return Check("学位", "pass", "学位不限")
    user_rank = DEGREE_RANK[user_value]

    if "与最高学历相对应" in req or "相应学位" in req:
        if user_rank > 0:
            return Check("学位", "pass", "具备学位，仍需核对是否与最高学历对应")
        return Check("学位", "fail", "岗位要求与最高学历相对应的学位")

    required_rank = None
    if "博士" in req:
        required_rank = 3
    elif "硕士" in req:
        required_rank = 2
    elif "学士" in req:
        required_rank = 1

    if required_rank is None:
        return Check("学位", "uncertain", f"无法自动解析学位要求“{req}”")
    if "及以上" in req:
        passed = user_rank >= required_rank
    else:
        passed = user_rank == required_rank or user_rank > required_rank
    if passed:
        return Check("学位", "pass", f"用户学位满足“{req}”")
    return Check("学位", "fail", f"要求“{req}”，用户为{user_value}")


def check_major(requirement: Any, profile: Profile) -> Check:
    req = text(requirement)
    if is_unlimited(req):
        return Check("专业", "pass", "专业不限")

    req_compact = compact(req)
    candidates = [*profile.majors, *profile.major_categories]
    candidate_compact = [compact(v) for v in candidates if compact(v)]

    direct = [original for original, norm in zip(candidates, candidate_compact) if norm and norm in req_compact]
    if direct:
        return Check("专业", "pass", f"直接匹配：{direct[0]}")

    # 去除常见后缀后进行较弱匹配，只标记为待确认。
    weak_tokens: list[str] = []
    for item in candidates:
        norm = compact(item)
        norm = re.sub(r"(专业|学类|类|学)$", "", norm)
        if len(norm) >= 3 and norm in req_compact:
            weak_tokens.append(item)
    if weak_tokens:
        return Check("专业", "uncertain", f"疑似匹配“{weak_tokens[0]}”，需按官方专业目录核对")

    status = "fail" if profile.strict_major else "uncertain"
    reason = (
        f"未发现用户专业与“{req}”的直接文本匹配"
        + ("（已启用严格模式）" if profile.strict_major else "，可能存在专业代码或上位专业类别关系")
    )
    return Check("专业", status, reason)


def check_political(requirement: Any, user_value: str) -> Check:
    req = text(requirement)
    if is_unlimited(req):
        return Check("政治面貌", "pass", "政治面貌不限")

    if "中共党员" in req:
        if user_value == "中共党员":
            return Check("政治面貌", "pass", "符合中共党员要求")
        if user_value == "中共预备党员":
            if "预备" in req or "含预备党员" in req:
                return Check("政治面貌", "pass", "岗位明确包含中共预备党员")
            return Check("政治面貌", "uncertain", "岗位写明中共党员，但未明确是否包含预备党员")
        if "或共青团员" in req and user_value == "共青团员":
            return Check("政治面貌", "pass", "符合党员或共青团员要求")
        return Check("政治面貌", "fail", f"要求“{req}”，用户为{user_value}")

    if "共青团员" in req:
        if user_value in {"共青团员", "中共党员", "中共预备党员"}:
            return Check("政治面貌", "pass", "符合政治面貌要求")
        return Check("政治面貌", "fail", f"要求“{req}”，用户为{user_value}")

    if user_value in req:
        return Check("政治面貌", "pass", "政治面貌直接匹配")
    return Check("政治面貌", "uncertain", f"无法自动判断“{req}”")


def check_grassroots(requirement: Any, user_years: int) -> Check:
    req = text(requirement)
    needed = extract_years(req)
    if needed == 0:
        return Check("基层经历", "pass", "基层工作经历不限")
    if needed is None:
        return Check("基层经历", "uncertain", f"无法自动解析“{req}”")
    if user_years >= needed:
        return Check("基层经历", "pass", f"要求至少{needed}年，用户为{user_years}年")
    return Check("基层经历", "fail", f"要求至少{needed}年，用户仅{user_years}年")


def check_service_project(requirement: Any, user_value: str) -> Check:
    req = text(requirement)
    if is_unlimited(req) or "无限制" in req:
        return Check("服务基层项目", "pass", "服务基层项目经历不限")
    if user_value == "无":
        return Check("服务基层项目", "fail", f"岗位要求“{req}”")
    if user_value in req or "服务基层项目人员" in req:
        return Check("服务基层项目", "pass", f"用户经历与“{req}”匹配")
    return Check("服务基层项目", "uncertain", f"用户经历为{user_value}，岗位要求“{req}”")


def check_fresh_graduate(requirement: Any, is_fresh: bool) -> Check:
    req = text(requirement)
    if is_unlimited(req):
        return Check("应届身份", "pass", "未限制应届身份")
    if any(k in req for k in ["应届", "高校毕业生", "2026届", "2027届"]):
        if is_fresh:
            return Check("应届身份", "pass", "用户选择了应届身份")
        return Check("应届身份", "fail", f"岗位要求“{req}”")
    if any(k in req for k in ["社会人员", "非应届"]):
        if not is_fresh:
            return Check("应届身份", "pass", "符合社会人员/非应届要求")
        return Check("应届身份", "uncertain", f"岗位面向“{req}”，需确认应届生是否可报")
    return Check("应届身份", "uncertain", f"无法自动解析“{req}”")


def check_gender(requirement: Any, user_value: str) -> Check:
    req = text(requirement)
    if is_unlimited(req) or "男女不限" in req:
        return Check("性别", "pass", "性别不限")
    req_compact = compact(req)
    if ("男性" in req or req_compact in {"男", "限男"}) and user_value != "男":
        return Check("性别", "fail", "岗位限男性")
    if ("女性" in req or req_compact in {"女", "限女"}) and user_value != "女":
        return Check("性别", "fail", "岗位限女性")
    if (
        ("男性" in req and user_value == "男")
        or ("女性" in req and user_value == "女")
        or req_compact == user_value
    ):
        return Check("性别", "pass", "性别符合要求")
    return Check("性别", "uncertain", f"无法自动解析“{req}”")


def check_remarks(requirement: Any) -> Check:
    req = text(requirement)
    if not req or is_unlimited(req):
        return Check("备注", "pass", "未发现额外备注条件")
    hits = [keyword for keyword in RISK_KEYWORDS if keyword in req]
    if hits:
        return Check("备注", "uncertain", f"备注含额外条件：{'、'.join(hits[:4])}")
    return Check("备注", "uncertain", "岗位存在备注信息，请人工阅读")


def value_from_row(row: pd.Series, mapping: dict[str, str | None], role: str) -> Any:
    col = mapping.get(role)
    return row.get(col, "") if col else ""


def parse_recruit_count(value: Any) -> int:
    match = re.search(r"\d+", text(value))
    return int(match.group()) if match else 1


def evaluate_job(
    row: pd.Series,
    mapping: dict[str, str | None],
    profile: Profile,
) -> tuple[str, int, str, list[Check]]:
    checks = [
        check_education(value_from_row(row, mapping, "education"), profile.education),
        check_degree(value_from_row(row, mapping, "degree"), profile.degree),
        check_major(value_from_row(row, mapping, "major"), profile),
        check_political(value_from_row(row, mapping, "political"), profile.political),
        check_grassroots(value_from_row(row, mapping, "grassroots"), profile.grassroots_years),
        check_service_project(value_from_row(row, mapping, "service_project"), profile.service_project),
        check_fresh_graduate(value_from_row(row, mapping, "fresh_graduate"), profile.fresh_graduate),
        check_gender(value_from_row(row, mapping, "gender"), profile.gender),
        check_remarks(value_from_row(row, mapping, "remarks")),
    ]

    if any(c.status == "fail" for c in checks):
        overall = "不可报"
    elif any(c.status == "uncertain" for c in checks):
        overall = "需人工确认"
    else:
        overall = "初筛可报"

    if overall == "不可报":
        score = 0
        tier = "不符合"
    else:
        pass_count = sum(c.status == "pass" for c in checks)
        uncertain_count = sum(c.status == "uncertain" for c in checks)
        recruit_count = parse_recruit_count(value_from_row(row, mapping, "recruit_count"))
        restrictive_passes = sum(
            c.status == "pass" and c.field in {"政治面貌", "基层经历", "服务基层项目", "应届身份", "性别"}
            and "不限" not in c.reason and "未限制" not in c.reason
            for c in checks
        )
        score = 52 + pass_count * 4 + min(recruit_count, 5) * 2 + restrictive_passes * 2 - uncertain_count * 5
        score = max(1, min(100, score))

        if overall == "需人工确认":
            tier = "人工核对"
        elif score >= 88 and recruit_count >= 2:
            tier = "稳妥候选"
        elif score >= 76:
            tier = "重点候选"
        else:
            tier = "冲刺候选"

    reasons = "；".join(f"{c.field}：{c.reason}" for c in checks if c.status != "pass")
    if not reasons:
        reasons = "各项已填写条件均通过规则初筛"
    return overall, score, tier, checks


def evaluate_dataframe(
    df: pd.DataFrame,
    mapping: dict[str, str | None],
    profile: Profile,
) -> tuple[pd.DataFrame, dict[int, list[Check]]]:
    output = df.copy()
    statuses: list[str] = []
    scores: list[int] = []
    tiers: list[str] = []
    reason_texts: list[str] = []
    details: dict[int, list[Check]] = {}

    for idx, row in output.iterrows():
        status, score, tier, checks = evaluate_job(row, mapping, profile)
        statuses.append(status)
        scores.append(score)
        tiers.append(tier)
        reason_texts.append("；".join(
            f"{c.field}[{c.status}]：{c.reason}" for c in checks
        ))
        details[idx] = checks

    output.insert(0, "匹配结论", statuses)
    output.insert(1, "匹配分", scores)
    output.insert(2, "相对分层", tiers)
    output.insert(3, "匹配说明", reason_texts)
    return output, details


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="岗位匹配结果")
        ws = writer.book["岗位匹配结果"]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.font = cell.font.copy(bold=True)
        widths = {
            "A": 12, "B": 10, "C": 12, "D": 55,
        }
        for col, width in widths.items():
            ws.column_dimensions[col].width = width
    return buffer.getvalue()


def get_secret(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, "")


def generate_ai_explanation(
    profile: Profile,
    row: dict[str, Any],
    checks: list[Check],
) -> str:
    api_key = get_secret("OPENAI_API_KEY")
    model = get_secret("OPENAI_MODEL")
    if not api_key or not model:
        return "未配置 OPENAI_API_KEY 或 OPENAI_MODEL。当前规则解释已可正常使用。"

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        payload = {
            "用户条件": asdict(profile),
            "岗位信息": {k: text(v) for k, v in row.items()},
            "规则检查": [asdict(c) for c in checks],
        }
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "你是公务员岗位资格初筛助手。只能依据用户提供的岗位表和规则检查结果解读，"
                        "不得声称用户一定具有报考资格。用中文输出：结论、关键匹配点、必须人工核对项、"
                        "报考前行动清单。控制在500字以内。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
        )
        return response.output_text
    except Exception as exc:
        return f"AI解读暂时失败：{exc}"


def render_mapping_editor(df: pd.DataFrame, detected: dict[str, str | None]) -> dict[str, str | None]:
    options = ["— 不使用此字段 —", *list(df.columns)]
    final_mapping: dict[str, str | None] = {}
    with st.expander("字段识别与手动校正", expanded=False):
        st.caption("系统会自动识别列名。岗位表格式特殊时，可在这里手动指定。")
        cols = st.columns(3)
        for index, role in enumerate(COLUMN_ALIASES):
            detected_col = detected.get(role)
            default_index = options.index(detected_col) if detected_col in options else 0
            selected = cols[index % 3].selectbox(
                FIELD_LABELS[role],
                options,
                index=default_index,
                key=f"mapping_{role}",
            )
            final_mapping[role] = None if selected.startswith("—") else selected
    return final_mapping


def main() -> None:
    st.set_page_config(page_title=f"{APP_NAME}｜公务员岗位匹配", page_icon="🏛️", layout="wide")

    st.title(f"🏛️ {APP_NAME}")
    st.subheader(APP_SUBTITLE)
    st.info(
        "本工具用于机器初筛，不构成官方报考资格认定。专业目录、应届身份、备注条件等，"
        "必须以当年度招录公告、专业指导目录和招录单位答复为准。"
    )

    with st.sidebar:
        st.header("① 填写个人条件")
        education = st.selectbox("最高学历", list(EDU_RANK), index=2)
        degree = st.selectbox("最高学位", list(DEGREE_RANK), index=2)
        major_text = st.text_input("所学专业", placeholder="例如：行政管理，公共事业管理")
        category_text = st.text_input("可能对应的专业类别", placeholder="例如：公共管理类")
        political = st.selectbox(
            "政治面貌",
            ["中共党员", "中共预备党员", "共青团员", "群众", "其他"],
            index=2,
        )
        grassroots_years = st.number_input("基层工作经历（年）", 0, 20, 0, 1)
        service_project = st.selectbox("服务基层项目经历", SERVICE_PROJECTS)
        fresh_graduate = st.toggle("属于岗位公告口径下的应届毕业生", value=True)
        gender = st.selectbox("性别", ["男", "女"])
        strict_major = st.toggle(
            "严格专业匹配",
            value=False,
            help="开启后，专业未直接匹配会判为不可报；关闭时会标记为人工确认。",
        )

        profile = Profile(
            education=education,
            degree=degree,
            majors=split_terms(major_text),
            major_categories=split_terms(category_text),
            political=political,
            grassroots_years=int(grassroots_years),
            service_project=service_project,
            fresh_graduate=fresh_graduate,
            gender=gender,
            strict_major=strict_major,
        )

    st.header("② 上传岗位表")
    uploaded = st.file_uploader(
        "上传国考、省考或事业单位岗位表",
        type=["xlsx", "xls", "csv"],
        help="支持常见 Excel/CSV 岗位表，系统会尝试自动识别表头和字段。",
    )

    if uploaded is None:
        st.warning("请先上传岗位表。项目压缩包中已附带 sample_jobs.xlsx，可直接测试。")
        st.stop()

    file_bytes = uploaded.getvalue()
    sheet_name: str | int = 0
    try:
        sheets = list_excel_sheets(file_bytes, uploaded.name)
        if sheets:
            sheet_name = st.selectbox("选择工作表", sheets)
        df = load_tabular_file(file_bytes, uploaded.name, sheet_name)
    except Exception as exc:
        st.error(f"岗位表读取失败：{exc}")
        st.stop()

    if df.empty:
        st.error("岗位表中没有识别到有效数据。")
        st.stop()

    st.success(f"已读取 {len(df):,} 条岗位记录、{len(df.columns)} 个字段。")
    detected = auto_map_columns(df.columns)
    mapping = render_mapping_editor(df, detected)

    required_roles = ["job_title", "major", "education"]
    missing = [FIELD_LABELS[r] for r in required_roles if not mapping.get(r)]
    if missing:
        st.error(f"至少需要识别这些字段：{'、'.join(missing)}。请在“字段识别与手动校正”中指定。")
        st.stop()

    st.header("③ 设置筛选范围")
    filter_cols = st.columns(3)
    location_keyword = filter_cols[0].text_input("工作地点包含", placeholder="例如：杭州、浙江")
    department_keyword = filter_cols[1].text_input("招录机关包含", placeholder="例如：税务、公安")
    only_available = filter_cols[2].toggle("仅显示非“不可报”岗位", value=True)

    working_df = df.copy()
    if location_keyword and mapping.get("location"):
        working_df = working_df[
            working_df[mapping["location"]].astype(str).str.contains(location_keyword, case=False, na=False)
        ]
    if department_keyword and mapping.get("department"):
        working_df = working_df[
            working_df[mapping["department"]].astype(str).str.contains(department_keyword, case=False, na=False)
        ]

    if working_df.empty:
        st.warning("当前地区或机关筛选条件下没有岗位。")
        st.stop()

    result_df, details = evaluate_dataframe(working_df, mapping, profile)
    display_df = result_df[result_df["匹配结论"] != "不可报"].copy() if only_available else result_df.copy()
    display_df = display_df.sort_values(["匹配分", "匹配结论"], ascending=[False, True])

    st.header("④ 匹配结果")
    total = len(result_df)
    available = int((result_df["匹配结论"] == "初筛可报").sum())
    uncertain = int((result_df["匹配结论"] == "需人工确认").sum())
    unavailable = int((result_df["匹配结论"] == "不可报").sum())
    metrics = st.columns(4)
    metrics[0].metric("参与匹配", total)
    metrics[1].metric("初筛可报", available)
    metrics[2].metric("需人工确认", uncertain)
    metrics[3].metric("不可报", unavailable)

    chart_data = pd.DataFrame(
        {"岗位数": [available, uncertain, unavailable]},
        index=["初筛可报", "需人工确认", "不可报"],
    )
    st.bar_chart(chart_data)

    preferred_front = ["匹配结论", "匹配分", "相对分层", "匹配说明"]
    job_front = [
        mapping.get("department"), mapping.get("office"), mapping.get("job_title"),
        mapping.get("job_code"), mapping.get("location"), mapping.get("recruit_count"),
        mapping.get("major"), mapping.get("education"),
    ]
    ordered = preferred_front + [c for c in job_front if c and c not in preferred_front]
    ordered += [c for c in display_df.columns if c not in ordered]
    st.dataframe(display_df[ordered], use_container_width=True, height=520, hide_index=True)

    st.caption(
        "“稳妥候选/重点候选/冲刺候选”只是依据填写条件、限制项数量和招录人数进行的相对分层，"
        "不代表真实竞争比或录取概率。"
    )

    export_bytes = dataframe_to_excel_bytes(display_df)
    st.download_button(
        "下载匹配结果 Excel",
        data=export_bytes,
        file_name="GovMatch_岗位匹配结果.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.header("⑤ 单个岗位详细解读")
    if display_df.empty:
        st.info("没有可供查看的岗位。")
        st.stop()

    label_col = mapping.get("job_title")
    code_col = mapping.get("job_code")
    labels: dict[str, int] = {}
    for idx, row in display_df.iterrows():
        title = text(row.get(label_col, "")) or "未命名岗位"
        code = text(row.get(code_col, ""))
        labels[f"{title}｜{code or f'第{idx + 1}行'}"] = idx

    selected_label = st.selectbox("选择岗位", list(labels))
    selected_index = labels[selected_label]
    selected_row = display_df.loc[selected_index]
    selected_checks = details[selected_index]

    check_df = pd.DataFrame(
        [{"检查项": c.field, "结果": c.status, "说明": c.reason} for c in selected_checks]
    )
    st.dataframe(check_df, use_container_width=True, hide_index=True)

    if st.button("生成 AI 岗位解读", use_container_width=True):
        with st.spinner("正在生成岗位解读……"):
            explanation = generate_ai_explanation(
                profile,
                {k: selected_row[k] for k in selected_row.index if k not in preferred_front},
                selected_checks,
            )
        st.markdown(explanation)

    with st.expander("部署配置说明"):
        st.code(
            'OPENAI_API_KEY = "你的 OpenAI API Key"\n'
            'OPENAI_MODEL = "你的账户可用模型名称"',
            language="toml",
        )
        st.caption("AI Key 为可选配置；不配置时，规则筛选、结果导出和详细检查仍可使用。")


if __name__ == "__main__":
    main()
