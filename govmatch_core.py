from __future__ import annotations

import io
import re
from collections.abc import Iterable
from copy import copy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

APP_VERSION = "3.0"
RULESET_VERSION = "2026.1"
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_ROWS = 100_000
MAX_COLUMNS = 200
MAX_SHEETS = 30

RULE_SOURCES = [
    {
        "name": "教育部：中央机关及其直属机构2026年度考试录用公务员公告",
        "url": "https://hudong.moe.gov.cn/s78/A04/tongzhi/202510/t20251015_1416829.html",
        "note": "专业名称与代码应按当年度官方专业目录核验。",
    },
    {
        "name": "国家税务总局：2026年度考试录用公务员相关事项通知",
        "url": "https://www.chinatax.gov.cn/chinatax/n896543r/c5243601/content.html",
        "note": "学历、学位与应届毕业生口径须以招录机关说明为准。",
    },
]

COLUMN_ALIASES: dict[str, list[str]] = {
    "department": ["招录机关", "招考单位", "招录单位", "单位名称", "部门名称", "机关", "部门"],
    "office": ["用人司局", "用人单位", "内设机构", "职位所在部门", "司局", "科室"],
    "job_title": ["招考职位", "职位名称", "岗位名称", "招录职位", "职位", "岗位"],
    "job_code": ["职位代码", "岗位代码", "招考职位代码", "招录职位代码", "职位编号", "岗位编号"],
    "recruit_count": ["招考人数", "计划招录人数", "招录人数", "招聘人数", "招考计划", "人数"],
    "major": ["专业", "专业要求", "所学专业", "专业类别", "专业限制", "专业条件"],
    "education": ["学历", "学历要求", "最低学历", "学历层次"],
    "degree": ["学位", "学位要求"],
    "political": ["政治面貌", "政治面貌要求"],
    "grassroots": ["基层工作最低年限", "基层工作年限", "基层经历年限", "基层工作经历", "工作年限"],
    "service_project": ["服务基层项目工作经历", "服务基层项目", "基层项目经历", "服务项目经历"],
    "fresh_graduate": ["是否限应届毕业生", "应届毕业生", "应届要求", "招录对象", "人员身份", "身份要求"],
    "gender": ["性别", "性别要求"],
    "household": ["户籍", "户籍要求", "生源地", "生源要求", "户籍或生源"],
    "location": ["工作地点", "工作地", "职位工作地点", "地区", "所在地", "落户地点", "行政区划"],
    "remarks": ["备注", "其他条件", "补充条件", "说明", "其他要求"],
}

TEMPLATE_ALIASES: dict[str, dict[str, list[str]]] = {
    "国考": {
        "department": ["部门名称"],
        "office": ["用人司局"],
        "job_title": ["招考职位"],
        "location": ["工作地点", "落户地点"],
    },
    "浙江省考": {
        "department": ["招录机关名称", "招录单位名称"],
        "job_title": ["职位名称"],
        "fresh_graduate": ["现有身份要求", "招考对象"],
        "household": ["户籍要求", "生源地要求"],
    },
    "上海市考": {
        "department": ["招录机关"],
        "job_title": ["职位名称"],
        "location": ["工作地区"],
    },
    "事业单位": {
        "department": ["招聘单位", "主管部门"],
        "job_title": ["招聘岗位", "岗位名称"],
        "recruit_count": ["招聘人数", "招聘计划数"],
    },
}

FIELD_LABELS = {
    "department": "招录机关",
    "office": "用人司局/科室",
    "job_title": "职位名称",
    "job_code": "职位代码",
    "recruit_count": "招考人数",
    "major": "专业要求",
    "education": "学历要求",
    "degree": "学位要求",
    "political": "政治面貌",
    "grassroots": "基层工作年限",
    "service_project": "服务基层项目",
    "fresh_graduate": "应届/身份要求",
    "gender": "性别要求",
    "household": "户籍/生源要求",
    "location": "工作地点",
    "remarks": "备注",
}

EDU_RANK = {"大专": 1, "本科": 2, "硕士研究生": 3, "博士研究生": 4}
DEGREE_RANK = {"无学位": 0, "学士": 1, "硕士": 2, "博士": 3}

UNLIMITED_WORDS = (
    "不限",
    "无限制",
    "无要求",
    "不作要求",
    "不限制",
    "均可",
    "否",
    "无",
    "不限户籍",
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
    "户籍",
    "生源",
    "资格证",
    "职业资格",
    "英语",
    "四级",
    "六级",
    "法律职业资格",
    "司法考试",
    "会计",
    "计算机等级",
    "普通话",
    "最低服务年限",
    "夜班",
    "值班",
    "体能",
    "视力",
    "工作经历",
    "相关经历",
    "面向",
    "证书",
    "专业能力测试",
    "加试",
]

PROVINCES = [
    "北京",
    "天津",
    "上海",
    "重庆",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "黑龙江",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "台湾",
    "内蒙古",
    "广西",
    "西藏",
    "宁夏",
    "新疆",
    "香港",
    "澳门",
]

CHINESE_NUMBERS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

STATUS_LABELS = {
    "pass": "✅ 符合",
    "uncertain": "⚠️ 待核对",
    "fail": "❌ 不符合",
}

QUALIFICATION_ROLES = (
    "education",
    "degree",
    "major",
    "political",
    "grassroots",
    "service_project",
    "fresh_graduate",
    "gender",
    "household",
    "remarks",
)


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
    fresh_status: str = ""
    household: str = ""
    extra_conditions: list[str] = field(default_factory=list)
    strict_major: bool = False
    prior_education: str = ""
    prior_degree: str = ""
    prior_majors: list[str] = field(default_factory=list)
    prior_major_categories: list[str] = field(default_factory=list)

    @property
    def primary_major_text(self) -> str:
        values = [*self.majors, *self.major_categories]
        return "、".join(value for value in values if value)

    @property
    def prior_major_text(self) -> str:
        values = [*self.prior_majors, *self.prior_major_categories]
        return "、".join(value for value in values if value)

    def to_rows(self) -> list[tuple[str, str]]:
        rows = [
            ("报考学历", self.education),
            ("报考学位", self.degree),
            ("报考学历专业", self.primary_major_text or "未填写"),
        ]
        if self.prior_education:
            rows.extend(
                [
                    ("补充学历", self.prior_education),
                    ("补充学历专业", self.prior_major_text or "未填写"),
                ]
            )
        rows.extend(
            [
                ("政治面貌", self.political),
                ("基层工作经历", f"{self.grassroots_years}年"),
                ("服务基层项目", self.service_project),
                ("应届身份", self.fresh_status or ("是" if self.fresh_graduate else "否")),
                ("性别", self.gender),
                ("户籍/生源", self.household or "未填写"),
                ("其他条件", "、".join(self.extra_conditions) or "未填写"),
            ]
        )
        return rows


@dataclass
class Check:
    field: str
    status: str  # pass / fail / uncertain
    reason: str


@dataclass
class MatchResult:
    overall: str
    score: int
    qualification_label: str
    checks: list[Check]
    coverage_score: int = 0
    checked_fields: int = 0
    expected_fields: int = len(QUALIFICATION_ROLES)
    missing_fields: list[str] = field(default_factory=list)


def text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def compact(value: Any) -> str:
    return re.sub(r"[\s\u3000,，;；、/（）()【】\[\]：:·\-—_]+", "", text(value)).lower()


def split_terms(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,，;；、/\n]+", value or "") if item.strip()]


def is_unlimited(value: Any) -> bool:
    value_text = text(value)
    if not value_text:
        return True
    normalized = compact(value_text)
    exact_unlimited = {compact(word) for word in UNLIMITED_WORDS}
    return normalized in exact_unlimited or any(
        phrase in value_text for phrase in ("专业不限", "不限专业", "户籍不限")
    )


def normalize_column_name(value: Any) -> str:
    return re.sub(r"[\s\n\r\t（）()【】\[\]：:]+", "", text(value)).lower()


def deduplicate_columns(columns: Iterable[Any]) -> list[str]:
    seen: dict[str, int] = {}
    output: list[str] = []
    for index, raw in enumerate(columns):
        base = text(raw) or f"未命名列_{index + 1}"
        seen[base] = seen.get(base, 0) + 1
        output.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return output


def aliases_for_template(template: str) -> dict[str, list[str]]:
    merged = {key: list(values) for key, values in COLUMN_ALIASES.items()}
    for role, values in TEMPLATE_ALIASES.get(template, {}).items():
        merged.setdefault(role, [])
        merged[role] = list(dict.fromkeys([*values, *merged[role]]))
    return merged


def detect_header_row_with_score(
    raw: pd.DataFrame,
    template: str = "自动识别（通用）",
    max_rows: int = 30,
) -> tuple[int, int]:
    aliases = aliases_for_template(template)
    keywords = {normalize_column_name(alias) for values in aliases.values() for alias in values}
    best_row, best_score = 0, -1
    for idx in range(min(max_rows, len(raw))):
        values = [normalize_column_name(value) for value in raw.iloc[idx].tolist()]
        score = 0
        for cell in values:
            if not cell:
                continue
            if cell in keywords:
                score += 4
            elif any(keyword and (keyword in cell or cell in keyword) for keyword in keywords):
                score += 1
        if score > best_score:
            best_row, best_score = idx, score
    return best_row, best_score


def detect_header_row(raw: pd.DataFrame, template: str = "自动识别（通用）", max_rows: int = 30) -> int:
    return detect_header_row_with_score(raw, template, max_rows)[0]


def _validate_upload_size(file_bytes: bytes) -> None:
    if not file_bytes:
        raise ValueError("文件为空，请重新选择岗位表。")
    if len(file_bytes) > MAX_FILE_BYTES:
        raise ValueError(f"文件超过 {MAX_FILE_BYTES // 1024 // 1024} MB 上限，请先精简岗位表。")


def _validate_dataframe_size(df: pd.DataFrame) -> None:
    if len(df) > MAX_ROWS:
        raise ValueError(f"岗位表超过 {MAX_ROWS:,} 行上限，请先按地区或职位拆分。")
    if len(df.columns) > MAX_COLUMNS:
        raise ValueError(f"岗位表超过 {MAX_COLUMNS} 列上限，请删除无关列后重试。")


def read_csv_flexible(file_bytes: bytes) -> pd.DataFrame:
    _validate_upload_size(file_bytes)
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030", "gbk", "utf-8"):
        try:
            return pd.read_csv(io.BytesIO(file_bytes), encoding=encoding, dtype=object)
        except Exception as exc:
            last_error = exc
    raise ValueError(f"CSV读取失败：{last_error}")


def list_excel_sheets(file_bytes: bytes, filename: str) -> list[str]:
    if not filename.lower().endswith((".xlsx", ".xls")):
        return []
    _validate_upload_size(file_bytes)
    names = pd.ExcelFile(io.BytesIO(file_bytes)).sheet_names
    if len(names) > MAX_SHEETS:
        raise ValueError(f"工作表数量超过 {MAX_SHEETS} 个上限，请先精简文件。")
    return names


def load_tabular_file(
    file_bytes: bytes,
    filename: str,
    sheet_name: str | int | None = 0,
    template: str = "自动识别（通用）",
) -> pd.DataFrame:
    _validate_upload_size(file_bytes)
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix == "csv":
        df = read_csv_flexible(file_bytes)
    elif suffix in {"xlsx", "xls"}:
        buffer = io.BytesIO(file_bytes)
        raw = pd.read_excel(buffer, sheet_name=sheet_name, header=None, dtype=object)
        header_row, confidence = detect_header_row_with_score(raw, template=template)
        if confidence < 4:
            raise ValueError("未能可靠识别表头；请将列名放在前30行，并至少包含职位、专业或学历字段。")
        buffer.seek(0)
        df = pd.read_excel(buffer, sheet_name=sheet_name, header=header_row, dtype=object)
    else:
        raise ValueError("仅支持 .xlsx、.xls 和 .csv 文件。")

    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all").copy()
    df.columns = deduplicate_columns(df.columns)
    _validate_dataframe_size(df)
    return df.reset_index(drop=True)


def auto_map_columns(columns: Iterable[str], template: str = "自动识别（通用）") -> dict[str, str | None]:
    columns = list(columns)
    normalized = {column: normalize_column_name(column) for column in columns}
    aliases = aliases_for_template(template)
    mapping: dict[str, str | None] = {}
    for role, role_aliases in aliases.items():
        alias_norms = [normalize_column_name(alias) for alias in role_aliases]
        exact = next((column for column, norm in normalized.items() if norm in alias_norms), None)
        if exact:
            mapping[role] = exact
            continue
        fuzzy = next(
            (
                column
                for column, norm in normalized.items()
                if any(alias and (alias in norm or norm in alias) for alias in alias_norms)
            ),
            None,
        )
        mapping[role] = fuzzy
    return mapping


def mapping_conflicts(mapping: dict[str, str | None]) -> dict[str, list[str]]:
    by_column: dict[str, list[str]] = {}
    for role, column in mapping.items():
        if column:
            by_column.setdefault(column, []).append(role)
    return {column: roles for column, roles in by_column.items() if len(roles) > 1}


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
    if user_value not in EDU_RANK:
        return Check("学历", "uncertain", "尚未填写有效学历")
    user_rank = EDU_RANK[user_value]

    min_patterns = [
        ("大专及以上", 1),
        ("专科及以上", 1),
        ("本科及以上", 2),
        ("大学本科及以上", 2),
        ("硕士研究生及以上", 3),
        ("研究生及以上", 3),
        ("博士研究生及以上", 4),
    ]
    for pattern, min_rank in min_patterns:
        if pattern in req:
            status = "pass" if user_rank >= min_rank else "fail"
            reason = f"用户学历满足“{pattern}”" if status == "pass" else f"要求{pattern}，用户为{user_value}"
            return Check("学历", status, reason)

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
        return Check("学历", "fail", f"学历要求为“{req}”，用户拟以{user_value}报考")
    return Check("学历", "uncertain", f"无法自动解析学历要求“{req}”")


def check_degree(requirement: Any, user_value: str) -> Check:
    req = text(requirement)
    if is_unlimited(req):
        return Check("学位", "pass", "学位不限")
    if user_value not in DEGREE_RANK:
        return Check("学位", "uncertain", "尚未填写有效学位")
    user_rank = DEGREE_RANK[user_value]

    if "与最高学历相对应" in req or "相应学位" in req:
        if user_rank > 0:
            return Check("学位", "uncertain", "具备学位，但仍需核对是否与拟报考学历对应")
        return Check("学位", "fail", "岗位要求与学历相对应的学位")

    required_rank = 3 if "博士" in req else 2 if "硕士" in req else 1 if "学士" in req else None
    if required_rank is None:
        return Check("学位", "uncertain", f"无法自动解析学位要求“{req}”")
    passed = user_rank >= required_rank if "及以上" in req else user_rank == required_rank
    if passed:
        return Check("学位", "pass", f"用户学位满足“{req}”")
    return Check("学位", "fail", f"要求“{req}”，用户为{user_value}")


def _negative_major_match(requirement: str, candidates: list[str]) -> str | None:
    """Find candidates explicitly excluded by phrases such as `不含法学` or `非法学类`."""
    req = compact(requirement)
    for candidate in candidates:
        normalized = compact(candidate)
        if not normalized:
            continue
        stems = {normalized, re.sub(r"(专业|学类|类|学)$", "", normalized)}
        for stem in sorted((item for item in stems if len(item) >= 2), key=len, reverse=True):
            patterns = (
                rf"非{re.escape(stem)}(?:专业|学类|类)?",
                rf"不含[^，；、]{{0,12}}{re.escape(stem)}",
                rf"不包括[^，；、]{{0,12}}{re.escape(stem)}",
                rf"排除[^，；、]{{0,12}}{re.escape(stem)}",
                rf"{re.escape(stem)}(?:专业|学类|类)?除外",
                rf"除[^，；、]{{0,12}}{re.escape(stem)}[^，；、]{{0,8}}外",
            )
            if any(re.search(pattern, req) for pattern in patterns):
                return candidate
    return None


def _positive_major_text(requirement: str) -> str:
    segments = re.split(r"[，；;。\n]", requirement)
    negative_markers = ("不含", "不包括", "排除", "除外")
    kept = [segment for segment in segments if not any(marker in segment for marker in negative_markers)]
    value = "，".join(kept)
    return re.sub(r"非([\u4e00-\u9fffA-Za-z0-9]+?)(?:专业|学类|类)(?=$|[、，；或和及])", "", value)


def _candidate_match(requirement: str, candidates: list[str]) -> str | None:
    req_compact = compact(_positive_major_text(requirement))
    for candidate in candidates:
        normalized = compact(candidate)
        if normalized and normalized in req_compact:
            return candidate
    return None


def check_major(requirement: Any, profile: Profile) -> Check:
    req = text(requirement)
    if is_unlimited(req):
        return Check("专业", "pass", "专业不限")

    primary = [*profile.majors, *profile.major_categories]
    prior = [*profile.prior_majors, *profile.prior_major_categories]

    excluded = _negative_major_match(req, [*primary, *prior])
    if excluded:
        return Check("专业", "fail", f"岗位条件明确排除了“{excluded}”")

    matched = _candidate_match(req, primary)
    if matched:
        return Check("专业", "pass", f"拟报考学历专业直接匹配：{matched}")

    prior_matched = _candidate_match(req, prior)
    if prior_matched:
        level = profile.prior_education or "补充学历"
        return Check(
            "专业",
            "uncertain",
            f"{level}专业“{prior_matched}”匹配，但拟以{profile.education}报考，需确认能否按该学历专业认定",
        )

    all_candidates = [*primary, *prior]
    req_compact = compact(req)
    for candidate in all_candidates:
        normalized = re.sub(r"(专业|学类|类|学)$", "", compact(candidate))
        if len(normalized) >= 3 and normalized in req_compact:
            return Check("专业", "uncertain", f"疑似匹配“{candidate}”，需按官方专业目录和代码核对")

    if not all_candidates:
        return Check("专业", "uncertain", "尚未填写专业，无法完成专业匹配")

    status = "fail" if profile.strict_major else "uncertain"
    suffix = "（已启用严格模式）" if profile.strict_major else "，可能存在专业代码、上位类别或新旧名称关系"
    return Check("专业", status, f"未发现用户专业与“{req}”的直接文本匹配{suffix}")


def check_political(requirement: Any, user_value: str) -> Check:
    req = text(requirement)
    if is_unlimited(req):
        return Check("政治面貌", "pass", "政治面貌不限")

    allows_party = "中共党员" in req or "党员" in req
    allows_youth = "共青团员" in req
    allows_pre = "预备" in req or "含预备党员" in req

    if user_value == "中共党员" and allows_party:
        return Check("政治面貌", "pass", "符合党员要求")
    if user_value == "中共预备党员" and allows_party:
        if allows_pre:
            return Check("政治面貌", "pass", "岗位明确包含预备党员")
        return Check("政治面貌", "uncertain", "岗位写明党员，但未明确是否包含预备党员")
    if user_value == "共青团员" and allows_youth:
        return Check("政治面貌", "pass", "符合共青团员要求")
    if user_value in req:
        return Check("政治面貌", "pass", "政治面貌直接匹配")
    if allows_party or allows_youth:
        return Check("政治面貌", "fail", f"要求“{req}”，用户为{user_value}")
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
    if is_unlimited(req):
        return Check("服务基层项目", "pass", "服务基层项目经历不限")
    if user_value == "无":
        return Check("服务基层项目", "fail", f"岗位要求“{req}”")
    if user_value in req or "服务基层项目人员" in req:
        return Check("服务基层项目", "pass", f"用户经历与“{req}”匹配")
    return Check("服务基层项目", "uncertain", f"用户经历为{user_value}，岗位要求“{req}”")


def check_fresh_graduate(requirement: Any, is_fresh: bool, fresh_status: str = "") -> Check:
    req = text(requirement)
    unlimited_phrases = (
        "不限应届",
        "应届不限",
        "不限制应届",
        "不限身份",
        "身份不限",
        "不限人员身份",
    )
    if is_unlimited(req) or any(phrase in req for phrase in unlimited_phrases):
        return Check("应届身份", "pass", "未限制应届身份")

    status = fresh_status.strip()
    if "不确定" in status or "请选择" in status:
        return Check("应届身份", "uncertain", f"岗位要求“{req}”，个人应届身份尚未确认")

    year_match = re.search(r"(20\d{2})届", req)
    if year_match:
        target = year_match.group(1)
        if target in status:
            return Check("应届身份", "pass", f"个人身份与岗位要求的{target}届一致")
        if status:
            return Check("应届身份", "fail", f"岗位限{target}届，个人选择为“{status}”")
        return Check("应届身份", "uncertain", f"岗位限{target}届，需核对毕业年份")

    if any(keyword in req for keyword in ["应届", "高校毕业生", "当年毕业生"]):
        return Check(
            "应届身份",
            "pass" if is_fresh else "fail",
            "用户选择了应届身份" if is_fresh else f"岗位要求“{req}”",
        )
    if any(keyword in req for keyword in ["社会人员", "非应届"]):
        return Check(
            "应届身份",
            "pass" if not is_fresh else "uncertain",
            "符合社会人员/非应届要求" if not is_fresh else f"岗位面向“{req}”，需确认应届生是否可报",
        )
    return Check("应届身份", "uncertain", f"无法自动解析“{req}”")


def check_gender(requirement: Any, user_value: str) -> Check:
    req = text(requirement)
    if is_unlimited(req) or "男女不限" in req:
        return Check("性别", "pass", "性别不限")
    normalized = compact(req)
    male_only = "男性" in req or normalized in {"男", "限男"}
    female_only = "女性" in req or normalized in {"女", "限女"}
    if male_only:
        return Check(
            "性别",
            "pass" if user_value == "男" else "fail",
            "性别符合要求" if user_value == "男" else "岗位限男性",
        )
    if female_only:
        return Check(
            "性别",
            "pass" if user_value == "女" else "fail",
            "性别符合要求" if user_value == "女" else "岗位限女性",
        )
    return Check("性别", "uncertain", f"无法自动解析“{req}”")


def _administrative_places(value: str) -> tuple[set[str], set[str]]:
    provinces = {province for province in PROVINCES if province in value}
    cities = {
        match.group(1)
        for match in re.finditer(r"([\u4e00-\u9fff]{2,12}?(?:市|自治州|地区|盟))", value)
        if match.group(1) not in {"户籍所在地", "生源所在地"}
    }
    return provinces, cities


def check_household(requirement: Any, user_value: str) -> Check:
    req = text(requirement)
    if is_unlimited(req) or "全国" in req:
        return Check("户籍/生源", "pass", "户籍或生源不限")
    if not user_value:
        return Check("户籍/生源", "uncertain", f"岗位要求“{req}”，但用户未填写户籍/生源")

    req_compact, user_compact = compact(req), compact(user_value)
    if user_compact in req_compact or req_compact in user_compact:
        return Check("户籍/生源", "pass", f"用户填写的“{user_value}”与岗位要求直接匹配")

    req_provinces, req_cities = _administrative_places(req)
    user_provinces, user_cities = _administrative_places(user_value)
    province_matches = req_provinces & user_provinces
    city_matches = req_cities & user_cities

    if req_cities:
        if city_matches:
            return Check("户籍/生源", "pass", f"地市范围匹配：{sorted(city_matches)[0]}")
        if user_cities and province_matches:
            return Check(
                "户籍/生源",
                "fail",
                f"岗位限制到{'、'.join(sorted(req_cities))}，个人填写为{'、'.join(sorted(user_cities))}",
            )
        return Check(
            "户籍/生源", "uncertain", f"岗位限制到地市“{'、'.join(sorted(req_cities))}”，需补充或核对具体地市"
        )

    if province_matches:
        return Check("户籍/生源", "pass", f"省级范围匹配：{sorted(province_matches)[0]}")
    if req_provinces and user_provinces:
        return Check(
            "户籍/生源",
            "fail",
            f"岗位要求{'、'.join(sorted(req_provinces))}，个人为{'、'.join(sorted(user_provinces))}",
        )
    return Check("户籍/生源", "uncertain", f"用户为“{user_value}”，岗位要求“{req}”，需核对具体口径")


def check_remarks(requirement: Any, extra_conditions: list[str]) -> Check:
    req = text(requirement)
    if not req or is_unlimited(req):
        return Check("备注", "pass", "未发现额外备注条件")

    hits = [keyword for keyword in RISK_KEYWORDS if keyword in req]
    provided = compact("、".join(extra_conditions))
    covered = [keyword for keyword in hits if compact(keyword) in provided]
    uncovered = [keyword for keyword in hits if keyword not in covered]

    if hits and not uncovered:
        return Check("备注", "uncertain", f"已填写相关条件（{'、'.join(covered)}），仍需按备注原文逐项核验")
    if hits:
        return Check("备注", "uncertain", f"备注含额外条件：{'、'.join(uncovered[:5])}")
    return Check("备注", "uncertain", "岗位存在备注信息，请人工完整阅读")


def value_from_row(row: pd.Series, mapping: dict[str, str | None], role: str) -> Any:
    column = mapping.get(role)
    return row.get(column, "") if column else ""


def parse_recruit_count(value: Any) -> int:
    match = re.search(r"\d+", text(value))
    return int(match.group()) if match else 1


def evaluate_job(row: pd.Series, mapping: dict[str, str | None], profile: Profile) -> MatchResult:
    checks: list[Check] = []

    if mapping.get("education"):
        checks.append(check_education(value_from_row(row, mapping, "education"), profile.education))
    if mapping.get("degree"):
        checks.append(check_degree(value_from_row(row, mapping, "degree"), profile.degree))
    if mapping.get("major"):
        checks.append(check_major(value_from_row(row, mapping, "major"), profile))
    if mapping.get("political"):
        checks.append(check_political(value_from_row(row, mapping, "political"), profile.political))
    if mapping.get("grassroots"):
        checks.append(check_grassroots(value_from_row(row, mapping, "grassroots"), profile.grassroots_years))
    if mapping.get("service_project"):
        checks.append(
            check_service_project(value_from_row(row, mapping, "service_project"), profile.service_project)
        )
    if mapping.get("fresh_graduate"):
        checks.append(
            check_fresh_graduate(
                value_from_row(row, mapping, "fresh_graduate"),
                profile.fresh_graduate,
                profile.fresh_status,
            )
        )
    if mapping.get("gender"):
        checks.append(check_gender(value_from_row(row, mapping, "gender"), profile.gender))
    if mapping.get("household"):
        checks.append(check_household(value_from_row(row, mapping, "household"), profile.household))
    if mapping.get("remarks"):
        checks.append(check_remarks(value_from_row(row, mapping, "remarks"), profile.extra_conditions))

    missing_roles = [role for role in QUALIFICATION_ROLES if not mapping.get(role)]
    checks.extend(
        Check(FIELD_LABELS[role], "uncertain", "岗位表未识别到该资格字段，系统不能视为不限")
        for role in missing_roles
    )

    fail_count = sum(check.status == "fail" for check in checks)
    uncertain_count = sum(check.status == "uncertain" for check in checks)
    pass_count = sum(check.status == "pass" for check in checks)

    checked_fields = len(QUALIFICATION_ROLES) - len(missing_roles)
    coverage_score = round(100 * checked_fields / len(QUALIFICATION_ROLES))

    if fail_count:
        overall = "明确不符合"
        score = 0
        label = "不建议报考"
    else:
        score = max(0, min(100, round(100 * pass_count / max(len(checks), 1))))
        if uncertain_count == 0:
            overall, label = "资格初筛匹配", "已核验条件通过"
        elif uncertain_count <= 2 and coverage_score >= 80:
            overall, label = "存在待核对项", "少量条件待核对"
        else:
            overall, label = "存在待核对项", "需要人工核对"

    return MatchResult(
        overall=overall,
        score=score,
        qualification_label=label,
        checks=checks,
        coverage_score=coverage_score,
        checked_fields=checked_fields,
        missing_fields=[FIELD_LABELS[role] for role in missing_roles],
    )


def evaluate_dataframe(
    df: pd.DataFrame,
    mapping: dict[str, str | None],
    profile: Profile,
) -> tuple[pd.DataFrame, dict[int, list[Check]]]:
    output = df.copy()
    overall_values: list[str] = []
    score_values: list[int] = []
    coverage_values: list[int] = []
    label_values: list[str] = []
    pending_values: list[int] = []
    fail_values: list[int] = []
    reason_values: list[str] = []
    details: dict[int, list[Check]] = {}

    for index, row in output.iterrows():
        result = evaluate_job(row, mapping, profile)
        overall_values.append(result.overall)
        score_values.append(result.score)
        coverage_values.append(result.coverage_score)
        label_values.append(result.qualification_label)
        pending_values.append(sum(check.status == "uncertain" for check in result.checks))
        fail_values.append(sum(check.status == "fail" for check in result.checks))
        reason_values.append(
            "；".join(
                f"{check.field}[{STATUS_LABELS[check.status]}]：{check.reason}" for check in result.checks
            )
        )
        details[index] = result.checks

    output.insert(0, "资格结论", overall_values)
    output.insert(1, "规则通过度", score_values)
    output.insert(2, "规则覆盖率", coverage_values)
    output.insert(3, "资格标签", label_values)
    output.insert(4, "待核对项数", pending_values)
    output.insert(5, "不符合项数", fail_values)
    output.insert(6, "匹配说明", reason_values)
    return output, details


def readable_checks(checks: list[Check]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"检查项": check.field, "结果": STATUS_LABELS[check.status], "说明": check.reason}
            for check in checks
        ]
    )


def pending_summary(checks: list[Check], limit: int = 3) -> str:
    pending = [check.field for check in checks if check.status == "uncertain"]
    failed = [check.field for check in checks if check.status == "fail"]
    if failed:
        return "不符合：" + "、".join(failed[:limit])
    if pending:
        return "待核对：" + "、".join(pending[:limit])
    return "已填写条件均通过规则初筛"


def job_label(row: pd.Series, mapping: dict[str, str | None], fallback: str) -> str:
    title = text(value_from_row(row, mapping, "job_title")) or "未命名岗位"
    code = text(value_from_row(row, mapping, "job_code"))
    return f"{title}｜{code or fallback}"


def generate_consultation_script(
    profile: Profile,
    row: pd.Series,
    mapping: dict[str, str | None],
    checks: list[Check],
) -> str:
    department = text(value_from_row(row, mapping, "department")) or "贵单位"
    title = text(value_from_row(row, mapping, "job_title")) or "该岗位"
    code = text(value_from_row(row, mapping, "job_code"))
    major_req = text(value_from_row(row, mapping, "major"))
    education_req = text(value_from_row(row, mapping, "education"))

    identity = f"我拟以{profile.education}学历报考，专业为{profile.primary_major_text or '（待填写）'}"
    if profile.prior_education and profile.prior_major_text:
        identity += f"；另有{profile.prior_education}学历，专业为{profile.prior_major_text}"

    uncertain = [check for check in checks if check.status == "uncertain"]
    failed = [check for check in checks if check.status == "fail"]
    questions = uncertain or failed
    if questions:
        numbered = "\n".join(
            f"{idx}. {check.field}：{check.reason}" for idx, check in enumerate(questions, 1)
        )
    else:
        numbered = "1. 请问资格复审时还需要特别准备哪些证明材料？"

    code_text = f"（职位代码：{code}）" if code else ""
    requirements = "、".join(value for value in [education_req, major_req] if value)
    req_text = f"岗位表显示相关要求为：{requirements}。" if requirements else ""

    return (
        f"您好，我想咨询{department}的“{title}”岗位{code_text}。\n"
        f"{identity}。{req_text}\n"
        "为避免资格审查理解有误，想请教以下事项：\n"
        f"{numbered}\n"
        "请问按照本次招录公告及专业目录，我是否符合报考条件？如需提供专业代码、培养方向或其他证明材料，也请告知。谢谢！"
    )


def sanitize_excel_value(value: Any) -> Any:
    """Neutralize spreadsheet formulas originating from uploaded cells."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def sanitize_dataframe_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    return df.map(sanitize_excel_value)


def dataframe_to_excel_bytes(df: pd.DataFrame, profile: Profile) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        sanitize_dataframe_for_excel(df).to_excel(writer, index=False, sheet_name="岗位匹配结果")
        sanitize_dataframe_for_excel(
            pd.DataFrame(profile.to_rows(), columns=["个人条件", "填写内容"])
        ).to_excel(writer, index=False, sheet_name="个人条件")
        pd.DataFrame(
            [
                {
                    "规则集版本": RULESET_VERSION,
                    "参考来源": source["name"],
                    "网址": source["url"],
                    "说明": source["note"],
                }
                for source in RULE_SOURCES
            ]
        ).to_excel(writer, index=False, sheet_name="规则与来源")

        result_ws = writer.book["岗位匹配结果"]
        result_ws.freeze_panes = "A2"
        result_ws.auto_filter.ref = result_ws.dimensions
        for cell in result_ws[1]:
            font = copy(cell.font)
            font.bold = True
            cell.font = font
        for column, width in {"A": 16, "B": 13, "C": 16, "D": 12, "E": 12, "F": 60}.items():
            result_ws.column_dimensions[column].width = width

        profile_ws = writer.book["个人条件"]
        profile_ws.freeze_panes = "A2"
        profile_ws.column_dimensions["A"].width = 22
        profile_ws.column_dimensions["B"].width = 60
        for cell in profile_ws[1]:
            font = copy(cell.font)
            font.bold = True
            cell.font = font

        source_ws = writer.book["规则与来源"]
        source_ws.freeze_panes = "A2"
        source_ws.column_dimensions["A"].width = 16
        source_ws.column_dimensions["B"].width = 54
        source_ws.column_dimensions["C"].width = 70
        source_ws.column_dimensions["D"].width = 60
        for cell in source_ws[1]:
            font = copy(cell.font)
            font.bold = True
            cell.font = font
    return buffer.getvalue()


def load_demo_file(project_dir: Path) -> tuple[bytes, str]:
    path = project_dir / "sample_jobs.xlsx"
    return path.read_bytes(), path.name


def profile_as_dict(profile: Profile) -> dict[str, Any]:
    return asdict(profile)
