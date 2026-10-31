#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
真太阳时校正 + 时辰边界判定
============================
八字排盘前必须先做这一步：北京时间（东经 120° 标准时）不等于出生地的
真太阳时。跨经度、以及地球轨道偏心率造成的"均时差"，两者叠加最大可达
±30 分钟以上，足以把时辰推到相邻一格。

校正公式
--------
  真太阳时 = 北京时间 + (出生地经度 - 120°) × 4 分钟 + 均时差(EoT)

均时差用 NOAA 近似式（精度约 ±10 秒）。

用法
----
  python truesolar.py --city 北京 --date 1999-11-18 --time 20:00
  python truesolar.py --lon 116.23 --date 1999-11-18 --time 20:00
  python truesolar.py --city 乌鲁木齐 --date 1999-11-18 --time 20:00 --json

若不给出生城市也不给经度，脚本会报错提示，不要默认按北京时间算。
"""

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------- 城市经度表
# 经度取市政府/主城区坐标，精度对时辰判定（±0.1° ≈ ±24 秒）足够。
CITY_LON = {
    # 直辖市
    "北京": 116.41, "上海": 121.47, "天津": 117.20, "重庆": 106.55,
    # 华北 / 东北
    "石家庄": 114.51, "太原": 112.55, "呼和浩特": 111.75, "唐山": 118.18,
    "保定": 115.48, "邯郸": 114.49, "大同": 113.30, "包头": 109.84,
    "沈阳": 123.43, "大连": 121.62, "长春": 125.32, "哈尔滨": 126.53,
    "吉林": 126.55, "齐齐哈尔": 123.92, "鞍山": 122.99,
    # 华东
    "南京": 118.80, "苏州": 120.62, "无锡": 120.30, "徐州": 117.28,
    "杭州": 120.15, "宁波": 121.55, "温州": 120.70, "绍兴": 120.58,
    "合肥": 117.28, "福州": 119.30, "厦门": 118.09, "泉州": 118.59,
    "南昌": 115.89, "济南": 117.00, "青岛": 120.38, "烟台": 121.39,
    "潍坊": 119.16, "临沂": 118.35,
    # 华中
    "郑州": 113.62, "洛阳": 112.45, "武汉": 114.30, "宜昌": 111.29,
    "长沙": 112.94, "株洲": 113.13, "衡阳": 112.57,
    # 华南
    "广州": 113.26, "深圳": 114.06, "珠海": 113.55, "佛山": 113.12,
    "东莞": 113.75, "汕头": 116.68, "南宁": 108.37, "桂林": 110.29,
    "柳州": 109.41, "海口": 110.33, "三亚": 109.51,
    # 西南
    "成都": 104.07, "绵阳": 104.68, "宜宾": 104.63, "南充": 106.11,
    "贵阳": 106.63, "遵义": 106.93, "昆明": 102.83, "大理": 100.23,
    "丽江": 100.23, "拉萨": 91.14, "日喀则": 88.88,
    # 西北
    "西安": 108.95, "宝鸡": 107.14, "咸阳": 108.71, "兰州": 103.83,
    "天水": 105.72, "西宁": 101.78, "银川": 106.23, "乌鲁木齐": 87.62,
    "喀什": 75.99, "伊宁": 81.32, "格尔木": 94.90,
    # 港澳台
    "香港": 114.17, "澳门": 113.55, "台北": 121.52, "高雄": 120.31,
    # 常用市辖区（与主城区经度差可达 0.5° 以上，单独列出以免误判时辰）
    "昌平": 116.23, "通州": 116.66, "海淀": 116.30, "朝阳": 116.49,
    "大兴": 116.34, "顺义": 116.65, "房山": 116.14, "门头沟": 116.10,
    "浦东": 121.54, "闵行": 121.38, "宝山": 121.49, "嘉定": 121.27,
    "松江": 121.23, "青浦": 121.12, "奉贤": 121.47,
    "宝安": 113.88, "龙岗": 114.25, "龙华": 114.04, "南山": 113.93,
    "番禺": 113.38, "增城": 113.81, "花都": 113.22, "南沙": 113.54,
    "顺德": 113.29, "南海": 113.15, "三水": 112.90,
    "余杭": 120.30, "萧山": 120.26, "富阳": 119.96, "临安": 119.72,
    "江宁": 118.84, "浦口": 118.63, "六合": 118.85,
    "璧山": 106.23, "万州": 108.41, "涪陵": 107.39, "江津": 106.26,
    "合川": 106.28, "永川": 105.93, "长寿": 107.08,
    "长安": 108.94, "临潼": 109.21, "鄠邑": 108.60,
    "温江": 103.85, "双流": 103.92, "郫都": 103.90, "新都": 104.16,
    "新北": 121.47, "沙坪坝": 106.46, "渝北": 106.63, "九龙坡": 106.51,
    "巴南": 106.54, "北碚": 106.44, "渝中": 106.57,
}

# 常见旧称 / 别名 → 标准名（仅用于表中没有精确条目的情况）
CITY_ALIAS = {
    "昌平县": "昌平", "宛平": "北京", "番禺市": "番禺",
    "香港岛": "香港", "澳门半岛": "澳门",
}

# 十二时辰：子时跨日（23:00–01:00），起始序号 0
SHICHEN = [
    ("子", 23, 1), ("丑", 1, 3), ("寅", 3, 5), ("卯", 5, 7),
    ("辰", 7, 9), ("巳", 9, 11), ("午", 11, 13), ("未", 13, 15),
    ("申", 15, 17), ("酉", 17, 19), ("戌", 19, 21), ("亥", 21, 23),
]


def eot_minutes(d: date, hour: float = 12.0) -> float:
    """均时差（Equation of Time），单位分钟。NOAA 近似式，精度约 ±10s。"""
    n = d.timetuple().tm_yday
    frac = (hour - 12.0) / 24.0
    gamma = 2.0 * math.pi / 365.0 * (n - 1 + frac)
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )


def resolve_lon(city: str):
    if not city:
        return None, None
    name = city.strip().replace("市", "").replace("区", "").replace("县", "")
    if name in CITY_ALIAS:
        std = CITY_ALIAS[name]
        return CITY_LON[std], f"{city}→{std}"
    if name in CITY_LON:
        return CITY_LON[name], name
    for k in CITY_LON:
        if k in name or name in k:
            return CITY_LON[k], f"{city}→{k}"
    return None, None


def shichen_of(hh: int, mm: int) -> str:
    """返回时辰名与是否处于时头/时尾（距边界 30 分钟内）。"""
    t = hh * 60 + mm
    for name, a, b in SHICHEN:
        lo, hi = a * 60, b * 60
        if a == 23:  # 子时跨日
            if t >= lo or t < hi:
                name_out = "子"
                dist_lo = (t - lo) if t >= lo else (t + 1440 - lo)
                dist_hi = (hi - t) if t < hi else (hi + 1440 - t)
                return f"{name_out}时", min(dist_lo, dist_hi), t
        elif lo <= t < hi:
            return f"{name}时", min(t - lo, hi - t), t
    return "子时", 0, t


def _risk_label(margin: float) -> str:
    """margin = 真太阳时距最近时辰边界的分钟数。时辰宽两小时，
    正中即 margin=60，是最安全的；越接近 0 越危险。"""
    if margin < 15:
        return "极高（距边界不足15分钟，几乎无法判定，须核对出生钟点精确到分钟）"
    if margin < 30:
        return "高（距边界不足30分钟，经度或钟点误差即可换格，须并列两版结论）"
    if margin < 45:
        return "中（距边界30-45分钟，仍建议复核出生钟点）"
    return "低（接近时辰正中，判定稳定）"


def get_prev(name: str) -> str:
    names = [x[0] for x in SHICHEN]
    i = names.index(name.replace("时", ""))
    return names[i - 1] + "时"


def get_next(name: str) -> str:
    names = [x[0] for x in SHICHEN]
    i = names.index(name.replace("时", ""))
    return names[(i + 1) % 12] + "时"


def main():
    ap = argparse.ArgumentParser(description="真太阳时校正与时辰判定")
    ap.add_argument("--city", help="出生城市，如 北京 / 昌平 / 乌鲁木齐")
    ap.add_argument("--lon", type=float, help="出生地经度（东经为正），优先于 --city")
    ap.add_argument("--date", required=True, help="公历出生日期 YYYY-MM-DD")
    ap.add_argument("--time", required=True, help="北京时间 HH:MM")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.lon is None:
        lon, note = resolve_lon(args.city)
        if lon is None:
            print(f"错误：城市「{args.city}」不在内置经度表中，请改用 --lon 直接给出经度。", file=sys.stderr)
            print("（可在城市经纬度网站查出生地经度；东经为正，如北京昌平 116.23）", file=sys.stderr)
            sys.exit(1)
    else:
        lon, note = args.lon, "手动指定"

    d = datetime.strptime(args.date, "%Y-%m-%d").date()
    bh, bm = (int(x) for x in args.time.split(":"))

    # 经度差时：每偏离 120°E 一度，差 4 分钟；偏西为正（真太阳时更早）
    lon_delta_min = (lon - 120.0) * 4.0
    eot = eot_minutes(d, bh)

    base = datetime(d.year, d.month, d.day, bh, bm)
    true_dt = base + timedelta(minutes=lon_delta_min + eot)

    sc, margin, _ = shichen_of(true_dt.hour, true_dt.minute)
    # 时辰判定同时检查边界：经度/均时差可能把时间推过 0 点，日期也会变
    day_shift = (true_dt.date() - d).days

    result = {
        "出生地": args.city or f"经度 {lon}°E",
        "经度": round(lon, 3),
        "公历日期": str(d),
        "北京时间": f"{bh:02d}:{bm:02d}",
        "经度差时_分钟": round(lon_delta_min, 2),
        "均时差_分钟": round(eot, 2),
        "合计修正_分钟": round(lon_delta_min + eot, 2),
        "真太阳时": true_dt.strftime("%H:%M:%S"),
        "真太阳时日期": str(true_dt.date()),
        "跨日偏移": day_shift,
        "时辰": sc,
        "距时辰边界_分钟": round(margin, 1),
        "边界风险": _risk_label(margin),
        "相邻时辰": [get_prev(sc), sc, get_next(sc)],
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print("=" * 46)
    print(f"出生地      {result['出生地']}" + (f"  经度 {lon}°E" if args.city else ""))
    print(f"北京时间    {args.date} {bh:02d}:{bm:02d}")
    print("-" * 46)
    print(f"经度差时    {lon_delta_min:+.2f} 分钟   (偏西为负→真太阳时更早)")
    print(f"均时差      {eot:+.2f} 分钟")
    print(f"合计修正    {lon_delta_min + eot:+.2f} 分钟")
    print("-" * 46)
    print(f"真太阳时    {true_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    if day_shift:
        print(f"⚠️  真太阳时已跨日（{'后一天' if day_shift > 0 else '前一天'}），日柱需按 {true_dt.date()} 排")
    print(f"时辰        {sc}")
    print(f"边界余量    距最近边界 {margin:.1f} 分钟（时辰正中为 60）→ 风险 {result['边界风险']}")
    if margin < 45:
        print(f"⚠️  若经度/钟点有小误差，可能落入 {get_prev(sc)} 或 {get_next(sc)}，请复核")
        print(f"    候选：{get_prev(sc)} / {sc} / {get_next(sc)}")
    print("=" * 46)
    print(f"排盘请用：-y {true_dt.year} -m {true_dt.month} -d {true_dt.day} "
          f"-H {true_dt.hour} -M {true_dt.minute}")


if __name__ == "__main__":
    main()
