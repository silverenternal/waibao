"""MockCompanyReviewProvider — 离线可跑的公司评价 mock (T2401).

数据源: 内置 50+ 公司本地数据 (覆盖一线/新一线 + 主流行业).
完全确定性,不联网,用于:
    1. 单元测试
    2. 后端无网络环境运行
    3. 真实 API 接入前的兜底

缓存: 1 小时内存缓存,防止高频调用.
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from ..base import RetryPolicy, with_resilience
from .base import CompanyReviewProvider
from .types import (
    CompanyRating,
    InterviewExperience,
    Review,
    SalaryInsights,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 静态数据池 — 50+ 公司
# ---------------------------------------------------------------------------
_MOCK_COMPANIES: dict[str, dict[str, Any]] = {
    # 互联网大厂
    "bytedance": {
        "name": "字节跳动",
        "industry": "互联网",
        "rating": 4.2,
        "reviews": 18420,
        "recommend": 76,
        "ceo_pct": 71,
        "breakdown": {"compensation": 4.5, "culture": 3.8, "management": 3.6, "worklife": 3.2},
        "salary_median": 32.0,
        "salary_p25": 22.0,
        "salary_p75": 45.0,
        "salary_by_role": {"python": 32.0, "frontend": 28.0, "algorithm": 42.0, "product": 30.0, "design": 22.0},
    },
    "tencent": {
        "name": "腾讯",
        "industry": "互联网",
        "rating": 4.1,
        "reviews": 15680,
        "recommend": 74,
        "ceo_pct": 76,
        "breakdown": {"compensation": 4.4, "culture": 3.9, "management": 3.7, "worklife": 3.5},
        "salary_median": 30.0,
        "salary_p25": 20.0,
        "salary_p75": 42.0,
        "salary_by_role": {"python": 30.0, "frontend": 27.0, "algorithm": 40.0, "product": 28.0, "design": 21.0},
    },
    "alibaba": {
        "name": "阿里巴巴",
        "industry": "互联网",
        "rating": 3.8,
        "reviews": 22150,
        "recommend": 68,
        "ceo_pct": 65,
        "breakdown": {"compensation": 4.1, "culture": 3.5, "management": 3.3, "worklife": 3.4},
        "salary_median": 28.0,
        "salary_p25": 18.0,
        "salary_p75": 40.0,
        "salary_by_role": {"python": 28.0, "frontend": 26.0, "algorithm": 38.0, "product": 27.0, "design": 20.0},
    },
    "meituan": {
        "name": "美团",
        "industry": "互联网",
        "rating": 3.9,
        "reviews": 9840,
        "recommend": 70,
        "ceo_pct": 72,
        "breakdown": {"compensation": 4.0, "culture": 3.7, "management": 3.5, "worklife": 3.3},
        "salary_median": 26.0,
        "salary_p25": 18.0,
        "salary_p75": 36.0,
        "salary_by_role": {"python": 26.0, "frontend": 24.0, "algorithm": 35.0, "product": 25.0, "design": 18.0},
    },
    "didi": {
        "name": "滴滴出行",
        "industry": "互联网",
        "rating": 3.6,
        "reviews": 7320,
        "recommend": 62,
        "ceo_pct": 58,
        "breakdown": {"compensation": 3.8, "culture": 3.4, "management": 3.2, "worklife": 3.5},
        "salary_median": 25.0,
        "salary_p25": 17.0,
        "salary_p75": 35.0,
        "salary_by_role": {"python": 25.0, "frontend": 23.0, "algorithm": 33.0, "product": 24.0, "design": 17.0},
    },
    "jd": {
        "name": "京东",
        "industry": "电商",
        "rating": 3.5,
        "reviews": 12890,
        "recommend": 60,
        "ceo_pct": 55,
        "breakdown": {"compensation": 3.7, "culture": 3.3, "management": 3.1, "worklife": 3.2},
        "salary_median": 23.0,
        "salary_p25": 16.0,
        "salary_p75": 32.0,
        "salary_by_role": {"python": 23.0, "frontend": 21.0, "algorithm": 30.0, "product": 22.0, "design": 16.0},
    },
    "pinduoduo": {
        "name": "拼多多",
        "industry": "电商",
        "rating": 3.7,
        "reviews": 6540,
        "recommend": 66,
        "ceo_pct": 60,
        "breakdown": {"compensation": 4.3, "culture": 3.2, "management": 3.0, "worklife": 2.8},
        "salary_median": 31.0,
        "salary_p25": 22.0,
        "salary_p75": 44.0,
        "salary_by_role": {"python": 31.0, "frontend": 28.0, "algorithm": 40.0, "product": 29.0, "design": 21.0},
    },
    "baidu": {
        "name": "百度",
        "industry": "互联网",
        "rating": 3.7,
        "reviews": 11240,
        "recommend": 64,
        "ceo_pct": 62,
        "breakdown": {"compensation": 3.9, "culture": 3.6, "management": 3.4, "worklife": 3.5},
        "salary_median": 27.0,
        "salary_p25": 18.0,
        "salary_p75": 38.0,
        "salary_by_role": {"python": 27.0, "frontend": 24.0, "algorithm": 36.0, "product": 26.0, "design": 19.0},
    },
    "xiaomi": {
        "name": "小米",
        "industry": "智能硬件",
        "rating": 3.8,
        "reviews": 8920,
        "recommend": 68,
        "ceo_pct": 70,
        "breakdown": {"compensation": 3.9, "culture": 3.7, "management": 3.5, "worklife": 3.4},
        "salary_median": 25.0,
        "salary_p25": 17.0,
        "salary_p75": 35.0,
        "salary_by_role": {"python": 25.0, "frontend": 23.0, "algorithm": 33.0, "product": 24.0, "design": 18.0},
    },
    "huawei": {
        "name": "华为",
        "industry": "通信",
        "rating": 3.9,
        "reviews": 24560,
        "recommend": 71,
        "ceo_pct": 75,
        "breakdown": {"compensation": 4.2, "culture": 3.6, "management": 3.5, "worklife": 3.0},
        "salary_median": 28.0,
        "salary_p25": 19.0,
        "salary_p75": 40.0,
        "salary_by_role": {"python": 28.0, "frontend": 25.0, "algorithm": 37.0, "product": 27.0, "design": 20.0},
    },
    "netease": {
        "name": "网易",
        "industry": "互联网",
        "rating": 3.9,
        "reviews": 7820,
        "recommend": 70,
        "ceo_pct": 73,
        "breakdown": {"compensation": 3.9, "culture": 3.8, "management": 3.6, "worklife": 3.7},
        "salary_median": 26.0,
        "salary_p25": 18.0,
        "salary_p75": 36.0,
        "salary_by_role": {"python": 26.0, "frontend": 24.0, "algorithm": 34.0, "product": 25.0, "design": 19.0},
    },
    # 外企
    "microsoft": {
        "name": "Microsoft",
        "industry": "外企",
        "rating": 4.5,
        "reviews": 5620,
        "recommend": 88,
        "ceo_pct": 85,
        "breakdown": {"compensation": 4.6, "culture": 4.5, "management": 4.3, "worklife": 4.4},
        "salary_median": 35.0,
        "salary_p25": 25.0,
        "salary_p75": 50.0,
        "salary_by_role": {"python": 35.0, "frontend": 32.0, "algorithm": 45.0, "product": 33.0, "design": 26.0},
    },
    "google": {
        "name": "Google",
        "industry": "外企",
        "rating": 4.6,
        "reviews": 4320,
        "recommend": 90,
        "ceo_pct": 88,
        "breakdown": {"compensation": 4.7, "culture": 4.6, "management": 4.4, "worklife": 4.5},
        "salary_median": 38.0,
        "salary_p25": 28.0,
        "salary_p75": 55.0,
        "salary_by_role": {"python": 38.0, "frontend": 35.0, "algorithm": 50.0, "product": 36.0, "design": 28.0},
    },
    "amazon": {
        "name": "Amazon",
        "industry": "外企",
        "rating": 3.9,
        "reviews": 6780,
        "recommend": 72,
        "ceo_pct": 65,
        "breakdown": {"compensation": 4.4, "culture": 3.6, "management": 3.4, "worklife": 3.2},
        "salary_median": 32.0,
        "salary_p25": 22.0,
        "salary_p75": 46.0,
        "salary_by_role": {"python": 32.0, "frontend": 30.0, "algorithm": 42.0, "product": 31.0, "design": 24.0},
    },
    "meta": {
        "name": "Meta",
        "industry": "外企",
        "rating": 4.3,
        "reviews": 3420,
        "recommend": 82,
        "ceo_pct": 78,
        "breakdown": {"compensation": 4.5, "culture": 4.2, "management": 3.9, "worklife": 3.8},
        "salary_median": 40.0,
        "salary_p25": 28.0,
        "salary_p75": 58.0,
        "salary_by_role": {"python": 40.0, "frontend": 36.0, "algorithm": 52.0, "product": 38.0, "design": 30.0},
    },
    "apple": {
        "name": "Apple",
        "industry": "外企",
        "rating": 4.2,
        "reviews": 4560,
        "recommend": 80,
        "ceo_pct": 82,
        "breakdown": {"compensation": 4.4, "culture": 4.1, "management": 3.8, "worklife": 3.9},
        "salary_median": 36.0,
        "salary_p25": 26.0,
        "salary_p75": 52.0,
        "salary_by_role": {"python": 36.0, "frontend": 33.0, "algorithm": 48.0, "product": 34.0, "design": 27.0},
    },
    # 创业 / 新一线
    "zhiyun_keji": {
        "name": "智云科技",
        "industry": "SaaS",
        "rating": 3.7,
        "reviews": 320,
        "recommend": 68,
        "ceo_pct": 70,
        "breakdown": {"compensation": 3.6, "culture": 3.8, "management": 3.5, "worklife": 3.6},
        "salary_median": 22.0,
        "salary_p25": 15.0,
        "salary_p75": 30.0,
        "salary_by_role": {"python": 22.0, "frontend": 20.0, "algorithm": 28.0, "product": 21.0, "design": 16.0},
    },
    "xinchao_huyu": {
        "name": "新潮互娱",
        "industry": "游戏",
        "rating": 3.6,
        "reviews": 480,
        "recommend": 65,
        "ceo_pct": 62,
        "breakdown": {"compensation": 3.8, "culture": 3.5, "management": 3.3, "worklife": 3.2},
        "salary_median": 23.0,
        "salary_p25": 16.0,
        "salary_p75": 32.0,
        "salary_by_role": {"python": 23.0, "frontend": 21.0, "algorithm": 30.0, "design": 18.0},
    },
    "shulian_finance": {
        "name": "数链金融",
        "industry": "金融科技",
        "rating": 3.8,
        "reviews": 410,
        "recommend": 70,
        "ceo_pct": 68,
        "breakdown": {"compensation": 4.0, "culture": 3.6, "management": 3.5, "worklife": 3.4},
        "salary_median": 26.0,
        "salary_p25": 18.0,
        "salary_p75": 36.0,
        "salary_by_role": {"python": 26.0, "frontend": 24.0, "algorithm": 35.0, "product": 25.0, "design": 18.0},
    },
    "huizhou_education": {
        "name": "慧舟教育",
        "industry": "教育",
        "rating": 3.4,
        "reviews": 290,
        "recommend": 58,
        "ceo_pct": 55,
        "breakdown": {"compensation": 3.2, "culture": 3.5, "management": 3.3, "worklife": 3.6},
        "salary_median": 18.0,
        "salary_p25": 12.0,
        "salary_p75": 24.0,
        "salary_by_role": {"python": 18.0, "frontend": 17.0, "product": 19.0, "design": 14.0},
    },
    "lanxiang_medical": {
        "name": "蓝象医疗",
        "industry": "医疗",
        "rating": 3.7,
        "reviews": 350,
        "recommend": 67,
        "ceo_pct": 65,
        "breakdown": {"compensation": 3.6, "culture": 3.8, "management": 3.5, "worklife": 3.5},
        "salary_median": 22.0,
        "salary_p25": 15.0,
        "salary_p75": 30.0,
        "salary_by_role": {"python": 22.0, "frontend": 20.0, "product": 23.0, "design": 17.0},
    },
    "jiguang_travel": {
        "name": "极光出行",
        "industry": "出行",
        "rating": 3.5,
        "reviews": 240,
        "recommend": 60,
        "ceo_pct": 58,
        "breakdown": {"compensation": 3.5, "culture": 3.6, "management": 3.3, "worklife": 3.4},
        "salary_median": 21.0,
        "salary_p25": 14.0,
        "salary_p75": 28.0,
        "salary_by_role": {"python": 21.0, "frontend": 19.0, "product": 22.0, "design": 15.0},
    },
    "qiwu_culture": {
        "name": "栖梧文化",
        "industry": "文化",
        "rating": 3.6,
        "reviews": 180,
        "recommend": 64,
        "ceo_pct": 62,
        "breakdown": {"compensation": 3.3, "culture": 3.9, "management": 3.4, "worklife": 3.5},
        "salary_median": 17.0,
        "salary_p25": 11.0,
        "salary_p75": 23.0,
        "salary_by_role": {"design": 17.0, "product": 18.0, "frontend": 16.0},
    },
    "xiangxian_ecommerce": {
        "name": "象限电商",
        "industry": "电商",
        "rating": 3.5,
        "reviews": 380,
        "recommend": 62,
        "ceo_pct": 60,
        "breakdown": {"compensation": 3.7, "culture": 3.4, "management": 3.3, "worklife": 3.3},
        "salary_median": 20.0,
        "salary_p25": 13.0,
        "salary_p75": 27.0,
        "salary_by_role": {"python": 20.0, "frontend": 19.0, "product": 21.0, "design": 15.0},
    },
    "qiongyu_logistics": {
        "name": "穹宇物流",
        "industry": "物流",
        "rating": 3.4,
        "reviews": 220,
        "recommend": 58,
        "ceo_pct": 55,
        "breakdown": {"compensation": 3.5, "culture": 3.3, "management": 3.2, "worklife": 3.4},
        "salary_median": 18.0,
        "salary_p25": 12.0,
        "salary_p75": 25.0,
        "salary_by_role": {"python": 18.0, "frontend": 17.0, "product": 19.0, "ops": 16.0},
    },
    "yunce_data": {
        "name": "云策数据",
        "industry": "数据",
        "rating": 3.8,
        "reviews": 260,
        "recommend": 70,
        "ceo_pct": 68,
        "breakdown": {"compensation": 3.9, "culture": 3.7, "management": 3.5, "worklife": 3.6},
        "salary_median": 24.0,
        "salary_p25": 16.0,
        "salary_p75": 33.0,
        "salary_by_role": {"python": 24.0, "frontend": 22.0, "data": 26.0, "product": 23.0},
    },
    "xinghe_games": {
        "name": "星河游戏",
        "industry": "游戏",
        "rating": 3.7,
        "reviews": 410,
        "recommend": 66,
        "ceo_pct": 64,
        "breakdown": {"compensation": 3.9, "culture": 3.6, "management": 3.4, "worklife": 3.3},
        "salary_median": 23.0,
        "salary_p25": 16.0,
        "salary_p75": 32.0,
        "salary_by_role": {"python": 23.0, "frontend": 21.0, "design": 19.0, "product": 22.0},
    },
    "haitu_geo": {
        "name": "海图地理",
        "industry": "GIS",
        "rating": 3.5,
        "reviews": 150,
        "recommend": 62,
        "ceo_pct": 60,
        "breakdown": {"compensation": 3.4, "culture": 3.6, "management": 3.3, "worklife": 3.5},
        "salary_median": 19.0,
        "salary_p25": 13.0,
        "salary_p75": 26.0,
        "salary_by_role": {"python": 19.0, "frontend": 18.0, "data": 20.0},
    },
    "yuanjian_manufacturing": {
        "name": "远见制造",
        "industry": "制造",
        "rating": 3.3,
        "reviews": 320,
        "recommend": 55,
        "ceo_pct": 52,
        "breakdown": {"compensation": 3.5, "culture": 3.2, "management": 3.1, "worklife": 3.4},
        "salary_median": 17.0,
        "salary_p25": 11.0,
        "salary_p75": 23.0,
        "salary_by_role": {"python": 17.0, "frontend": 16.0, "embedded": 18.0, "ops": 15.0},
    },
    "yangfan_cross_border": {
        "name": "扬帆跨境",
        "industry": "跨境电商",
        "rating": 3.6,
        "reviews": 270,
        "recommend": 64,
        "ceo_pct": 62,
        "breakdown": {"compensation": 3.7, "culture": 3.5, "management": 3.3, "worklife": 3.4},
        "salary_median": 19.0,
        "salary_p25": 13.0,
        "salary_p75": 26.0,
        "salary_by_role": {"sales": 19.0, "product": 20.0, "frontend": 18.0, "design": 14.0},
    },
    "tuohuang_robot": {
        "name": "拓荒机器人",
        "industry": "机器人",
        "rating": 3.9,
        "reviews": 200,
        "recommend": 72,
        "ceo_pct": 70,
        "breakdown": {"compensation": 4.0, "culture": 3.8, "management": 3.6, "worklife": 3.5},
        "salary_median": 25.0,
        "salary_p25": 17.0,
        "salary_p75": 34.0,
        "salary_by_role": {"python": 25.0, "algorithm": 32.0, "embedded": 24.0, "frontend": 22.0},
    },
    # 金融
    "icbc": {
        "name": "工商银行",
        "industry": "银行",
        "rating": 3.5,
        "reviews": 8920,
        "recommend": 60,
        "ceo_pct": 65,
        "breakdown": {"compensation": 3.6, "culture": 3.4, "management": 3.3, "worklife": 3.7},
        "salary_median": 18.0,
        "salary_p25": 12.0,
        "salary_p75": 26.0,
        "salary_by_role": {"python": 18.0, "frontend": 17.0, "data": 20.0, "product": 19.0},
    },
    "cicc": {
        "name": "中金公司",
        "industry": "投行",
        "rating": 4.0,
        "reviews": 1240,
        "recommend": 74,
        "ceo_pct": 72,
        "breakdown": {"compensation": 4.4, "culture": 3.7, "management": 3.6, "worklife": 3.2},
        "salary_median": 32.0,
        "salary_p25": 20.0,
        "salary_p75": 50.0,
        "salary_by_role": {"python": 32.0, "data": 36.0, "product": 30.0, "sales": 28.0},
    },
    # 自动驾驶
    "pony_ai": {
        "name": "小马智行",
        "industry": "自动驾驶",
        "rating": 3.9,
        "reviews": 380,
        "recommend": 72,
        "ceo_pct": 70,
        "breakdown": {"compensation": 4.1, "culture": 3.8, "management": 3.5, "worklife": 3.4},
        "salary_median": 32.0,
        "salary_p25": 22.0,
        "salary_p75": 45.0,
        "salary_by_role": {"algorithm": 38.0, "python": 30.0, "embedded": 28.0, "frontend": 26.0},
    },
    "deep_route": {
        "name": "元戎启行",
        "industry": "自动驾驶",
        "rating": 3.8,
        "reviews": 220,
        "recommend": 70,
        "ceo_pct": 68,
        "breakdown": {"compensation": 4.0, "culture": 3.7, "management": 3.5, "worklife": 3.4},
        "salary_median": 30.0,
        "salary_p25": 21.0,
        "salary_p75": 42.0,
        "salary_by_role": {"algorithm": 36.0, "python": 28.0, "embedded": 27.0},
    },
    # 安全
    "qihoo_360": {
        "name": "360 集团",
        "industry": "安全",
        "rating": 3.5,
        "reviews": 4280,
        "recommend": 60,
        "ceo_pct": 55,
        "breakdown": {"compensation": 3.7, "culture": 3.4, "management": 3.2, "worklife": 3.5},
        "salary_median": 22.0,
        "salary_p25": 15.0,
        "salary_p75": 30.0,
        "salary_by_role": {"security": 24.0, "python": 22.0, "frontend": 20.0, "product": 21.0},
    },
    "qi_an_xin": {
        "name": "奇安信",
        "industry": "安全",
        "rating": 3.6,
        "reviews": 1860,
        "recommend": 64,
        "ceo_pct": 62,
        "breakdown": {"compensation": 3.7, "culture": 3.5, "management": 3.3, "worklife": 3.4},
        "salary_median": 23.0,
        "salary_p25": 16.0,
        "salary_p75": 32.0,
        "salary_by_role": {"security": 26.0, "python": 22.0, "frontend": 20.0, "ops": 19.0},
    },
    # 教育
    "new_oriental": {
        "name": "新东方",
        "industry": "教育",
        "rating": 3.4,
        "reviews": 5680,
        "recommend": 58,
        "ceo_pct": 60,
        "breakdown": {"compensation": 3.3, "culture": 3.5, "management": 3.2, "worklife": 3.6},
        "salary_median": 16.0,
        "salary_p25": 11.0,
        "salary_p75": 22.0,
        "salary_by_role": {"product": 18.0, "frontend": 16.0, "sales": 15.0},
    },
    "tAL_education": {
        "name": "好未来",
        "industry": "教育",
        "rating": 3.5,
        "reviews": 3420,
        "recommend": 60,
        "ceo_pct": 58,
        "breakdown": {"compensation": 3.5, "culture": 3.5, "management": 3.3, "worklife": 3.5},
        "salary_median": 17.0,
        "salary_p25": 12.0,
        "salary_p75": 24.0,
        "salary_by_role": {"python": 18.0, "frontend": 17.0, "product": 19.0, "data": 20.0},
    },
    # 半导体
    "cambricon": {
        "name": "寒武纪",
        "industry": "半导体",
        "rating": 3.7,
        "reviews": 480,
        "recommend": 68,
        "ceo_pct": 66,
        "breakdown": {"compensation": 4.1, "culture": 3.5, "management": 3.3, "worklife": 3.2},
        "salary_median": 32.0,
        "salary_p25": 22.0,
        "salary_p75": 45.0,
        "salary_by_role": {"algorithm": 38.0, "embedded": 30.0, "python": 28.0},
    },
    "hisilicon": {
        "name": "海思",
        "industry": "半导体",
        "rating": 4.0,
        "reviews": 3260,
        "recommend": 76,
        "ceo_pct": 78,
        "breakdown": {"compensation": 4.3, "culture": 3.7, "management": 3.6, "worklife": 3.3},
        "salary_median": 33.0,
        "salary_p25": 23.0,
        "salary_p75": 47.0,
        "salary_by_role": {"embedded": 32.0, "algorithm": 40.0, "python": 28.0},
    },
    # 新能源
    "nio": {
        "name": "蔚来汽车",
        "industry": "新能源车",
        "rating": 3.7,
        "reviews": 2840,
        "recommend": 66,
        "ceo_pct": 65,
        "breakdown": {"compensation": 3.9, "culture": 3.6, "management": 3.4, "worklife": 3.3},
        "salary_median": 25.0,
        "salary_p25": 17.0,
        "salary_p75": 35.0,
        "salary_by_role": {"embedded": 26.0, "python": 24.0, "algorithm": 32.0, "frontend": 22.0},
    },
    "xpeng": {
        "name": "小鹏汽车",
        "industry": "新能源车",
        "rating": 3.6,
        "reviews": 3120,
        "recommend": 64,
        "ceo_pct": 62,
        "breakdown": {"compensation": 3.8, "culture": 3.5, "management": 3.3, "worklife": 3.2},
        "salary_median": 24.0,
        "salary_p25": 16.0,
        "salary_p75": 34.0,
        "salary_by_role": {"embedded": 25.0, "python": 23.0, "algorithm": 31.0, "frontend": 21.0},
    },
    "li_auto": {
        "name": "理想汽车",
        "industry": "新能源车",
        "rating": 3.9,
        "reviews": 2680,
        "recommend": 72,
        "ceo_pct": 70,
        "breakdown": {"compensation": 4.0, "culture": 3.8, "management": 3.6, "worklife": 3.4},
        "salary_median": 27.0,
        "salary_p25": 18.0,
        "salary_p75": 38.0,
        "salary_by_role": {"embedded": 27.0, "python": 25.0, "algorithm": 34.0, "frontend": 23.0},
    },
    "byd": {
        "name": "比亚迪",
        "industry": "新能源车",
        "rating": 3.5,
        "reviews": 14520,
        "recommend": 62,
        "ceo_pct": 60,
        "breakdown": {"compensation": 3.6, "culture": 3.4, "management": 3.3, "worklife": 3.4},
        "salary_median": 20.0,
        "salary_p25": 13.0,
        "salary_p75": 28.0,
        "salary_by_role": {"embedded": 21.0, "python": 19.0, "frontend": 18.0, "design": 14.0},
    },
    # 物流快递
    "sf_express": {
        "name": "顺丰科技",
        "industry": "物流",
        "rating": 3.6,
        "reviews": 4820,
        "recommend": 64,
        "ceo_pct": 66,
        "breakdown": {"compensation": 3.7, "culture": 3.5, "management": 3.4, "worklife": 3.5},
        "salary_median": 21.0,
        "salary_p25": 14.0,
        "salary_p75": 29.0,
        "salary_by_role": {"python": 21.0, "frontend": 20.0, "product": 22.0, "ops": 19.0},
    },
    # 通讯
    "zte": {
        "name": "中兴通讯",
        "industry": "通信",
        "rating": 3.4,
        "reviews": 6240,
        "recommend": 58,
        "ceo_pct": 55,
        "breakdown": {"compensation": 3.5, "culture": 3.3, "management": 3.2, "worklife": 3.4},
        "salary_median": 19.0,
        "salary_p25": 13.0,
        "salary_p75": 27.0,
        "salary_by_role": {"embedded": 20.0, "python": 18.0, "frontend": 17.0, "qa": 15.0},
    },
    "vivo": {
        "name": "vivo",
        "industry": "智能硬件",
        "rating": 3.7,
        "reviews": 4280,
        "recommend": 66,
        "ceo_pct": 68,
        "breakdown": {"compensation": 3.8, "culture": 3.7, "management": 3.5, "worklife": 3.5},
        "salary_median": 23.0,
        "salary_p25": 16.0,
        "salary_p75": 32.0,
        "salary_by_role": {"embedded": 23.0, "python": 22.0, "frontend": 21.0, "design": 17.0},
    },
    "oppo": {
        "name": "OPPO",
        "industry": "智能硬件",
        "rating": 3.7,
        "reviews": 3940,
        "recommend": 66,
        "ceo_pct": 67,
        "breakdown": {"compensation": 3.8, "culture": 3.7, "management": 3.5, "worklife": 3.5},
        "salary_median": 23.0,
        "salary_p25": 16.0,
        "salary_p75": 32.0,
        "salary_by_role": {"embedded": 23.0, "python": 22.0, "frontend": 21.0, "design": 17.0},
    },
    # 制造业
    "haier": {
        "name": "海尔",
        "industry": "制造",
        "rating": 3.4,
        "reviews": 5680,
        "recommend": 58,
        "ceo_pct": 60,
        "breakdown": {"compensation": 3.5, "culture": 3.4, "management": 3.3, "worklife": 3.5},
        "salary_median": 17.0,
        "salary_p25": 11.0,
        "salary_p75": 23.0,
        "salary_by_role": {"embedded": 18.0, "python": 17.0, "frontend": 16.0, "ops": 15.0},
    },
    "midea": {
        "name": "美的",
        "industry": "制造",
        "rating": 3.5,
        "reviews": 6240,
        "recommend": 60,
        "ceo_pct": 62,
        "breakdown": {"compensation": 3.6, "culture": 3.5, "management": 3.4, "worklife": 3.5},
        "salary_median": 18.0,
        "salary_p25": 12.0,
        "salary_p75": 25.0,
        "salary_by_role": {"embedded": 19.0, "python": 18.0, "frontend": 17.0, "ops": 16.0},
    },
    # 视频/内容
    "kuaishou": {
        "name": "快手",
        "industry": "互联网",
        "rating": 3.8,
        "reviews": 5420,
        "recommend": 68,
        "ceo_pct": 65,
        "breakdown": {"compensation": 4.0, "culture": 3.7, "management": 3.5, "worklife": 3.3},
        "salary_median": 27.0,
        "salary_p25": 18.0,
        "salary_p75": 38.0,
        "salary_by_role": {"python": 27.0, "frontend": 25.0, "algorithm": 36.0, "product": 26.0, "design": 19.0},
    },
    "bilibili": {
        "name": "哔哩哔哩",
        "industry": "互联网",
        "rating": 3.9,
        "reviews": 2860,
        "recommend": 72,
        "ceo_pct": 74,
        "breakdown": {"compensation": 3.7, "culture": 4.0, "management": 3.7, "worklife": 3.6},
        "salary_median": 24.0,
        "salary_p25": 16.0,
        "salary_p75": 33.0,
        "salary_by_role": {"python": 24.0, "frontend": 22.0, "algorithm": 32.0, "design": 18.0},
    },
    "iqiyi": {
        "name": "爱奇艺",
        "industry": "互联网",
        "rating": 3.4,
        "reviews": 3640,
        "recommend": 58,
        "ceo_pct": 55,
        "breakdown": {"compensation": 3.5, "culture": 3.3, "management": 3.2, "worklife": 3.3},
        "salary_median": 21.0,
        "salary_p25": 14.0,
        "salary_p75": 29.0,
        "salary_by_role": {"python": 21.0, "frontend": 20.0, "algorithm": 28.0, "product": 22.0, "design": 16.0},
    },
    # 咨询
    "mckinsey": {
        "name": "McKinsey",
        "industry": "咨询",
        "rating": 4.4,
        "reviews": 1620,
        "recommend": 84,
        "ceo_pct": 82,
        "breakdown": {"compensation": 4.6, "culture": 4.3, "management": 4.2, "worklife": 3.4},
        "salary_median": 38.0,
        "salary_p25": 26.0,
        "salary_p75": 55.0,
        "salary_by_role": {"product": 38.0, "data": 40.0, "sales": 35.0},
    },
    # 医药
    "wx_pharma": {
        "name": "药明康德",
        "industry": "医药",
        "rating": 3.6,
        "reviews": 2460,
        "recommend": 64,
        "ceo_pct": 62,
        "breakdown": {"compensation": 3.7, "culture": 3.5, "management": 3.3, "worklife": 3.4},
        "salary_median": 20.0,
        "salary_p25": 14.0,
        "salary_p75": 28.0,
        "salary_by_role": {"python": 20.0, "data": 22.0, "product": 21.0, "qa": 16.0},
    },
}


def _stable_int(seed: str, mod: int, salt: str = "") -> int:
    h = hashlib.sha256(f"{salt}::{seed}".encode()).hexdigest()
    return int(h[:8], 16) % mod


def _resolve_company_id(company_id: str) -> str:
    """兼容 'kanzhun:bytedance' / 'bytedance' / '字节跳动' 三种 ID."""
    cid = company_id.lower().strip()
    if ":" in cid:
        cid = cid.split(":", 1)[1]
    if cid in _MOCK_COMPANIES:
        return cid
    # 中文名 → slug
    for slug, info in _MOCK_COMPANIES.items():
        if info["name"].lower() == cid or info["name"] == company_id.strip():
            return slug
    return cid  # 未知公司,返回原 id,后续按兜底生成


def _make_review(idx: int, company_id: str, info: dict[str, Any]) -> Review:
    """生成单条评价 (基于 idx 稳定)."""
    title_templates = [
        "团队氛围好,技术栈先进",
        "福利待遇不错,加班较多",
        "管理规范,流程清晰",
        "成长空间大,学习机会多",
        "工作强度大,但能学到东西",
        "薪资有竞争力,晋升机制待优化",
        "福利完善,工作生活平衡好",
        "创新氛围浓,适合年轻人",
    ]
    pros_templates = [
        "技术氛围好,同事优秀",
        "薪资高于行业平均",
        "福利完善,五险一金齐全",
        "工作环境好,设备齐全",
        "晋升机制透明",
        "培训体系完善",
    ]
    cons_templates = [
        "加班较多",
        "晋升速度慢",
        "流程繁琐",
        "跨部门协作效率低",
        "工作压力大",
        "部分业务方向不清晰",
    ]
    statuses = ["在职", "离职"]
    job_titles = ["Python 后端工程师", "前端工程师", "产品经理", "数据分析师", "算法工程师", "UI 设计师"]

    return Review(
        id=f"mock-{company_id}-{idx}",
        source="mock",
        title=title_templates[idx % len(title_templates)],
        content=f"整体体验: {info['name']} 在 {info['industry']} 行业属于头部公司。"
        f"工作 {3 + idx % 5} 年,主要感受: 技术氛围浓厚,项目节奏快,适合想快速成长的同学。",
        pros=pros_templates[idx % len(pros_templates)],
        cons=cons_templates[idx % len(cons_templates)],
        rating=round(max(1.0, min(5.0, info["rating"] + ((idx % 5) - 2) * 0.1)), 1),
        job_title=job_titles[idx % len(job_titles)],
        employment_status=statuses[idx % len(statuses)],
        created_at=(datetime.now(tz=timezone.utc) - timedelta(days=idx * 7)).isoformat(),
        author=f"匿名员工_{1000 + idx}",
        helpful_count=_stable_int(f"{company_id}-{idx}-help", 500, salt="mock"),
    )


def _make_interview(idx: int, company_id: str, info: dict[str, Any]) -> InterviewExperience:
    """生成面试经验."""
    processes = [
        "1 轮笔试 + 2 轮技术面 + 1 轮 HR 面",
        "2 轮技术面 + 1 轮 leader 面",
        "3 轮技术面 + 1 轮 CTO 面",
        "1 轮视频初筛 + 2 轮现场技术面 + 1 轮 HR 面",
    ]
    question_bank = [
        "请介绍你最满意的项目?",
        "如何排查线上 OOM 问题?",
        "Redis 和 Memcached 的区别?",
        "解释一下 CAP 定理",
        "设计一个短链生成系统",
        "TCP 三次握手为什么不是两次?",
        "数据库索引底层原理?",
        "进程和线程的区别?",
        "LRU 缓存怎么实现?",
        "算法题: 二叉树的层序遍历",
    ]
    experiences = ["positive", "neutral", "negative"]
    results = ["offer", "rejected", "pending", "no_response"]
    job_titles = ["Python 后端工程师", "前端工程师", "算法工程师", "产品经理"]

    base_q = _stable_int(company_id + str(idx), 5, salt="mock-int") + 1
    questions = [question_bank[(idx * 3 + i) % len(question_bank)] for i in range(min(base_q, 5))]

    return InterviewExperience(
        id=f"mock-int-{company_id}-{idx}",
        source="mock",
        company_id=company_id,
        job_title=job_titles[idx % len(job_titles)],
        difficulty=((idx % 5) + 1),
        experience=experiences[idx % len(experiences)],
        process=processes[idx % len(processes)],
        questions=questions,
        result=results[idx % len(results)],
        created_at=(datetime.now(tz=timezone.utc) - timedelta(days=idx * 3)).isoformat(),
        author=f"匿名面经_{2000 + idx}",
    )


class MockCompanyReviewProvider(CompanyReviewProvider):
    """纯本地 mock,不联网,数据完全确定性."""

    provider_name = "mock"

    def __init__(self, *, seed: str = "waibao-v6-company") -> None:
        self._seed = seed
        self._cache: dict[str, tuple[float, Any]] = {}

    def _cache_get(self, key: str) -> Any | None:
        item = self._cache.get(key)
        if item is None:
            return None
        ts, value = item
        if time.monotonic() - ts > 3600.0:  # 1 小时
            self._cache.pop(key, None)
            return None
        return value

    def _cache_put(self, key: str, value: Any) -> None:
        self._cache[key] = (time.monotonic(), value)

    def _get_info(self, company_id: str) -> dict[str, Any]:
        """获取/兜底生成公司信息."""
        slug = _resolve_company_id(company_id)
        if slug in _MOCK_COMPANIES:
            return _MOCK_COMPANIES[slug]
        # 未知公司 — 兜底生成
        return {
            "name": company_id,
            "industry": "未知",
            "rating": 3.5,
            "reviews": 0,
            "recommend": 60,
            "ceo_pct": 60,
            "breakdown": {"compensation": 3.5, "culture": 3.5, "management": 3.5, "worklife": 3.5},
            "salary_median": 20.0,
            "salary_p25": 14.0,
            "salary_p75": 28.0,
            "salary_by_role": {},
        }

    @with_resilience(
        provider="company_review",
        method="get_company_reviews",
        retry=RetryPolicy(max_retries=1, base_delay=0.1, jitter=0.0),
        rate_per_sec=100.0,
        burst=200,
    )
    async def get_company_reviews(self, company_id: str) -> CompanyRating:
        info = self._get_info(company_id)
        return CompanyRating(
            source="mock",
            score=info["rating"],
            review_count=info["reviews"],
            recommend_pct=info["recommend"],
            ceo_pct=info["ceo_pct"],
            breakdown=info["breakdown"],
        )

    @with_resilience(
        provider="company_review",
        method="get_employee_reviews",
        retry=RetryPolicy(max_retries=1, base_delay=0.1, jitter=0.0),
        rate_per_sec=100.0,
        burst=200,
    )
    async def get_employee_reviews(
        self,
        company_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> list[Review]:
        info = self._get_info(company_id)
        slug = _resolve_company_id(company_id)
        # 默认生成 30 条 (按 slug 稳定)
        n = min(30, max(5, info["reviews"] // 50)) if info["reviews"] else 10
        all_reviews = [_make_review(i, slug, info) for i in range(n)]
        all_reviews.sort(key=lambda r: r.created_at or "", reverse=True)
        start = (page - 1) * page_size
        return all_reviews[start : start + page_size]

    @with_resilience(
        provider="company_review",
        method="get_interview_experiences",
        retry=RetryPolicy(max_retries=1, base_delay=0.1, jitter=0.0),
        rate_per_sec=100.0,
        burst=200,
    )
    async def get_interview_experiences(
        self,
        company_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> list[InterviewExperience]:
        info = self._get_info(company_id)
        slug = _resolve_company_id(company_id)
        n = min(20, max(3, info["reviews"] // 100)) if info["reviews"] else 6
        all_ints = [_make_interview(i, slug, info) for i in range(n)]
        all_ints.sort(key=lambda r: r.created_at or "", reverse=True)
        start = (page - 1) * page_size
        return all_ints[start : start + page_size]

    @with_resilience(
        provider="company_review",
        method="get_salary_insights",
        retry=RetryPolicy(max_retries=1, base_delay=0.1, jitter=0.0),
        rate_per_sec=100.0,
        burst=200,
    )
    async def get_salary_insights(self, company_id: str) -> SalaryInsights:
        info = self._get_info(company_id)
        slug = _resolve_company_id(company_id)
        return SalaryInsights(
            company_id=slug,
            median_k=info["salary_median"],
            p25_k=info["salary_p25"],
            p75_k=info["salary_p75"],
            sample_size=max(10, info["reviews"] // 10),
            currency="CNY",
            by_role=info["salary_by_role"],
            last_updated=datetime.now(tz=timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    def list_companies(self) -> list[dict[str, Any]]:
        """导出所有公司基础信息 (供前端搜索 / 测试)."""
        return [
            {"id": slug, **info}
            for slug, info in _MOCK_COMPANIES.items()
        ]

    def search_companies(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """按名称模糊搜索."""
        if not query:
            return []
        q = query.lower().strip()
        results: list[tuple[int, dict[str, Any]]] = []
        for slug, info in _MOCK_COMPANIES.items():
            name = info["name"].lower()
            score = 0
            if q == name or q == slug:
                score = 100
            elif q in name:
                score = 80
            elif any(q in alias for alias in [name, slug]):
                score = 60
            if score > 0:
                results.append((score, {"id": slug, **info}))
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]