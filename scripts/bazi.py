# -*- coding: utf-8 -*-
"""
八字排盘引擎（bazi.py）
===================
给定公历出生时间 + 性别，精确排出：
  四柱（年/月/日/时干支，以立春、节气为界）
  十神、地支藏干、五行旺衰评分、日主强弱
  大运（起运岁数 + 干支序列）、神煞、纳音、流年十神

依赖：sxtwl（寿星天文历，pip install sxtwl）—— 干支与节气按天文历精确计算。
设计原则：排盘只由本脚本确定性算出，绝不让模型手推；解读由 AI 依据
references/ 中的方法论完成。

用法：
  python bazi.py -y 1990 -m 1 -d 15 -H 12 -M 0 -s male
  python bazi.py -y 1988 -m 6 -d 18 -H 22 -M 30 -s female --json
  python bazi.py -y 1990 -m 1 -d 15 -H 12 -M 0 -s male --liunian 2024
"""

import argparse
import datetime
import json
import sys

try:
    import sxtwl
except ImportError:
    sys.stderr.write("缺少依赖 sxtwl，请先执行：pip install sxtwl\n")
    raise

# ---------- 基础常量 ----------
GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
GAN_WX = ["木", "木", "火", "火", "土", "土", "金", "金", "水", "水"]
ZHI_WX = ["水", "土", "木", "木", "土", "火", "火", "土", "金", "金", "土", "水"]
GAN_YIN = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]   # 0=阳 1=阴
ZHI_YIN = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
SHEN_10 = ["比肩", "劫财", "食神", "伤官", "正财", "偏财", "正官", "七杀", "正印", "偏印"]

# 地支藏干：(本气, 中气, 余气) 天干序号；None 表示该层无藏干
CANG = {
    0: (9, None, None),       # 子: 癸
    1: (5, 9, 7),             # 丑: 己癸辛
    2: (0, 2, 4),             # 寅: 甲丙戊
    3: (1, None, None),       # 卯: 乙
    4: (4, 1, 9),             # 辰: 戊乙癸
    5: (2, 6, 4),             # 巳: 丙庚戊
    6: (3, 5, None),          # 午: 丁己
    7: (5, 3, 1),             # 未: 己丁乙
    8: (6, 8, 4),             # 申: 庚壬戊
    9: (7, None, None),       # 酉: 辛
    10: (4, 7, 3),            # 戌: 戊辛丁
    11: (8, 0, None),         # 亥: 壬甲
}

# 六十甲子纳音（按干支序 0..59）
NAYIN = [
    "海中金", "海中金", "炉中火", "炉中火", "大林木", "大林木",
    "路旁土", "路旁土", "剑锋金", "剑锋金", "山头火", "山头火",
    "涧下水", "涧下水", "城头土", "城头土", "白蜡金", "白蜡金",
    "杨柳木", "杨柳木", "泉中水", "泉中水", "屋上土", "屋上土",
    "霹雳火", "霹雳火", "松柏木", "松柏木", "长流水", "长流水",
    "沙中金", "沙中金", "山下火", "山下火", "平地木", "平地木",
    "壁上土", "壁上土", "金箔金", "金箔金", "覆灯火", "覆灯火",
    "天河水", "天河水", "大驿土", "大驿土", "钗钏金", "钗钏金",
    "桑柘木", "桑柘木", "大溪水", "大溪水", "沙中土", "沙中土",
    "天上火", "天上火", "石榴木", "石榴木", "大海水", "大海水",
]


# ---------- 工具函数 ----------
def gz_to_seq(g, z):
    for k in range(60):
        if k % 10 == g and k % 12 == z:
            return k
    raise ValueError("invalid gz")


def seq_to_gz(k):
    return (k % 10, k % 12)


def sheng(w1, w2):
    order = ["木", "火", "土", "金", "水"]
    return order[(order.index(w1) + 1) % 5] == w2


def ke(w1, w2):
    order = ["木", "火", "土", "金", "水"]
    return order[(order.index(w1) + 2) % 5] == w2


def shishen(rg, g):
    """日主天干 rg 对他干 g 的十神序号。"""
    if GAN_WX[g] == GAN_WX[rg]:
        return 0 if GAN_YIN[g] == GAN_YIN[rg] else 1
    if sheng(GAN_WX[rg], GAN_WX[g]):
        return 2 if GAN_YIN[g] == GAN_YIN[rg] else 3
    if ke(GAN_WX[rg], GAN_WX[g]):
        return 4 if GAN_YIN[g] != GAN_YIN[rg] else 5
    if ke(GAN_WX[g], GAN_WX[rg]):
        return 6 if GAN_YIN[g] != GAN_YIN[rg] else 7
    if sheng(GAN_WX[g], GAN_WX[rg]):
        return 8 if GAN_YIN[g] != GAN_YIN[rg] else 9
    return -1


def wang_xiang(rg_wx, month_zhi):
    m_wx = ZHI_WX[month_zhi]
    if m_wx == rg_wx:
        return "旺"
    if sheng(m_wx, rg_wx):
        return "相"
    if sheng(rg_wx, m_wx):
        return "休"
    if ke(m_wx, rg_wx):
        return "囚"
    if ke(rg_wx, m_wx):
        return "死"
    return "休"


def month_branch_of(y, mo, d, h=12, mi=0):
    """用 sxtwl 精确取该日（正午）的月支（节气为界）。"""
    return sxtwl.fromSolar(y, mo, d).getMonthGZ().dz


def datetime_to_jd(year, month, day, hour, minute):
    if month <= 2:
        year -= 1
        month += 12
    a = int(year / 100)
    b = 2 - a + int(a / 4)
    jd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + b - 1524.5
    jd += (hour + minute / 60.0) / 24.0
    return jd


# 月支 -> 起始"节"名称（12 节）
MZ_JIE = {2: "立春", 3: "惊蛰", 4: "清明", 5: "立夏", 6: "芒种", 7: "小暑",
          8: "立秋", 9: "白露", 10: "寒露", 11: "立冬", 0: "大雪", 1: "小寒"}
# 各"节"的公历大致月日（用于从 sxtwl 返回中识别该节）
JIE_EXPECT = {"立春": (2, 4), "惊蛰": (3, 6), "清明": (4, 5), "立夏": (5, 6),
              "芒种": (6, 6), "小暑": (7, 7), "立秋": (8, 8), "白露": (9, 8),
              "寒露": (10, 8), "立冬": (11, 7), "大雪": (12, 7), "小寒": (1, 5)}


def collect_jie(year):
    """收集 year-1..year+1 共三年里 12 节的 JD（以 JD2DD 校验真实日期）。"""
    res = {}
    for yr in (year - 1, year, year + 1):
        jqs = sxtwl.getJieQiByYear(yr)
        for info in jqs:
            if info is None:
                continue
            t = sxtwl.JD2DD(info.jd)
            md = (t.getMonth(), t.getDay())
            ay = t.getYear()
            for name, (em, ed) in JIE_EXPECT.items():
                if md[0] == em and abs(md[1] - ed) <= 2:
                    res[(name, ay)] = info.jd
    return res


MZ_JIE_INV = {v: k for k, v in MZ_JIE.items()}

# 立春最晚日兜底。1900–2100 实测分布：2/3 共 39 年、2/4 共 128 年、2/5 共 34 年，
# 最晚不超过 2/5（1980 年之后未再出现）。仅在精确节气取不到时启用，**不默认 2/4**。
LICHUN_FALLBACK = (2, 5)


def _lichun_jd(year):
    """取 year 年立春的儒略日。取不到返回 None。"""
    res = collect_jie(year)
    return {ay: j for (name, ay), j in res.items() if name == "立春"}.get(year)


def lichun_date(year):
    """返回 year 年立春的公历 (年, 月, 日)。以 sxtwl 实测节气为准。"""
    jd = _lichun_jd(year)
    if jd is None:
        return (year,) + LICHUN_FALLBACK
    t = sxtwl.JD2DD(jd)
    return (t.getYear(), t.getMonth(), t.getDay())


def year_gz_of(year):
    """取 year 年（立春之后）的年干支。

    **必须以该年实测立春为基准**，不能用年中日期近似。
    立春在 2/3~2/5 之间浮动（1900–2100 实测分布 39/128/34 年），
    取年中虽然"恰好"落在前后两个立春之间、结果不会错，但那是碰巧落在区间内，
    不是按定义取——一旦区间边界因历法误差或外推范围变化而移动，就会静默出错。
    """
    jd = _lichun_jd(year)
    if jd is None:
        # 兜底：最晚立春为 2/5，取其次日 2/6 确保已进新年
        dd = sxtwl.fromSolar(year, LICHUN_FALLBACK[0], LICHUN_FALLBACK[1] + 1)
    else:
        # 交节发生在具体时刻，取立春后 1 天，确保已过交节
        t = sxtwl.JD2DD(jd + 1.0)
        dd = sxtwl.fromSolar(t.getYear(), t.getMonth(), t.getDay())
    gz = dd.getYearGZ()
    return gz.tg, gz.dz


def _wuhu_dun(yg, mz):
    """五虎遁：年干 yg + 月支 mz -> 月干。"""
    start = {0: 2, 5: 2, 1: 4, 6: 4, 2: 6, 7: 6, 3: 8, 8: 8, 4: 0, 9: 0}
    return (start[yg] + (mz - 2) % 12) % 10


def _build_jie_list(year):
    res = collect_jie(year)
    return [(jd, MZ_JIE_INV[name]) for (name, ay), jd in res.items()]


def _true_month_branch(birth_jd, jie_list):
    cand = [jd for jd, b in jie_list if jd <= birth_jd]
    if not cand:
        return min(jie_list, key=lambda x: x[0])[1]
    start_jd = max(cand)
    for jd, b in jie_list:
        if jd == start_jd:
            return b
    return jie_list[0][1]


def _true_year_gz(birth_jd, year):
    res = collect_jie(year)
    lc = {ay: jd for (name, ay), jd in res.items() if name == '立春'}
    actual = None
    for Y in sorted(lc):
        if lc[Y] <= birth_jd:
            actual = Y
    if actual is None:
        actual = min(lc)
    # 用该年实测立春为基准取年干支（不再用年中近似）
    return year_gz_of(actual)


# ---------- 核心排盘 ----------
def compute(year, month, day, hour, minute, sex, use_night_zi=True):
    result = {}
    result["input"] = {
        "solar": f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}",
        "sex": sex, "use_night_zi": use_night_zi,
    }

    birth_jd = datetime_to_jd(year, month, day, hour, minute)
    yg, yz = _true_year_gz(birth_jd, year)
    jie_list = _build_jie_list(year)
    mz = _true_month_branch(birth_jd, jie_list)
    mg = _wuhu_dun(yg, mz)

    # 晚子时：23:00-23:59 时干取次日日干
    cy, cm, cd, ch = year, month, day, hour
    if use_night_zi and hour == 23:
        dt = datetime.date(year, month, day) + datetime.timedelta(days=1)
        cy, cm, cd = dt.year, dt.month, dt.day
        ch = 0

    d = sxtwl.fromSolar(cy, cm, cd)
    rg, rz = d.getDayGZ().tg, d.getDayGZ().dz
    hg, hz = d.getHourGZ(ch).tg, d.getHourGZ(ch).dz

    pillars = {"year": (yg, yz), "month": (mg, mz), "day": (rg, rz), "hour": (hg, hz)}
    result["pillars"] = {
        "year": f"{GAN[yg]}{ZHI[yz]}", "month": f"{GAN[mg]}{ZHI[mz]}",
        "day": f"{GAN[rg]}{ZHI[rz]}", "hour": f"{GAN[hg]}{ZHI[hz]}",
    }
    result["day_master"] = GAN[rg]
    result["day_master_wx"] = GAN_WX[rg]
    result["day_master_yin"] = "阳" if GAN_YIN[rg] == 0 else "阴"

    result["pillar_shishen"] = {
        "year": SHEN_10[shishen(rg, yg)],
        "month": SHEN_10[shishen(rg, mg)],
        "day": "日主",
        "hour": SHEN_10[shishen(rg, hg)],
    }

    # 地支藏干 + 十神（含日支）
    hidden = {}
    for name in ("year", "month", "day", "hour"):
        g, z = pillars[name]
        items = []
        for idx, sg in enumerate(CANG[z]):
            if sg is None:
                continue
            level = "本气" if idx == 0 else ("中气" if idx == 1 else "余气")
            items.append({
                "gan": GAN[sg], "wx": GAN_WX[sg], "level": level,
                "shishen": SHEN_10[shishen(rg, sg)],
            })
        hidden[name] = items
    result["hidden_stems"] = hidden

    result["nayin"] = {
        "year": NAYIN[gz_to_seq(yg, yz)], "month": NAYIN[gz_to_seq(mg, mz)],
        "day": NAYIN[gz_to_seq(rg, rz)], "hour": NAYIN[gz_to_seq(hg, hz)],
    }

    # 五行统计 + 旺衰评分
    wx_count = {w: 0.0 for w in GAN_WX}
    strength = 0.0
    weight_table = {"本气": 1.0, "中气": 0.6, "余气": 0.3}

    def add_gan(g, factor):
        nonlocal strength
        if GAN_WX[g] == GAN_WX[rg]:
            strength += 3 * factor
        elif sheng(GAN_WX[rg], GAN_WX[g]):
            strength -= 2 * factor
        elif ke(GAN_WX[rg], GAN_WX[g]):
            strength -= 1.5 * factor
        elif ke(GAN_WX[g], GAN_WX[rg]):
            strength -= 2.5 * factor
        elif sheng(GAN_WX[g], GAN_WX[rg]):
            strength += 3 * factor

    for name in ("year", "month", "hour"):
        g, z = pillars[name]
        wx_count[GAN_WX[g]] += 1.0
        add_gan(g, 1.0)
    for name in ("year", "month", "day", "hour"):
        g, z = pillars[name]
        base_factor = 3.0 if name == "month" else (2.0 if name == "day" else 1.0)
        for s in hidden[name]:
            wgt = weight_table[s["level"]]
            wx_count[s["wx"]] += wgt
            add_gan(GAN.index(s["gan"]), base_factor * wgt)

    result["wx_count"] = {k: round(v, 2) for k, v in wx_count.items()}

    de_ling = wang_xiang(GAN_WX[rg], mz) in ("旺", "相")
    de_di = any(GAN_WX[CANG[z][0]] == GAN_WX[rg] for (g, z) in
                [pillars["year"], pillars["month"], pillars["hour"], (0, rz)])
    help_gan = sum(1 for name in ("year", "month", "hour")
                   if (GAN_WX[pillars[name][0]] == GAN_WX[rg]
                       or sheng(GAN_WX[pillars[name][0]], GAN_WX[rg])))
    de_shi = help_gan >= 2

    score = round(strength, 2)
    if score >= 12 and de_ling:
        level = "身强"
    elif score <= 0 and not de_ling:
        level = "身弱"
    elif score >= 6:
        level = "偏强"
    elif score <= 4:
        level = "偏弱"
    else:
        level = "中和"

    result["strength_eval"] = {
        "score": score, "wang_xiang": wang_xiang(GAN_WX[rg], mz),
        "de_ling": de_ling, "de_di": de_di, "de_shi": de_shi, "level": level,
    }
    result["tiaohou"] = tiaohou(mz)
    result["yongshen_rough"] = {
        "level": level,
        "xi": ("克泄耗（官杀/食伤/财）" if level in ("身强", "偏强")
               else "生扶（印/比劫）" if level in ("身弱", "偏弱")
               else "酌宜酌忌，视组合而定"),
        "ji": ("生扶（印/比劫）" if level in ("身强", "偏强")
               else "克泄耗（官杀/食伤/财）" if level in ("身弱", "偏弱")
               else "不宜偏颇"),
    }
    result["pattern"] = get_pattern(rg, mz, hidden["month"])
    result["shensha"] = get_shensha(rg, rz, pillars)
    result["kongwang"] = kongwang(rg, rz)
    result["dayun"] = get_dayun(yg, mg, mz, rg, rz, year, month, day, hour, minute, sex)
    return result


# ---------- 调候 / 格局 / 神煞 ----------
def tiaohou(mz):
    if mz in (10, 11, 0):
        return "寒（冬月），调候喜 丙火、戊土 暖局"
    if mz in (4, 5, 6):
        return "燥（夏月），调候喜 壬水、癸水 润局"
    if mz in (1, 2):
        return "余寒初春，调候喜 丙火"
    return "寒暖适中"


def get_pattern(rg, mz, month_hidden):
    ben = CANG[mz][0]
    s = shishen(rg, ben)
    pattern_map = {
        6: "正官格", 7: "七杀格（偏官格）", 4: "正财格", 5: "偏财格",
        8: "正印格", 9: "偏印格（枭神格）", 2: "食神格", 3: "伤官格",
    }
    pat = pattern_map.get(s, SHEN_10[s])
    return {
        "name": pat, "month_root": GAN[ben], "root_shishen": SHEN_10[s],
        "note": "以月令本气取格；完整取格须看月支藏干（本/中/余气）何者透出天干（子平真诠：月令为提纲，透则成格）",
    }


def get_shensha(rg, rz, pillars):
    out = {}
    zhis = [pillars[n][1] for n in ("year", "month", "day", "hour")]
    gui_ren = {
        0: [1, 7], 2: [1, 7], 4: [1, 7],
        1: [0, 8], 5: [0, 8],
        3: [11, 9], 6: [11, 9],
        8: [3, 5], 9: [3, 5],
        7: [2, 6],
    }
    gr = gui_ren.get(rg, [])
    found = [ZHI[z] for z in zhis if z in gr]
    out["天乙贵人"] = "、".join(found) if found else "无"
    wc_map = {0: 5, 1: 6, 2: 8, 3: 9, 4: 8, 5: 9, 6: 11, 7: 0, 8: 2, 9: 3}  # 文昌：甲巳、乙午、丙戊申、丁己酉、庚亥、辛子、壬寅、癸卯
    wc = wc_map[rg]
    out["文昌"] = ZHI[wc] if wc in zhis else f"{ZHI[wc]}（不在四柱）"
    tao = {2: 3, 6: 3, 10: 3, 8: 9, 0: 9, 4: 9, 11: 0, 3: 0, 7: 0, 5: 6, 9: 6, 1: 6}  # 咸池：寅午戌→卯、申子辰→酉、亥卯未→寅、巳酉丑→午
    th = tao[rz]
    out["桃花"] = ZHI[th] if th in zhis else f"{ZHI[th]}（不在四柱）"
    yi = {2: 8, 6: 8, 10: 8, 8: 2, 0: 2, 4: 2, 11: 5, 3: 5, 7: 5, 5: 11, 9: 11, 1: 11}  # 驿马：寅午戌→申、申子辰→寅、亥卯未→巳、巳酉丑→亥
    ym = yi[rz]
    out["驿马"] = ZHI[ym] if ym in zhis else f"{ZHI[ym]}（不在四柱）"
    hua = {2: 10, 6: 10, 10: 10, 8: 4, 0: 4, 4: 4, 11: 7, 3: 7, 7: 7, 5: 1, 9: 1, 1: 1}  # 华盖：寅午戌→戌、申子辰→辰、亥卯未→未、巳酉丑→丑
    hg_ = hua[rz]
    out["华盖"] = ZHI[hg_] if hg_ in zhis else f"{ZHI[hg_]}（不在四柱）"
    yang_ren = {0: 3, 2: 6, 4: 6, 6: 9, 8: 0}
    if rg in yang_ren:
        yr = yang_ren[rg]
        out["羊刃"] = ZHI[yr] if yr in zhis else f"{ZHI[yr]}（不在四柱）"
    else:
        out["羊刃"] = "阴干无刃（派别不同，或取冠带位）"
    if (rg, rz) in [(6, 10), (6, 4), (8, 10), (4, 4)]:
        out["魁罡"] = f"{GAN[rg]}{ZHI[rz]}（魁罡格）"
    else:
        out["魁罡"] = "无"
    bai = [(0, 4), (1, 5), (2, 8), (3, 11), (4, 10), (5, 1), (6, 4), (7, 5), (8, 8), (9, 11)]
    out["十恶大败"] = "是" if (rg, rz) in bai else "否"
    return out


def kongwang(rg, rz):
    starts = [(0, 0), (0, 10), (0, 8), (0, 6), (0, 4), (0, 2)]
    seqd = gz_to_seq(rg, rz)
    for (sg, sz) in starts:
        seq0 = gz_to_seq(sg, sz)
        if 0 <= (seqd - seq0) % 60 <= 9:
            kong = [(sz + 10) % 12, (sz + 11) % 12]
            return "、".join(ZHI[k] for k in kong)
    return "无"


# ---------- 大运（以月支对应的"节"精确定位，避免 jqIndex 跨年错乱） ----------
def _dayun_shensha(yg, mz, tokens, rg, rz, sex, dayun_list):
    """大运神煞：以日干/日支/年干/月支/性别为参照，看大运地支落入哪些神煞位。"""
    gui_ren = {0: [1, 7], 2: [1, 7], 4: [1, 7], 1: [0, 8], 5: [0, 8],
               3: [11, 9], 6: [11, 9], 8: [3, 5], 9: [3, 5], 7: [2, 6]}
    wc_map = {0: 5, 1: 6, 2: 8, 3: 9, 4: 8, 5: 9, 6: 11, 7: 0, 8: 2, 9: 3}
    tao = {2: 3, 6: 3, 10: 3, 8: 9, 0: 9, 4: 9, 11: 0, 3: 0, 7: 0, 5: 6, 9: 6, 1: 6}
    yi = {2: 8, 6: 8, 10: 8, 8: 2, 0: 2, 4: 2, 11: 5, 3: 5, 7: 5, 5: 11, 9: 11, 1: 11}
    hua = {2: 10, 6: 10, 10: 10, 8: 4, 0: 4, 4: 4, 11: 7, 3: 7, 7: 7, 5: 1, 9: 1, 1: 1}
    yang_ren = {0: 3, 2: 6, 4: 6, 6: 9, 8: 0}
    jie = {2: 11, 6: 11, 10: 11, 8: 5, 0: 5, 4: 5, 11: 8, 3: 8, 7: 8, 5: 2, 9: 2, 1: 2}
    guoyin = {0: 10, 1: 11, 2: 1, 3: 2, 4: 1, 5: 2, 6: 4, 7: 5, 8: 7, 9: 8}
    ciguan = {0: 2, 1: 3, 2: 5, 3: 6, 4: 5, 5: 6, 6: 8, 7: 9, 8: 11, 9: 0}
    targets = {
        "天乙贵人": set(gui_ren.get(rg, [])),
        "文昌": {wc_map[rg]},
        "桃花": {tao[rz]},
        "驿马": {yi[rz]},
        "华盖": {hua[rz]},
        "劫煞": {jie[rz]},
        "天医": {(mz - 1) % 12},
        "国印贵人": {guoyin[yg]},
        "词馆": {ciguan[rg]},
        "天罗地网": ({10, 11} if sex == "male" else {4, 5}),
    }
    if rg in yang_ren:
        targets["羊刃"] = {yang_ren[rg]}
    out = []
    for d in dayun_list:
        zz = ZHI.index(d["ganzhi"][1])
        out.append([name for name, tset in targets.items() if zz in tset])
    return out


def get_dayun(yg, mg, mz, rg, rz, year, month, day, hour, minute, sex):
    yang_year = GAN_YIN[yg] == 0
    male = sex == "male"
    forward = (yang_year and male) or (not yang_year and not male)
    direction = "顺行" if forward else "逆行"
    birth_jd = datetime_to_jd(year, month, day, hour, minute)

    res = collect_jie(year)
    prev_name = MZ_JIE[mz]
    next_name = MZ_JIE[(mz + 1) % 12]

    prev_jds = [jd for (n, yr), jd in res.items() if n == prev_name and jd <= birth_jd]
    next_jds = [jd for (n, yr), jd in res.items() if n == next_name and jd > birth_jd]
    if forward:
        target_jd = min(next_jds) if next_jds else None
    else:
        target_jd = max(prev_jds) if prev_jds else None

    if target_jd is None:
        delta_days = 0.0
    else:
        delta_days = abs(target_jd - birth_jd)

    start_age = delta_days / 3.0
    yrs = int(start_age)
    months = int(round((start_age - yrs) * 12))

    month_seq = gz_to_seq(mg, mz)
    dayun_list = []
    for i in range(1, 9):
        k = (month_seq + i) % 60 if forward else (month_seq - i) % 60
        gg, zz = seq_to_gz(k)
        age_start = yrs + (i - 1) * 10
        dayun_list.append({
            "step": i, "ganzhi": f"{GAN[gg]}{ZHI[zz]}", "nayin": NAYIN[k],
            "age": f"{age_start}-{age_start + 9}岁",
        })
    ds = _dayun_shensha(yg, mz, None, rg, rz, sex, dayun_list)
    for i, d in enumerate(dayun_list):
        d["shensha"] = ds[i]
    return {
        "direction": direction,
        "start_age": f"{yrs}岁{months}个月（约 {round(start_age, 1)} 岁）",
        "start_age_value": round(start_age, 2),
        "list": dayun_list,
    }


def get_liunian(rg, start_year, n=12):
    out = []
    for y in range(start_year, start_year + n):
        # 年干支以该年实测立春为界（立春最早 2/3、最晚 2/5）。
        # 曾用 fromSolar(y, 1, 1) 取，结果落在立春之前，序列整体错位一年。
        gg, zz = year_gz_of(y)
        out.append({
            "year": y, "ganzhi": f"{GAN[gg]}{ZHI[zz]}",
            "shishen": SHEN_10[shishen(rg, gg)],
        })
    return out


# ---------- 渲染 ----------
def render_text(r):
    lines = []
    inp = r["input"]
    lines.append(f"【输入】公历 {inp['solar']}  性别 {inp['sex']}（晚子时规则：{inp['use_night_zi']}）")
    p, ps, ny = r["pillars"], r["pillar_shishen"], r["nayin"]
    lines.append("")
    lines.append("四柱      年柱      月柱      日柱      时柱")
    lines.append(f"干支      {p['year']}    {p['month']}    {p['day']}(日主)  {p['hour']}")
    lines.append(f"十神      {ps['year']}    {ps['month']}    {ps['day']}    {ps['hour']}")
    lines.append(f"纳音      {ny['year']}  {ny['month']}  {ny['day']}  {ny['hour']}")
    lines.append("")
    lines.append("【地支藏干】")
    for name in ("year", "month", "day", "hour"):
        hs = r["hidden_stems"][name]
        txt = "  ".join(f"{h['gan']}({h['level']},{h['shishen']})" for h in hs)
        lines.append(f"  {name}支：{txt}")
    lines.append("")
    lines.append(f"【日主】{r['day_master']}（{r['day_master_wx']}，{r['day_master_yin']}）")
    se = r["strength_eval"]
    lines.append(f"【旺衰】月令状态：{se['wang_xiang']}  得令:{se['de_ling']} 得地:{se['de_di']} 得势:{se['de_shi']}  评分:{se['score']}  → {se['level']}")
    lines.append(f"         用神(粗)：喜 {r['yongshen_rough']['xi']}；忌 {r['yongshen_rough']['ji']}")
    lines.append(f"         调候：{r['tiaohou']}")
    lines.append(f"【五行】" + "  ".join(f"{k}:{v}" for k, v in r["wx_count"].items()))
    lines.append("")
    lines.append(f"【格局派·取格】{r['pattern']['name']}（月令本气 {r['pattern']['month_root']} — {r['pattern']['root_shishen']}）")
    lines.append(f"         {r['pattern']['note']}")
    lines.append("")
    lines.append("【神煞】")
    for k, v in r["shensha"].items():
        lines.append(f"  {k}：{v}")
    lines.append(f"  空亡：{r['kongwang']}")
    lines.append("")
    dy = r["dayun"]
    lines.append(f"【大运】{dy['direction']}  起运 {dy['start_age']}")
    for d in dy["list"]:
        extra = ""
        if d.get("shensha"):
            extra = "  「" + "、".join(d["shensha"]) + "」"
        lines.append(f"  第{d['step']}运  {d['ganzhi']}({d['nayin']})  {d['age']}{extra}")

    if "liunian" in r:
        lines.append("")
        lines.append("【流年十神】")
        for ln in r["liunian"]:
            lines.append(f"  {ln['year']}  {ln['ganzhi']}  {ln['shishen']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="八字排盘")
    ap.add_argument("-y", "--year", type=int, required=True)
    ap.add_argument("-m", "--month", type=int, required=True)
    ap.add_argument("-d", "--day", type=int, required=True)
    ap.add_argument("-H", "--hour", type=int, required=True)
    ap.add_argument("-M", "--minute", type=int, default=0)
    ap.add_argument("-s", "--sex", choices=["male", "female"], required=True)
    ap.add_argument("--no-night-zi", action="store_true", help="不使用晚子时规则")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--liunian", type=int, default=0, help="显示从指定年份起的流年")
    args = ap.parse_args()

    r = compute(args.year, args.month, args.day, args.hour, args.minute,
                args.sex, use_night_zi=not args.no_night_zi)

    if args.liunian:
        r["liunian"] = get_liunian(GAN.index(r["day_master"]), args.liunian)

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(render_text(r))


if __name__ == "__main__":
    main()
