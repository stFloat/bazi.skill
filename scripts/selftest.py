#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bazi 技能自测（回归测试）
=========================
把"已知正确值"写成断言，防止历法相关的改动静默破坏排盘。

运行：
  PY="C:/Users/DWHadmin/.workbuddy/binaries/python/envs/py311/Scripts/python.exe"
  PYTHONIOENCODING=utf-8 "$PY" scripts/selftest.py

全部通过输出 OK，任一失败以非零码退出。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bazi
import truesolar

FAIL = []
PASS = 0
VERBOSE = "-v" in sys.argv or "--verbose" in sys.argv
RESULTS = []


def check(name, got, want):
    global PASS
    ok = got == want
    if ok:
        PASS += 1
    else:
        FAIL.append(f"{name}: 期望 {want!r}，实得 {got!r}")
    RESULTS.append((ok, name, got, want))


def gz(y):
    g, z = bazi.year_gz_of(y)
    return bazi.GAN[g] + bazi.ZHI[z]


# ---------------------------------------------------------------- 立春日期
# 1900–2100 实测分布：2/3 共39年、2/4 共128年、2/5 共34年（最晚 2/5）
check("1980 立春日（全史最晚）", bazi.lichun_date(1980)[1:], (2, 5))
check("1976 立春日（2/5）", bazi.lichun_date(1976)[1:], (2, 5))
check("2024 立春日（常规2/4）", bazi.lichun_date(2024)[1:], (2, 4))
check("2025 立春日（2/3）", bazi.lichun_date(2025)[1:], (2, 3))
check("2029 立春日（2/3）", bazi.lichun_date(2029)[1:], (2, 3))


# ------------------------------------------------- 立春交节时刻（外部可核）
# 这几条不依赖本仓库的任何假设，可与公开天文历表逐秒比对。
# 注意 sxtwl 的 Time 对象把时/分/秒分为 h、m、s 三个字段，
# 不是"h 带小数"——按后者解析会得出整点时刻的错误结论。
def lichun_moment(y):
    import sxtwl
    t = sxtwl.JD2DD(bazi._lichun_jd(y))
    return "%04d-%02d-%02d %02d:%02d:%02d" % (
        t.Y, t.M, t.D, int(t.h), int(t.m), int(t.s))


check("2024 立春时刻", lichun_moment(2024), "2024-02-04 16:26:53")
check("2025 立春时刻", lichun_moment(2025), "2025-02-03 22:10:13")
check("1980 立春时刻（过午夜9分钟）", lichun_moment(1980), "1980-02-05 00:09:27")

# ---------------------------------------------------------------- 年干支
check("1980 年干支", gz(1980), "庚申")
check("1976 年干支", gz(1976), "丙辰")
check("1984 年干支", gz(1984), "甲子")
check("2024 年干支", gz(2024), "甲辰")
check("2025 年干支", gz(2025), "乙巳")
check("2026 年干支", gz(2026), "丙午")
check("2029 年干支", gz(2029), "己酉")
check("2033 年干支", gz(2033), "癸丑")

# ------------------------------------------------- 年柱必须按立春换年（非 1/1）
def year_pillar(y, m, d, H=12, M=0):
    r = bazi.compute(y, m, d, H, M, "male")
    return r["pillars"]["year"]


check("2025-02-02 出生年柱（立春前）", year_pillar(2025, 2, 2), "甲辰")
check("2025-02-04 出生年柱（立春后）", year_pillar(2025, 2, 4), "乙巳")
check("1980-02-04 出生年柱（2/5立春前）", year_pillar(1980, 2, 4), "己未")
check("1980-02-06 出生年柱（2/5立春后）", year_pillar(1980, 2, 6), "庚申")

# ------------------- 交节时刻的分钟级精度（1980 立春 2/5 00:09:27，紧贴午夜）
check("1980-02-04 23:59 年柱（差10分钟交节）", year_pillar(1980, 2, 4, 23, 59), "己未")
check("1980-02-05 00:05 年柱（交节前5分钟）", year_pillar(1980, 2, 5, 0, 5), "己未")
check("1980-02-05 00:15 年柱（交节后6分钟）", year_pillar(1980, 2, 5, 0, 15), "庚申")

# ---------------------------------------------------------------- 基准案例
# 用构造日期做回归锚点（非任何真实出生信息）：己巳 戊辰 壬寅 甲辰，身弱杀重
BASE = bazi.compute(1989, 4, 12, 8, 0, "male")
check("基准案例四柱", BASE["pillars"],
      {"year": "己巳", "month": "戊辰", "day": "壬寅", "hour": "甲辰"})
check("基准案例日主", BASE["day_master"], "壬")
check("基准案例旺衰层级", BASE["strength_eval"]["level"], "身弱")
check("基准案例空亡", BASE["kongwang"], "辰、巳")
check("基准案例起运", BASE["dayun"]["start_age_value"], 2.4)
check("基准案例第3运干支", BASE["dayun"]["list"][2]["ganzhi"], "乙丑")
check("基准案例第5运干支", BASE["dayun"]["list"][4]["ganzhi"], "癸亥")

# ------------------------------------------------- 流年序列（曾错位一年的 bug）
LN = {x["year"]: x["ganzhi"] for x in bazi.get_liunian(
    bazi.GAN.index("甲"), 2024, 6)}
check("流年 2024", LN[2024], "甲辰")
check("流年 2025", LN[2025], "乙巳")
check("流年 2026", LN[2026], "丙午")
check("流年 2027", LN[2027], "丁未")
check("流年 2029", LN[2029], "己酉")

# ------------------------------- 独立交叉验证：纯算式 vs 立春法（1900–2100 全量）
# 上面的断言都是本仓库自己写的期望值，若期望本身写错，测试会"自洽地通过"。
# 这里用完全不依赖 sxtwl 的六十甲子循环算式对碰，能抓出此类同源错误。
def _gz_by_cycle(y):
    i = (y - 1984) % 60
    return bazi.GAN[i % 10] + bazi.ZHI[i % 12]


_mismatch = [y for y in range(1900, 2101) if gz(y) != _gz_by_cycle(y)]
check("1900-2100 年干支与六十循环零差异", _mismatch, [])

# ---------------------------------------------------------------- 真太阳时
lon, _ = truesolar.resolve_lon("成都")
check("成都经度", round(lon, 2), 104.07)

lon_bj, _ = truesolar.resolve_lon("北京")
check("北京经度", round(lon_bj, 2), 116.41)

lon_w, _ = truesolar.resolve_lon("乌鲁木齐")
check("乌鲁木齐经度", round(lon_w, 2), 87.62)

# 成都 2000-01-01 12:00 → 10:53 巳时，余量仅 7 分钟（极高风险，用于验证边界告警）
eot = truesolar.eot_minutes(__import__("datetime").date(2000, 1, 1), 12)
total = (104.07 - 120.0) * 4.0 + eot
check("成都该日合计修正（分钟）", round(total, 1), -66.6)
check("修正后小时", 12 * 60 + round(total), 653)

sc, margin, _ = truesolar.shichen_of(10, 53)
check("10:53 时辰", sc, "巳时")
check("10:53 距边界", round(margin), 7)

sc2, _, _ = truesolar.shichen_of(23, 30)
check("23:30 时辰（子时跨日）", sc2, "子时")

# ---------------------------------------------------------------- 结果
if VERBOSE:
    for ok, name, got, want in RESULTS:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {name:<28} {got!r}" + ("" if ok else f"  (期望 {want!r})"))
    print()

print(f"通过 {PASS} 项 / 共 {len(RESULTS)} 项")
if FAIL:
    print(f"失败 {len(FAIL)} 项：")
    for f in FAIL:
        print("  ✗", f)
    sys.exit(1)
print("OK")
