# -*- coding: utf-8 -*-
"""
========================================================
  股市助手  stock_app.py  v1.0
  一个有窗口的程序：左边自选股，中间 K 线，右边规则体检
========================================================

不装任何第三方库（只用 Python 自带的 tkinter 画图），双击 `股市助手.bat`
或打包好的 `股市助手.exe` 就能用，不弹黑窗口。

它做什么：
  1. 左边点一只股票 → 中间画出它的 K 线（红涨绿跌 + MA5/MA20/MA60 + 成交量）
  2. 鼠标在图上移动 → 十字线跟着走，显示那一天的开收高低、涨跌幅、成交量
  3. 右边告诉你：今天规则说了什么（带数字的原因），以及过去两年这条规则准不准
  4. 底部按钮换时间区间（3 个月 / 半年 / 1 年 / 全部），滚轮也能缩放

它不做什么：不预测、不荐股、不连账户、不下单。
"""

import bisect
import csv
import datetime
import json
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk

# ---------------- 0. 路径：打包成 exe 后也能找到同目录的 csv ----------------

def app_dir():
    """程序所在目录。打包成 exe 后 sys.frozen 为真，用 exe 自己的目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = app_dir()
WATCH_FILE = os.path.join(BASE_DIR, "自选股.csv")
LOG_FILE = os.path.join(BASE_DIR, "调试日志.txt")


def log(msg):
    """写一行小日志，出问题时能回头查（窗口版没有黑窗口看报错）。"""
    try:
        import datetime
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("{} {}\n".format(datetime.datetime.now().strftime("%H:%M:%S"), msg))
    except Exception:                            # noqa: BLE001
        pass


WATCH_HEADER = ["代码", "名称"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# 周期：(klt, 按钮文字, 新浪 scale)。101 表示日线，其余是分钟线
PERIODS = ((101, "日线", None), (60, "60分", 60), (30, "30分", 30),
           (15, "15分", 15), (5, "5分", 5), (1, "1分", 1))
SINA_MIN_URL = ("https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_=/CN_MarketDataService"
                ".getKLineData?symbol={sym}&scale={scale}&ma=no&datalen={n}")

# 分钟线能回溯多久（1023 根上限，按 240 分钟/交易日估）
PERIOD_SPAN = {1: "约 4~5 个交易日", 5: "约 1 个月", 15: "约 3 个月",
               30: "约 6 个月", 60: "约 1 年", 101: "很多年（接口够长）"}

UP = "#e2342f"      # 涨：红
DOWN = "#12a35c"    # 跌：绿
MA5_C = "#e08a1e"
MA20_C = "#2f7ff0"
MA60_C = "#8b5cf6"
GRID = "#eceef1"
TEXT = "#1f2328"
MUTED = "#6b7280"

FONT = ("Microsoft YaHei UI", 9)
FONT_B = ("Microsoft YaHei UI", 9, "bold")
FONT_T = ("Microsoft YaHei UI", 13, "bold")
FONT_S = ("Microsoft YaHei UI", 8)


# ---------------- 1. 自选股 ----------------

def load_watch():
    if not os.path.exists(WATCH_FILE):
        rows = [["600519", "贵州茅台"], ["600900", "长江电力"],
                ["000001", "平安银行"], ["300750", "宁德时代"]]
        save_watch(rows)
        return rows
    rows = []
    with open(WATCH_FILE, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            code = (row.get("代码") or "").strip()
            if code:
                rows.append([code, (row.get("名称") or "").strip()])
    return rows


def save_watch(rows):
    with open(WATCH_FILE, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(WATCH_HEADER)
        w.writerows(rows)


# ---------------- 2. 行情 ----------------

def market_of(code):
    return "1" if code.startswith("6") else "0"


def fetch_em(code, count=520, secid=None):
    """东方财富公开日 K 接口，返回 (名称, bars)。secid 形如 "1.600519"，不给就按代码猜。"""
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid="
           + (secid or (market_of(code) + "." + code))
           + "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57"
           + "&klt=101&fqt=1&end=20500101&lmt=" + str(count))
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Referer": "https://quote.eastmoney.com/"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    block = json.loads(raw).get("data")
    if not block or not block.get("klines"):
        raise RuntimeError("东方财富没返回数据")
    bars = []
    for line in block["klines"]:
        p = line.split(",")
        bars.append({
            "date": p[0], "open": float(p[1]), "close": float(p[2]),
            "high": float(p[3]), "low": float(p[4]), "vol": float(p[5]),
        })
    return block.get("name", ""), bars


def fetch_tx(code, count=520, secid=None):
    """腾讯行情接口（备胎）。东财抽风时用它，返回同样的 (名称, bars)。"""
    if code.startswith("6"):
        sym = "sh" + code
    elif code.startswith(("4", "8", "9")):
        sym = "bj" + code
    else:
        sym = "sz" + code
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param="
           + sym + ",day,,," + str(count) + ",qfq")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    node = (json.loads(raw).get("data") or {}).get(sym) or {}
    rows = node.get("qfqday") or node.get("day") or []
    if not rows:
        raise RuntimeError("腾讯也没返回数据")
    name = ""
    qt = (node.get("qt") or {}).get(sym) or []
    if len(qt) > 1:
        name = qt[1]
    bars = []
    for p in rows[-count:]:
        bars.append({
            "date": p[0], "open": float(p[1]), "close": float(p[2]),
            "high": float(p[3]), "low": float(p[4]), "vol": float(p[5]),
        })
    return name, bars


def fetch_kline(code, count=520, secid=None):
    """先问东方财富，不通就换腾讯——两个源都挂了才报错。"""
    problems = []
    for fn in (fetch_em, fetch_tx):
        try:
            name, bars = fn(code, count=count, secid=secid)
            if bars:
                return name, bars
            problems.append(fn.__name__ + "：空数据")
        except Exception as e:                      # noqa: BLE001 - 换下一个源再试
            problems.append(fn.__name__ + "：" + str(e)[:40])
    raise RuntimeError("两个数据源都没拿到数据（" + "；".join(problems) + "）")


# ---- 实时报价（盘中每隔几秒刷一次；收盘后返回的就是收盘价）----

QUOTE_URL = ("https://push2.eastmoney.com/api/qt/stock/get?secid={}"
             "&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f86,f169,f170")


def quote_em(code, secid=None):
    """东方财富实时报价。价格单位是分，要除 100。"""
    url = QUOTE_URL.format(secid or (market_of(code) + "." + code))
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Referer": "https://quote.eastmoney.com/"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    d = json.loads(raw).get("data")
    if not d or d.get("f43") in (None, "-"):
        raise RuntimeError("东方财富没返回报价")
    ts = d.get("f86") or 0
    stamp = datetime.datetime.fromtimestamp(ts) if ts else datetime.datetime.now()
    return {
        "code": d.get("f57") or code,
        "name": d.get("f58") or "",
        "price": d["f43"] / 100.0,
        "prev": (d.get("f60") or 0) / 100.0,
        "open": (d.get("f46") or 0) / 100.0,
        "high": (d.get("f44") or 0) / 100.0,
        "low": (d.get("f45") or 0) / 100.0,
        "vol": float(d.get("f47") or 0),
        "time": stamp.strftime("%H:%M:%S"),
        "date": stamp.strftime("%Y-%m-%d"),
    }


def quote_tx(code):
    """腾讯实时报价（备胎）。字段用 ~ 分隔，价格单位是元。"""
    if code.startswith("6"):
        sym = "sh" + code
    elif code.startswith(("4", "8", "9")):
        sym = "bj" + code
    else:
        sym = "sz" + code
    req = urllib.request.Request("https://qt.gtimg.cn/q=" + sym,
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read().decode("gbk", "ignore")
    body = raw.split('="', 1)[-1].rstrip('";\n ')
    f = body.split("~")
    if len(f) < 35:
        raise RuntimeError("腾讯没返回报价")
    t = f[30]                                     # 20261030161455
    stamp = datetime.datetime.strptime(t[:14], "%Y%m%d%H%M%S")
    return {
        "code": f[2], "name": f[1], "price": float(f[3]), "prev": float(f[4]),
        "open": float(f[5]), "high": float(f[33]), "low": float(f[34]),
        "vol": float(f[6] or 0), "time": stamp.strftime("%H:%M:%S"),
        "date": stamp.strftime("%Y-%m-%d"),
    }


def fetch_quote(code, secid=None):
    """先东财，不行再腾讯。"""
    problems = []
    for fn, kw in ((quote_em, {"secid": secid}), (quote_tx, {})):
        try:
            return fn(code, **kw)
        except Exception as e:                  # noqa: BLE001 - 换下一个源再试
            problems.append(fn.__name__ + "：" + str(e)[:40])
    raise RuntimeError("报价没拿到（" + "；".join(problems) + "）")


def is_trading_time(now=None):
    """A 股交易时段（含集合竞价前后一点余量）。周末一律 False。"""
    now = now or datetime.datetime.now()
    if now.weekday() >= 5:
        return False
    hm = now.hour * 100 + now.minute
    return (915 <= hm <= 1135) or (1255 <= hm <= 1505)


SEARCH_URL = ("https://searchapi.eastmoney.com/api/suggest/get?input={}&type=14"
              "&token=D43BF722C8E33BDC906FB84D85E326E8&count=20")


# ---- 公司资料（F10 概况）----

ORG_URL = ("https://datacenter.eastmoney.com/securities/api/data/v1/get?"
           "reportName=RPT_F10_BASIC_ORGINFO&columns=ALL&filter=(SECURITY_CODE=%22{}%22)"
           "&client=PC&source=WEB")
ORG_F10_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax?code={}"


def _org_code(code):
    """东财 F10 要的是 SH600519 / SZ300750 这种写法。"""
    if code.startswith("6"):
        return "SH" + code
    if code.startswith(("4", "8", "9")):
        return "BJ" + code
    return "SZ" + code


def fetch_org(code):
    """公司简介：先用东财数据中心，不行再试 F10 页面接口。"""
    problems = []
    try:
        req = urllib.request.Request(ORG_URL.format(code),
                                     headers={"User-Agent": UA,
                                              "Referer": "https://quote.eastmoney.com/"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", "ignore")
        rows = ((json.loads(raw).get("result") or {}).get("data") or [])
        if not rows:
            raise RuntimeError("数据中心没这条记录")
        d = rows[0]
        return {
            "name": d.get("SECURITY_NAME_ABBR") or "",
            "full_name": d.get("ORG_NAME") or "",
            "former": d.get("FORMERNAME") or "",
            "list_date": (d.get("LISTING_DATE") or "")[:10],
            "industry": d.get("EM2016") or "",
            "industry_csrc": d.get("INDUSTRYCSRC1") or "",
            "market": d.get("TRADE_MARKET") or "",
            "main_business": d.get("MAIN_BUSINESS") or "",
            "scope": d.get("BUSINESS_SCOPE") or "",
            "profile": (d.get("ORG_PROFILE") or "").strip(),
            "employees": d.get("EMP_NUM"),
            "capital": d.get("REG_CAPITAL"),
            "address": d.get("ADDRESS") or "",
            "web": d.get("ORG_WEB") or "",
            "legal": d.get("LEGAL_PERSON") or "",
            "chairman": d.get("CHAIRMAN") or "",
            "tel": d.get("ORG_TEL") or "",
            "src": "东财数据中心",
        }
    except Exception as e:                          # noqa: BLE001 - 换下一个源
        problems.append("数据中心：" + str(e)[:40])

    try:
        req = urllib.request.Request(ORG_F10_URL.format(_org_code(code)),
                                     headers={"User-Agent": UA,
                                              "Referer": "https://emweb.securities.eastmoney.com/"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", "ignore")
        jb = (json.loads(raw).get("jbzl") or [{}])[0]
        if not jb:
            raise RuntimeError("F10 没返回概况")
        return {
            "name": jb.get("SECURITY_NAME_ABBR") or "",
            "full_name": jb.get("ORG_NAME") or "",
            "former": jb.get("FORMERNAME") or "",
            "list_date": (jb.get("LISTING_DATE") or "")[:10],
            "industry": jb.get("EM2016") or "",
            "industry_csrc": jb.get("INDUSTRYCSRC1") or "",
            "market": jb.get("TRADE_MARKET") or "",
            "main_business": jb.get("MAIN_BUSINESS") or "",
            "scope": jb.get("BUSINESS_SCOPE") or "",
            "profile": (jb.get("ORG_PROFILE") or "").strip(),
            "employees": jb.get("EMP_NUM"),
            "capital": jb.get("REG_CAPITAL"),
            "address": jb.get("ADDRESS") or "",
            "web": jb.get("ORG_WEB") or "",
            "legal": jb.get("LEGAL_PERSON") or "",
            "chairman": jb.get("CHAIRMAN") or "",
            "tel": jb.get("ORG_TEL") or "",
            "src": "东财 F10",
        }
    except Exception as e:                          # noqa: BLE001
        problems.append("F10：" + str(e)[:40])
    raise RuntimeError("公司资料没拿到（" + "；".join(problems) + "）")
def search_tx(keyword, limit=10):
    """腾讯的搜索备胎：返回同样的结构，只留 A 股。"""
    url = ("https://smartbox.gtimg.cn/s3/?q=" + urllib.parse.quote(keyword)
           + "&t=all&c=50")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    try:
        raw = raw.encode("utf-8").decode("unicode_escape")
    except Exception:                               # noqa: BLE001 - 解不开就用原样
        pass
    out = []
    mark = raw.find('v_hint="')
    if mark < 0:
        return out
    body = raw[mark + 8:].split('"')[0]
    for part in body.split("^"):
        f = part.split("~")
        if len(f) < 5 or f[4] != "GP-A":            # GP-A 才是 A 股
            continue
        code = f[1]
        out.append({
            "code": code,
            "name": f[2],
            "market": "沪A" if f[0] == "sh" else "深A",
            "secid": ("1." if f[0] == "sh" else "0.") + code,
            "pinyin": f[3].upper(),
        })
        if len(out) >= limit:
            break
    return out


def search_stocks(keyword, limit=10):
    """按名称 / 拼音 / 代码搜 A 股，返回列表：[{code,name,market,secid,pinyin}]。"""
    kw = (keyword or "").strip()
    if not kw:
        return []
    try:
        return search_em(kw, limit)
    except Exception:                               # noqa: BLE001 - 东财抽风就用腾讯
        return search_tx(kw, limit)


def search_em(keyword, limit=10):
    """东方财富的搜索接口。"""
    kw = (keyword or "").strip()
    url = SEARCH_URL.format(urllib.parse.quote(kw))
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Referer": "https://quote.eastmoney.com/"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    block = json.loads(raw).get("QuotationCodeTable") or {}
    out = []
    for it in block.get("Data") or []:
        if it.get("Classify") != "AStock":      # 只要 A 股，基金/港美股/板块都跳过
            continue
        code = it.get("Code") or ""
        if not code:
            continue
        out.append({
            "code": code,
            "name": it.get("Name") or "",
            "market": it.get("SecurityTypeName") or ("沪A" if it.get("MktNum") == "1" else "深A"),
            "secid": it.get("QuoteID") or (market_of(code) + "." + code),
            "pinyin": it.get("PinYin") or "",
        })
        if len(out) >= limit:
            break
    return out


# ---------------- 3. 均线 / 规则 ----------------

def fetch_min_bars(code, scale=5, n=1023):
    """分钟线（新浪）：scale=1/5/15/30/60，单次最多约 1023 根。"""
    sym = _org_code(code).lower()
    url = SINA_MIN_URL.format(sym=sym, scale=scale, n=n)
    raw, err = "", None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Referer": "https://finance.sina.com.cn/",
                "Accept": "*/*"})
            raw = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
            if '"day"' in raw:
                break
            err = raw[:80].replace("\n", " ")
        except Exception as e:              # noqa: BLE001
            err = "{}".format(e)
        time.sleep(1.2)
    if '"day"' not in raw:
        raise RuntimeError("新浪分钟线没返回数据（{}）".format(err))
    a, b = raw.find("["), raw.rfind("]")
    arr = json.loads(raw[a:b + 1])
    bars = []
    for it in arr:
        d = str(it["day"])
        bars.append({"date": d,
                     "label": d[5:16] if len(d) >= 16 else d,
                     "open": float(it["open"]), "high": float(it["high"]),
                     "low": float(it["low"]), "close": float(it["close"]),
                     "vol": float(it.get("volume") or 0) / 100.0})
    if not bars:
        raise RuntimeError("分钟线是空的")
    return bars


def moving_average(values, n):
    out, total = [], 0.0
    for i, v in enumerate(values):
        total += v
        if i >= n:
            total -= values[i - n]
        out.append(total / n if i + 1 >= n else None)
    return out


def analyze(bars):
    """算均线、买卖点、以及这条规则的历史成绩。返回一个字典。"""
    closes = [b["close"] for b in bars]
    ma5 = moving_average(closes, 5)
    ma20 = moving_average(closes, 20)
    ma60 = moving_average(closes, 60)

    # 规则：持仓为空时，收盘上穿 MA20 且 MA20>MA60 → 买；持有时，收盘下穿 MA20 → 卖。
    # 买卖点是「同一笔交易的两头」，所以图上的三角形和下面的统计永远对得上。
    buys, sells, trades = [], [], []
    entry = None
    for i in range(1, len(bars)):
        if ma20[i] is None or ma20[i - 1] is None or ma60[i] is None:
            continue
        c0, c1 = bars[i - 1]["close"], bars[i]["close"]
        cross_up = c0 < ma20[i - 1] and c1 >= ma20[i]
        cross_down = c0 > ma20[i - 1] and c1 <= ma20[i]
        if entry is None and cross_up and ma20[i] > ma60[i]:
            entry = c1
            buys.append({"i": i, "price": bars[i]["low"],
                         "text": "{} 收盘上穿 MA20（{:.2f}→{:.2f}），MA20>MA60，买入".format(
                             bars[i]["date"], ma20[i - 1], ma20[i])})
        elif entry is not None and cross_down:
            trades.append((entry, c1))
            entry = None
            sells.append({"i": i, "price": bars[i]["high"],
                          "text": "{} 收盘下穿 MA20（{:.2f}→{:.2f}），卖出，这笔 {}{:.1f}%".format(
                              bars[i]["date"], ma20[i - 1], ma20[i],
                              "+" if c1 >= trades[-1][0] else "",
                              (c1 / trades[-1][0] - 1) * 100)})
    if entry is not None:                 # 还拿着没卖：算到最新价为止，图上不画卖点
        trades.append((entry, bars[-1]["close"]))

    wins = [t for t in trades if t[1] > t[0]]
    loses = [t for t in trades if t[1] <= t[0]]
    win_sum = sum((t[1] - t[0]) / t[0] for t in wins)
    lose_sum = -sum((t[1] - t[0]) / t[0] for t in loses)
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0
    ratio = (win_sum / lose_sum) if lose_sum > 1e-9 else None

    # 规则收益：把每笔（按全仓、不考虑手续费）连乘起来
    equity = 1.0
    curve = [1.0]
    for a, b in trades:
        equity *= b / a
        curve.append(equity)
    rule_ret = (equity - 1) * 100
    hold_ret = (bars[-1]["close"] / bars[0]["close"] - 1) * 100
    peak, mdd = 0.0, 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = max(mdd, (peak - v) / peak * 100)

    return {"ma5": ma5, "ma20": ma20, "ma60": ma60,
            "buys": buys, "sells": sells,
            "n": len(trades), "win_rate": win_rate,
            "ratio": ratio, "rule_ret": rule_ret,
            "hold_ret": hold_ret, "mdd": mdd}


def today_notes(bars, a):
    """今天（最后一根）触发了什么，用大白话 + 数字写出来。"""
    i = len(bars) - 1
    b, prev = bars[i], bars[i - 1]
    c, c0 = b["close"], prev["close"]
    m20, m20p = a["ma20"][i], a["ma20"][i - 1]
    m60 = a["ma60"][i]
    chg = (c - c0) / c0 * 100
    notes = []
    notes.append(("{} 收盘 {:.2f}".format(b["date"], c),
                  "涨跌 {}{:.2f}%".format("+" if chg >= 0 else "", chg),
                  UP if chg >= 0 else DOWN))
    if m20 is not None and m60 is not None:
        trend = "多头排列（MA20 在 MA60 上方）" if m20 > m60 else "空头排列（MA20 在 MA60 下方）"
        notes.append(("趋势", trend, TEXT))
        dev = (c - m20) / m20 * 100
        notes.append(("离 MA20", "{:+.2f}%　MA20={:.2f}".format(dev, m20), TEXT))
        if dev > 8:
            notes.append(("追高警告", "收盘比 MA20 高 {:.1f}%，偏离过大".format(dev), UP))
        if m20p is not None and c0 < m20p and c >= m20 and m20 > m60:
            notes.append(("买入提示", "上穿 MA20 且 MA20>MA60", UP))
        elif m20p is not None and c0 > m20p and c <= m20:
            notes.append(("卖出提示", "下穿 MA20", DOWN))
        else:
            notes.append(("规则提示", "今天没有触发任何规则", MUTED))
        if c < m60:
            notes.append(("跌破 MA60", "收盘 {:.2f} 在 MA60（{:.2f}）下方".format(c, m60), DOWN))
    return notes


# ---------------- 3.4 「今天怎么办」：机械打分，不是预测 ----------------

def decide(bars, a, holding=False):
    """把 6 条机械规则各打 ±1/±2 分，加起来给一个结论。

    这不是预测、也不是建议：规则写死、每条都带数字，你可以自己复核，
    也可以拿历史数据检验它有多准（右侧「这条规则过去有多准」就是它的成绩单）。
    """
    ma20, ma60 = a["ma20"], a["ma60"]
    i = len(bars) - 1
    last = bars[i]
    c = last["close"]
    items = []

    def add(text, delta):
        items.append({"text": text, "delta": delta})

    # 1 中期趋势
    if ma20[i] is not None and ma60[i] is not None:
        if ma20[i] > ma60[i]:
            add("MA20 {:.2f} 在 MA60 {:.2f} 上方 → 中期趋势向上".format(ma20[i], ma60[i]), 2)
        else:
            add("MA20 {:.2f} 在 MA60 {:.2f} 下方 → 中期趋势向下".format(ma20[i], ma60[i]), -2)

    dev = (c / ma20[i] - 1) * 100 if ma20[i] else 0.0
    # 2 站没站上 20 日线
    if dev >= 0:
        add("收盘 {:.2f}，比 MA20 高 {:.2f}%（站在线上面）".format(c, dev), 1)
    else:
        add("收盘 {:.2f}，比 MA20 低 {:.2f}%（在线下面）".format(c, -dev), -1)

    # 3 追高警报
    if dev > 8:
        add("但已比 MA20 高 {:.1f}%，属于追高区（历史上这种位置回撤概率大）".format(dev), -1)

    # 4 MA20 自己往上还是往下（跟 5 天前比）
    if i >= 5 and ma20[i - 5]:
        slope = (ma20[i] / ma20[i - 5] - 1) * 100
        if slope > 0.3:
            add("MA20 这 5 天上翘 {:+.1f}% → 线自己在往上走".format(slope), 1)
        elif slope < -0.3:
            add("MA20 这 5 天下拐 {:+.1f}% → 线自己在往下走".format(slope), -1)

    # 5 近 20 日新高 / 新低
    win = bars[max(0, i - 19):i + 1]
    hi = max(b["high"] for b in win)
    lo = min(b["low"] for b in win)
    if c >= hi * 0.999:
        add("收盘是近 20 个交易日的最高价（{:.2f}）".format(hi), 1)
    elif c <= lo * 1.001:
        add("收盘是近 20 个交易日的最低价（{:.2f}）".format(lo), -1)

    # 6 量能配不配合
    vols = [b["vol"] for b in bars]
    if len(vols) >= 20:
        v5 = sum(vols[-5:]) / 5
        v20 = sum(vols[-20:]) / 20
        if v20:
            ratio = v5 / v20
            if ratio > 1.3 and dev >= 0:
                add("近 5 天成交量是 20 天均量的 {:.2f} 倍，放量且价格在线上".format(ratio), 1)
            elif ratio > 1.3 and dev < 0:
                add("近 5 天成交量是 20 天均量的 {:.2f} 倍，放量下跌".format(ratio), -1)

    score = sum(it["delta"] for it in items)
    top = sum(abs(it["delta"]) for it in items)

    if holding:
        if score >= 3:
            verdict = "规则说：继续持有"
        elif score >= 1:
            verdict = "规则说：持有，但别加仓"
        elif score >= -1:
            verdict = "规则说：减掉一部分"
        else:
            verdict = "规则说：考虑卖出"
        tone = UP if score >= 1 else (MUTED if score >= -1 else DOWN)
    else:
        if score >= 3:
            verdict = "规则说可以买（分两次进）"
        elif score >= 1:
            verdict = "规则说：先别买，等它站稳 MA20"
        elif score >= -1:
            verdict = "规则说：先不买"
        else:
            verdict = "规则说：别买（趋势向下）"
        tone = UP if score >= 3 else (MUTED if score >= -1 else DOWN)

    return {"verdict": verdict, "score": score, "top": top, "items": items, "tone": tone,
            "holding": holding}


# ---------------- 3.5 新闻：公告 + 研报 + 事件研究 ----------------

ANN_URL = ("https://np-anotice-stock.eastmoney.com/api/security/ann"
           "?sr=-1&page_size={size}&page_index={page}&ann_type=A&client_source=web"
           "&stock_list={code}")

ANN_PAGE = "https://data.eastmoney.com/notices/detail/{code}/{art}.html"

REPORT_URL = ("https://reportapi.eastmoney.com/report/list?cb=cb&industryCode=*&pageSize={size}"
              "&industry=*&rating=&ratingChange=&beginTime={beg}&endTime={end}&pageNo=1"
              "&fields=&qType=0&orgCode=&code={code}&rcode=&p=1&pageNum=1")

REPORT_PAGE = "https://data.eastmoney.com/report/zw_stock.jshtml?infocode={code}"

# 关键词表：只是「数词」，不是我的看法。命中多只说明标题像利空/利多，仅此而已。
GOOD_WORDS = ("增长", "增持", "回购", "中标", "签约", "提价", "分红", "预增", "扭亏", "新高",
              "获批", "合作", "超预期", "盈利", "上调", "订单", "扩产", "涨价", "投产", "推荐")
BAD_WORDS = ("下降", "减持", "亏损", "预亏", "处罚", "违规", "诉讼", "减值", "解禁", "下滑",
             "质押", "问询", "警示", "立案", "终止", "失败", "退市", "下调", "商誉", "离职",
             "冻结", "停产", "风险提示", "监管函", "关注函")

# 公告种类：这个一定数得出来（标题里写明是什么事），所以比「偏多/偏空」可靠。
EVENT_WORDS = (
    ("业绩", ("年度报告", "半年度报告", "季度报告", "业绩预告", "业绩快报", "经营数据", "业绩说明会")),
    ("分红", ("分红", "派息", "利润分配", "股息")),
    ("增减持", ("增持", "减持", "回购", "股东", "股权激励")),
    ("并购重组", ("收购", "并购", "重组", "定增", "增发", "配股", "资产", "出售", "转让")),
    ("融资", ("可转债", "债券", "融资", "借款", "担保", "质押")),
    ("风险", ("处罚", "立案", "诉讼", "违规", "警示", "问询", "关注函", "风险提示", "退市", "冻结")),
)


def event_type(title):
    """按标题里的事件词把公告归个类，归不上就是「其他」。"""
    for name, words in EVENT_WORDS:
        for w in words:
            if w in title:
                return name
    return "其他"


def classify(title):
    """返回 (标签, 命中的词)。纯关键词计数，不是判断涨跌。"""
    good = [w for w in GOOD_WORDS if w in title]
    bad = [w for w in BAD_WORDS if w in title]
    if len(good) > len(bad):
        return "偏多", good
    if len(bad) > len(good):
        return "偏空", bad
    return "中性", []


def _get_text(url, referer=None, timeout=15):
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def fetch_anns(code, pages=1, size=50):
    """东方财富公告列表，按日期从新到旧：[{date,title,tag,words,url}]。"""
    out = []
    for page in range(1, pages + 1):
        raw = _get_text(ANN_URL.format(size=size, page=page, code=code),
                        referer="https://data.eastmoney.com/")
        data = (json.loads(raw).get("data") or {}).get("list") or []
        for it in data:
            title = (it.get("title") or "").strip()
            art = it.get("art_code") or ""
            tag, words = classify(title)
            out.append({
                "date": (it.get("notice_date") or "")[:10],
                "title": title, "tag": tag, "words": words, "etype": event_type(title),
                "url": ANN_PAGE.format(code=code, art=art) if art else "",
            })
        if not data:
            break
    return out


def fetch_reports(code, count=8):
    """东方财富研报（近一年）：机构评级也在标题里，那是机构观点，不是事实。"""
    today = datetime.date.today()
    beg = (today - datetime.timedelta(days=365)).isoformat()
    url = REPORT_URL.format(size=count, beg=beg, end=today.isoformat(), code=code)
    raw = _get_text(url, referer="https://data.eastmoney.com/")
    body = raw[raw.index("(") + 1: raw.rindex(")")] if "(" in raw else raw
    rows = (json.loads(body).get("data") or [])[:count]
    out = []
    for it in rows:
        title = (it.get("title") or "").strip()
        org = (it.get("orgSName") or "").strip()
        rating = (it.get("emRatingName") or "").strip()
        tag, words = classify(title + rating)
        info = it.get("infoCode") or ""
        out.append({
            "date": (it.get("publishDate") or "")[:10],
            "title": (org + "：" if org else "") + title,
            "tag": tag, "words": words, "rating": rating,
            "url": REPORT_PAGE.format(code=info) if info else "",
        })
    return out


def impact_stats(bars, dates, horizons=(1, 3, 5)):
    """这些日期之后 1/3/5 个交易日涨了多少，再跟「全样本随便一天」比。"""
    if not bars or not dates:
        return {}
    dlist = [b["date"] for b in bars]
    closes = [b["close"] for b in bars]
    res = {}
    for h in horizons:
        if len(closes) <= h:
            res[h] = {"ann": None, "base": None}
            continue
        base = [(closes[i + h] / closes[i] - 1) * 100 for i in range(len(closes) - h)]
        ann = []
        for d in dates:
            pos = bisect.bisect_left(dlist, d)      # 公告日或之后最近的一个交易日
            if pos >= len(closes) or pos + h >= len(closes):
                continue
            ann.append((closes[pos + h] / closes[pos] - 1) * 100)

        def pack(vals):
            if not vals:
                return None
            return {"n": len(vals),
                    "avg": sum(vals) / len(vals),
                    "win": sum(1 for v in vals if v > 0) / len(vals) * 100}

        res[h] = {"ann": pack(ann), "base": pack(base)}
    return res


def group_impact(bars, items, h=5, min_n=5):
    """按公告种类分组：这类公告之后 h 个交易日平均涨多少。太少的组不显示。"""
    if not bars or not items:
        return []
    dlist = [b["date"] for b in bars]
    closes = [b["close"] for b in bars]
    buckets = {}
    seen = set()
    for it in items:
        key = (it.get("date") or "", it.get("etype") or "其他")
        if key in seen:
            continue
        seen.add(key)
        pos = bisect.bisect_left(dlist, it.get("date") or "")
        if pos >= len(closes) or pos + h >= len(closes):
            continue
        buckets.setdefault(it.get("etype") or "其他", []).append(
            (closes[pos + h] / closes[pos] - 1) * 100)
    rows = []
    for name, vals in buckets.items():
        if len(vals) < min_n:
            continue
        rows.append({"type": name, "n": len(vals),
                     "avg": sum(vals) / len(vals),
                     "win": sum(1 for v in vals if v > 0) / len(vals) * 100})
    rows.sort(key=lambda r: -r["avg"])
    return rows


# ---------------- 4. 主窗口 ----------------

class App:
    def __init__(self, root):
        self.root = root
        self.watch = load_watch()
        self.code = self.watch[0][0] if self.watch else "600519"
        self.name = self.watch[0][1] if self.watch else ""
        self.bars = []
        self.analysis = None
        self.view_n = 250          # 当前显示多少根
        self.view_bars = None      # 分钟线（None = 显示日线）
        self.view_ma = None        # 分钟线对应的均线
        self.period = 101          # 当前周期
        self.secid = None          # 搜索来的准确市场编号（如 1.600519）
        self.q = queue.Queue()
        self.loading = False
        self.var_live = tk.BooleanVar(value=True)   # 盘中自动每 5 秒刷一次报价
        self.quote = None
        self._last_live_txt = ""

        root.title("股市助手 · 自选股 K 线与规则体检")
        root.geometry("1280x800")
        root.minsize(1000, 640)
        root.configure(bg="#f2f4f7")
        self._build_ui()
        self._load(show_msg=True)
        root.after(120, self._poll)
        root.after(2500, self._tick_live)

    def _mk_entry(self, parent, width=10):
        """统一样式的输入框：细边框，聚焦时变蓝。"""
        return tk.Entry(parent, width=width, font=FONT, relief="flat", bd=0,
                        highlightthickness=1, highlightbackground="#d8dce2",
                        highlightcolor="#1a73e8", insertbackground=TEXT)

    # ---- 界面骨架 ----
    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", font=FONT, padding=(10, 4), background="#f7f9fc",
                        bordercolor="#d5dae1", lightcolor="#f7f9fc", darkcolor="#f7f9fc",
                        focuscolor="#f7f9fc", relief="flat", borderwidth=1)
        style.map("TButton",
                  background=[("active", "#e9eff7"), ("pressed", "#dfe6f0")],
                  bordercolor=[("active", "#b9c6d6")])
        style.configure("TCheckbutton", background="#ffffff", font=FONT)
        style.configure("TCombobox", font=FONT)
        style.configure("TNotebook", background="#ffffff", borderwidth=0, tabmargins=(8, 8, 8, 0))
        style.configure("TNotebook.Tab", font=FONT_S, padding=(7, 5))
        style.map("TNotebook.Tab",
                  background=[("selected", "#ffffff"), ("", "#eef1f5")],
                  foreground=[("selected", "#1a73e8"), ("", MUTED)])

        # 顶部工具条
        top = tk.Frame(self.root, bg="#ffffff", height=54)
        top.pack(side="top", fill="x")
        tk.Frame(top, bg="#e6e8eb", height=1).pack(side="bottom", fill="x")

        self.lbl_title = tk.Label(top, text="股市助手", font=FONT_T, bg="#ffffff", fg=TEXT)
        self.lbl_title.pack(side="left", padx=(14, 12), pady=10)
        tk.Frame(top, bg="#e6e8eb", width=1, height=22).pack(side="left", padx=(0, 12), pady=16)

        self.entry_code = self._mk_entry(top, 9)
        self.entry_code.pack(side="left", pady=13)
        self.entry_code.insert(0, self.code)
        self.entry_code.bind("<Return>", lambda e: self._load())

        ttk.Button(top, text="看这只", command=self._load).pack(side="left", padx=(8, 4), pady=10)
        ttk.Button(top, text="刷新数据", command=lambda: self._load(refresh=True)).pack(side="left", pady=10)

        # 顶栏也放一个搜索框（有人就是不看左栏）
        tk.Label(top, text="搜股票", font=FONT_S, bg="#ffffff", fg=MUTED).pack(side="left", padx=(20, 6))
        self.entry_top = self._mk_entry(top, 10)
        self.entry_top.pack(side="left", pady=13)
        self.entry_top.bind("<Return>", lambda e: self._on_search_top())
        ttk.Button(top, text="搜一下", command=self._on_search_top).pack(side="left", padx=(8, 0), pady=10)

        self.lbl_status = tk.Label(top, text="", font=FONT_S, bg="#ffffff", fg=MUTED)
        self.lbl_status.pack(side="right", padx=(6, 16))
        self.lbl_live = tk.Label(top, text="", font=FONT_S, bg="#ffffff", fg=MUTED)
        self.lbl_live.pack(side="right")
        self.chk_live = tk.Checkbutton(
            top, text="实时", font=FONT_S, bg="#ffffff", fg=MUTED, variable=self.var_live,
            activebackground="#ffffff", activeforeground=TEXT, selectcolor="#ffffff",
            bd=0, highlightthickness=0, cursor="hand2", command=self._on_live_toggle)
        self.chk_live.pack(side="right", padx=(0, 8))
        self.lbl_live.configure(text="实时准备中…" if is_trading_time() else "已收盘")

        # 菜单栏（Ctrl+F 搜股票、Ctrl+D 按代码加自选、Delete 删自选）
        menubar = tk.Menu(self.root, tearoff=0)
        m_tool = tk.Menu(menubar, tearoff=0)
        m_tool.add_command(label="搜索股票…", accelerator="Ctrl+F", command=self._focus_search)
        m_tool.add_command(label="按代码加入自选", accelerator="Ctrl+D",
                           command=lambda: self.entry_add.focus_set())
        m_tool.add_command(label="删除选中的自选股", accelerator="Delete", command=self._remove_watch)
        m_tool.add_separator()
        m_tool.add_command(label="退出", command=self.root.destroy)
        menubar.add_cascade(label="工具", menu=m_tool)
        try:
            self.root.config(menu=menubar)
        except tk.TclError:
            pass
        self.root.bind("<Control-f>", lambda e: self._focus_search())
        self.root.bind("<Control-F>", lambda e: self._focus_search())
        self.root.bind("<Control-d>", lambda e: self.entry_add.focus_set())

        # 主体：左列表 + 中图 + 右体检
        body = tk.Frame(self.root, bg="#f2f4f7")
        body.pack(side="top", fill="both", expand=True)

        left = tk.Frame(body, bg="#ffffff", width=210)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Frame(left, bg="#e6e8eb", width=1).pack(side="right", fill="y")
        # 搜索：名字 / 拼音 / 代码都行
        box = tk.Frame(left, bg="#ffffff")
        box.pack(fill="x", padx=10, pady=(12, 4))
        tk.Label(box, text="搜索股票", font=FONT_B, bg="#ffffff", fg=TEXT).pack(anchor="w")
        self.entry_search = self._mk_entry(box, 6)
        self.entry_search.pack(fill="x", pady=(5, 0), ipady=4)
        self.entry_search.bind("<Return>", lambda e: self._on_search())
        ttk.Button(box, text="搜索", command=self._on_search).pack(fill="x", pady=(5, 0))
        self.lbl_search = tk.Label(box, text="中文 / 拼音 / 代码", font=FONT_S,
                                   bg="#ffffff", fg=MUTED, anchor="w", justify="left",
                                   wraplength=170)
        self.lbl_search.pack(anchor="w", fill="x", pady=(3, 0))

        hdr = tk.Frame(left, bg="#ffffff")
        hdr.pack(fill="x", padx=12, pady=(12, 5))
        tk.Label(hdr, text="自选股", font=FONT_B, bg="#ffffff", fg=TEXT).pack(side="left")
        tk.Label(hdr, text="Delete 删", font=FONT_S, bg="#ffffff", fg="#9aa3af").pack(side="right")

        self.listbox = tk.Listbox(left, font=("Microsoft YaHei UI", 10), activestyle="none",
                                  relief="flat", highlightthickness=0, selectbackground="#dbe9fd",
                                  selectforeground=TEXT, bg="#ffffff", borderwidth=0,
                                  selectborderwidth=0, exportselection=False)
        self.listbox.pack(fill="both", expand=True, padx=6)
        self.listbox.bind("<<ListboxSelect>>", self._on_pick)
        self.listbox.bind("<Delete>", lambda e: self._remove_watch())
        self._fill_list()

        add = tk.Frame(left, bg="#ffffff")
        add.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(add, text="按代码加自选", font=FONT_S, bg="#ffffff", fg=MUTED).pack(anchor="w")
        self.entry_add = self._mk_entry(add, 6)
        self.entry_add.pack(fill="x", pady=(3, 0), ipady=4)
        self.entry_add.bind("<Return>", lambda e: self._add_watch())
        ttk.Button(add, text="加入自选", command=self._add_watch).pack(fill="x", pady=(5, 0))

        rm = tk.Frame(left, bg="#ffffff")
        rm.pack(fill="x", padx=10, pady=(0, 10))
        tk.Label(rm, text="滚轮缩放图 · ← → 平移", font=FONT_S, bg="#ffffff",
                 fg="#9aa3af").pack(anchor="w")
        tk.Button(rm, text="删除选中的自选股", font=FONT_S, relief="flat", bg="#ffffff",
                  fg="#b42318", activebackground="#fdeaea", activeforeground="#b42318",
                  cursor="hand2", bd=0, padx=0,
                  command=self._remove_watch).pack(anchor="w", pady=(3, 0))

        right = tk.Frame(body, bg="#ffffff", width=330)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        tk.Frame(right, bg="#e6e8eb", width=1).pack(side="left", fill="y")

        self.note = ttk.Notebook(right)
        self.note.pack(side="left", fill="both", expand=True, padx=0, pady=8)

        # ---------------- 第一页：今天怎么办（机械打分） ----------------
        f_dec = tk.Frame(self.note, bg="#ffffff")
        self.note.add(f_dec, text="今天怎么办")
        f_dec.rowconfigure(7, weight=1)
        f_dec.columnconfigure(0, weight=1)

        tk.Label(f_dec, text="机械规则说（不是预测，也不是建议）", font=FONT_S,
                 bg="#ffffff", fg=MUTED).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        self.lbl_verdict = tk.Label(f_dec, text="—", font=("Microsoft YaHei UI", 15, "bold"),
                                    bg="#ffffff", fg=MUTED, anchor="w", justify="left")
        self.lbl_verdict.grid(row=1, column=0, sticky="w", padx=12)
        self.lbl_score = tk.Label(f_dec, text="", font=FONT_S, bg="#ffffff", fg=MUTED,
                                  anchor="w", justify="left")
        self.lbl_score.grid(row=2, column=0, sticky="w", padx=12, pady=(2, 4))

        self.var_holding = tk.BooleanVar(value=False)
        ttk.Checkbutton(f_dec, text="我已经持有这只股票", variable=self.var_holding,
                        command=self._update_decision).grid(row=3, column=0, sticky="w",
                                                            padx=12, pady=(0, 6))

        self.txt_dec = tk.Text(f_dec, font=FONT_S, bg="#ffffff", relief="flat", wrap="word",
                               state="disabled", padx=2, pady=2, fg=TEXT, width=1, height=7,
                               highlightthickness=0, spacing1=1, spacing3=5)
        self.txt_dec.grid(row=4, column=0, sticky="new", padx=10)
        for tag, color in (("up", UP), ("down", DOWN), ("muted", MUTED),
                           ("n", TEXT), ("b", TEXT)):
            self.txt_dec.tag_configure(tag, foreground=color,
                                       font=FONT_B if tag == "b" else FONT_S)

        self.lbl_dec_note = tk.Label(f_dec, text="", font=FONT_S, bg="#ffffff", fg=MUTED,
                                     anchor="nw", justify="left", wraplength=280)
        self.lbl_dec_note.grid(row=5, column=0, sticky="new", padx=12, pady=(6, 0))
        tk.Label(f_dec, text="六条规则的原文见「使用说明.md」第十三节", font=FONT_S,
                 bg="#ffffff", fg="#9aa3af", anchor="w").grid(
            row=6, column=0, sticky="sw", padx=12, pady=(6, 0))
        tk.Frame(f_dec, bg="#ffffff").grid(row=7, column=0, sticky="nsew")

        # ---------------- 第二页：规则体检 ----------------
        f_check = tk.Frame(self.note, bg="#ffffff")
        self.note.add(f_check, text="规则体检")

        self.txt_notes = tk.Text(f_check, font=FONT, bg="#ffffff", relief="flat", wrap="word",
                                 height=13, state="disabled", padx=12, pady=6, fg=TEXT,
                                 cursor="arrow", highlightthickness=0)
        self.txt_notes.pack(fill="x")
        for tag, color in (("up", UP), ("down", DOWN), ("muted", MUTED), ("b", TEXT)):
            self.txt_notes.tag_configure(tag, foreground=color,
                                         font=FONT_B if tag == "b" else FONT)

        tk.Label(f_check, text="这条规则过去有多准", font=FONT_B, bg="#ffffff",
                 fg=TEXT).pack(anchor="w", padx=12, pady=(12, 4))
        self.v_bt = tk.StringVar(value="—")
        self.v_hold = tk.StringVar(value="—")
        grid = tk.Frame(f_check, bg="#ffffff")
        grid.pack(fill="x", padx=12)
        for r, (k, var) in enumerate((("规则收益", self.v_bt), ("买入不动", self.v_hold))):
            tk.Label(grid, text=k, font=FONT, bg="#ffffff", fg=MUTED).grid(row=r, column=0, sticky="w", pady=3)
            tk.Label(grid, textvariable=var, font=FONT_B, bg="#ffffff", fg=TEXT).grid(
                row=r, column=1, sticky="w", padx=8)

        self.txt_be = tk.Text(f_check, font=FONT, bg="#fff8f0", relief="flat", wrap="word",
                              height=8, state="disabled", padx=10, pady=8, fg="#7a4b00",
                              highlightthickness=0)
        self.txt_be.pack(fill="x", padx=12, pady=(8, 10))

        # ---------------- 第三页：新闻 · 公告 · 研报 ----------------
        f_news = tk.Frame(self.note, bg="#ffffff")
        self.note.add(f_news, text="新闻·公告")
        f_news.rowconfigure(1, weight=1)
        f_news.columnconfigure(0, weight=1)

        self.lbl_news_head = tk.Label(f_news, text="切到一只股票，才会去拉它的新闻",
                                      font=FONT_S, bg="#ffffff", fg=MUTED, justify="left",
                                      anchor="w", wraplength=280)
        self.lbl_news_head.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))

        self.txt_news = tk.Text(f_news, font=FONT_S, bg="#ffffff", relief="flat", wrap="char",
                                height=8, state="disabled", padx=3, pady=2, fg=TEXT,
                                cursor="hand2", highlightthickness=0, spacing1=1, spacing3=2,
                                width=1)
        self.txt_news.grid(row=1, column=0, sticky="nsew", padx=6)
        for tag, color in (("good", UP), ("bad", DOWN), ("flat", MUTED),
                           ("muted", MUTED), ("title", TEXT)):
            self.txt_news.tag_configure(tag, foreground=color)
        self.txt_news.bind("<Double-Button-1>", self._open_news)
        self.news_urls = []

        tk.Label(f_news, text="双击某条 → 打开原文；标签是数关键词，不是判断",
                 font=FONT_S, bg="#ffffff", fg=MUTED).grid(row=2, column=0, sticky="w",
                                                          padx=10, pady=(4, 2))

        self.txt_impact = tk.Text(f_news, font=FONT_S, bg="#f4f7fb", relief="flat", wrap="char",
                                  height=12, state="disabled", padx=6, pady=5, fg="#1f3b63",
                                  highlightthickness=0, width=1)
        self.txt_impact.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))

        # ---------------- 第四页：公司简介 ----------------
        f_org = tk.Frame(self.note, bg="#ffffff")
        self.note.add(f_org, text="公司简介")
        f_org.rowconfigure(1, weight=1)
        f_org.columnconfigure(0, weight=1)

        self.lbl_org_head = tk.Label(f_org, text="切到一只股票，才会去拉它的资料",
                                     font=FONT_B, bg="#ffffff", fg=TEXT, justify="left",
                                     anchor="w", wraplength=292)
        self.lbl_org_head.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))

        self.txt_org = tk.Text(f_org, font=FONT_S, bg="#ffffff", relief="flat", wrap="char",
                               state="disabled", padx=3, pady=2, fg=TEXT,
                               highlightthickness=0, spacing1=1, spacing3=3, width=1)
        self.txt_org.grid(row=1, column=0, sticky="nsew", padx=8)
        for tag, kw in (("sec", {"foreground": "#1a73e8", "font": FONT_B,
                                 "spacing1": 8, "spacing3": 3}),
                        ("k", {"foreground": MUTED, "font": FONT_S}),
                        ("n", {"foreground": TEXT, "font": FONT_S}),
                        ("big", {"foreground": TEXT, "font": FONT_B})):
            self.txt_org.tag_configure(tag, **kw)

        # 中间图
        mid = tk.Frame(body, bg="#ffffff")
        mid.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        head = tk.Frame(mid, bg="#ffffff")
        head.pack(side="top", fill="x", padx=4, pady=(8, 0))
        self.lbl_quote = tk.Label(head, text="", font=("Microsoft YaHei UI", 13, "bold"),
                                  bg="#ffffff", fg=TEXT)
        self.lbl_quote.pack(side="left")
        self.lbl_code = tk.Label(head, text="", font=FONT_S, bg="#ffffff", fg="#9aa3af")
        self.lbl_code.pack(side="left", padx=(8, 0))
        self.lbl_price = tk.Label(head, text="", font=("Microsoft YaHei UI", 15, "bold"),
                                  bg="#ffffff")
        self.lbl_price.pack(side="left", padx=(14, 0))
        self.lbl_chg = tk.Label(head, text="", font=FONT_B, bg="#ffffff")
        self.lbl_chg.pack(side="left", padx=(10, 0))
        self.lbl_meta = tk.Label(head, text="", font=FONT_S, bg="#ffffff", fg="#9aa3af")
        self.lbl_meta.pack(side="right")

        bar = tk.Frame(mid, bg="#ffffff")
        bar.pack(side="top", fill="x", padx=4, pady=(6, 4))
        self.view_btns = []
        for label, n in (("3 个月", 60), ("半年", 120), ("1 年", 250), ("全部", 0)):
            b = tk.Button(bar, text=label, font=FONT, relief="flat", bd=0, width=7, pady=3,
                          cursor="hand2", bg="#f7f9fc", fg=TEXT, activebackground="#e9eff7",
                          activeforeground=TEXT, highlightthickness=0,
                          command=lambda n=n: self._set_view(n))
            b.pack(side="left", padx=(0, 6))
            self.view_btns.append((b, n))
        tk.Label(bar, text="滚轮缩放 · ← → 平移 · 鼠标停在图上看当天价格",
                 font=FONT_S, bg="#ffffff", fg=MUTED).pack(side="right")

        pbar = tk.Frame(mid, bg="#ffffff")
        pbar.pack(side="top", fill="x", padx=4, pady=(0, 2))
        tk.Label(pbar, text="周期", font=FONT_S, bg="#ffffff",
                 fg=MUTED).pack(side="left", padx=(2, 6))
        self.period_btns = []
        for klt, label, _scale in PERIODS:
            b = tk.Button(pbar, text=label, font=FONT_S, relief="flat", bd=0, width=5, pady=2,
                          cursor="hand2", bg="#f7f9fc", fg=TEXT, activebackground="#e9eff7",
                          activeforeground=TEXT, highlightthickness=0,
                          command=lambda k=klt: self._set_period(k))
            b.pack(side="left", padx=(0, 4))
            self.period_btns.append((b, klt))
        self.lbl_period = tk.Label(pbar, text="分钟线只换看图粒度，规则体检仍按日线算",
                                   font=FONT_S, bg="#ffffff", fg="#9aa3af")
        self.lbl_period.pack(side="right", padx=(6, 2))

        self.canvas = tk.Canvas(mid, bg="#ffffff", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(side="top", fill="both", expand=True, padx=4, pady=(0, 8))
        self.canvas.bind("<Configure>", lambda e: self._draw())
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda e: self._clear_cross())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self._sync_view_buttons()
        self.root.bind("<Left>", lambda e: self._pan(-1))
        self.root.bind("<Right>", lambda e: self._pan(1))
        self.tip = None

    def _fill_list(self):
        self.listbox.delete(0, "end")
        self.listbox.selection_clear(0, "end")
        for code, name in self.watch:
            self.listbox.insert("end", "  {}   {}".format(code, name))
        for i, (code, _) in enumerate(self.watch):
            if code == self.code:
                self.listbox.selection_set(i)

    # ---- 搜索（后台搜，界面不卡） ----
    def _say(self, text, color=None):
        """搜索框下面那行小字，专门显示搜索状态（不再跑到右上角去）。"""
        try:
            self.lbl_search.configure(text=text, fg=color or MUTED)
        except Exception:                        # noqa: BLE001
            pass

    def _on_search(self):
        kw = self.entry_search.get().strip()
        if not kw:
            self._say("先输点东西：中文、拼音或 6 位代码")
            self.entry_search.focus_set()
            return
        self._say("正在搜「{}」……".format(kw))
        log("搜索：" + kw)

        def work():
            try:
                self.q.put(("search", kw, "", search_stocks(kw)))
            except Exception as e:          # noqa: BLE001
                log("搜索失败 {}：{}".format(kw, e))
                self.q.put(("search_err", kw, "", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _show_results(self, kw, results):
        """把搜索结果放在一个小窗口里，双击就打开。"""
        if not results:
            self._say("没搜到「{}」，换个词试试".format(kw), UP)
            log("搜索无结果：" + kw)
            try:
                self.entry_search.focus_set()
                self.entry_search.selection_range(0, "end")
            except tk.TclError:
                pass
            return

        self._say("搜到 {} 只，选一个".format(len(results)))
        win = tk.Toplevel(self.root)
        win.title("搜索结果：{}".format(kw))
        win.configure(bg="#ffffff")
        win.transient(self.root)
        win.resizable(False, False)

        tk.Label(win, text="「{}」搜到 {} 只，双击一行打开".format(kw, len(results)),
                 font=FONT, bg="#ffffff", fg=MUTED).pack(anchor="w", padx=14, pady=(12, 6))

        box = tk.Listbox(win, font=("Microsoft YaHei UI", 10), activestyle="none", width=40,
                         height=min(len(results), 10), relief="solid", bd=1,
                         selectbackground="#e8f0fe", selectforeground=TEXT,
                         highlightthickness=0)
        box.pack(fill="both", padx=14)
        for r in results:
            box.insert("end", "  {}   {}    ({})".format(r["code"], r["name"], r["market"]))
        box.selection_set(0)

        def open_selected(event=None):
            sel = box.curselection()
            if not sel:
                return
            win.destroy()
            self._load_stock(results[sel[0]])

        def add_selected():
            sel = box.curselection()
            if not sel:
                return
            win.destroy()
            self._add_watch(results[sel[0]]["code"])

        box.bind("<Double-Button-1>", open_selected)
        box.bind("<Return>", open_selected)

        btns = tk.Frame(win, bg="#ffffff")
        btns.pack(fill="x", padx=14, pady=12)
        ttk.Button(btns, text="看这只", command=open_selected).pack(side="left")
        ttk.Button(btns, text="加入自选", command=add_selected).pack(side="left", padx=6)
        ttk.Button(btns, text="取消", command=win.destroy).pack(side="right")

        win.update_idletasks()
        x = self.root.winfo_rootx() + 60
        y = self.root.winfo_rooty() + 120
        win.geometry("+{}+{}".format(x, y))
        try:
            win.grab_set()
        except tk.TclError:
            pass
        win.lift()
        try:
            win.focus_force()
            box.focus_set()
        except tk.TclError:
            pass

    def _load_stock(self, item):
        """打开搜索结果里的那一只（带上它准确的 secid）。"""
        self.code, self.name = item["code"], item["name"]
        self.entry_code.delete(0, "end")
        self.entry_code.insert(0, item["code"])
        self._load(secid=item["secid"])

    # ---- 实时报价 ----
    def _on_live_toggle(self):
        if self.var_live.get():
            self._ask_quote()
        else:
            self.lbl_live.configure(text="实时已关（点一下打开）", fg=MUTED)

    def _ask_quote(self):
        code = self.code
        secid = self.secid

        def work():
            try:
                self.q.put(("quote", code, "", fetch_quote(code, secid=secid)))
            except Exception as e:              # noqa: BLE001 - 刷新报价失败不该打断人
                self.q.put(("quote_err", code, "", str(e)[:60]))

        threading.Thread(target=work, daemon=True).start()

    def _tick_live(self):
        try:
            if not self.code or not self.bars:
                pass
            elif not self.var_live.get():
                pass
            elif is_trading_time():
                self._ask_quote()
            else:
                self.lbl_live.configure(text="已收盘", fg=MUTED)
        finally:
            self.root.after(5000, self._tick_live)

    def _apply_quote(self, q):
        """把实时价写进顶栏；如果最后一根日线就是今天，顺便把它的收盘/最高/最低更新。"""
        if not q or q.get("code") != self.code:
            return
        self.quote = q
        prev = q.get("prev") or 0.0
        amt = q["price"] - prev
        chg = (amt / prev * 100) if prev else 0.0
        color = UP if amt >= 0 else DOWN
        self.lbl_price.configure(text="{:.2f}".format(q["price"]), fg=color)
        self.lbl_chg.configure(text="{}{:.2f}　{}{:.2f}%".format(
            "+" if amt >= 0 else "", amt, "+" if chg >= 0 else "", chg), fg=color)

        changed = False
        if self.bars and self.bars[-1]["date"] == q["date"]:
            b = self.bars[-1]
            new_b = {"date": b["date"], "open": q["open"] or b["open"], "close": q["price"],
                     "high": max(b["high"], q["high"]), "low": min(b["low"], q["low"]),
                     "vol": q["vol"] or b["vol"]}
            if (new_b["close"], new_b["high"], new_b["low"]) != (b["close"], b["high"], b["low"]):
                self.bars[-1] = new_b
                self.analysis = analyze(self.bars)
                changed = True

        tip = "实时 {}".format(q["time"])
        if not is_trading_time():
            tip = "已收盘 {}".format(q["time"])
        self.lbl_live.configure(text=tip, fg="#1a73e8" if is_trading_time() else MUTED)
        if changed:
            self._update_notes()
            self._update_decision()
            self._draw()

    # ---- 数据加载（放后台线程，界面不卡） ----
    def _load(self, refresh=False, show_msg=False, secid=None):
        code = self.entry_code.get().strip()
        if not code:
            return
        if (not refresh) and not (code.isdigit() and len(code) == 6):
            # 输的不是 6 位代码（中文 / 拼音）→ 当成搜索词，别让人干瞪眼
            self.entry_search.delete(0, "end")
            self.entry_search.insert(0, code)
            self._on_search()
            return
        if self.loading:
            return
        self.code = code
        self.secid = secid
        self.quote = None
        self.loading = True
        self.lbl_status.configure(text="正在拉数据……", fg=MUTED)
        self.txt_notes.configure(state="normal")
        self.txt_notes.delete("1.0", "end")
        self.txt_notes.insert("end", "正在读取行情，请稍等……\n", "muted")
        self.txt_notes.configure(state="disabled")

        def work():
            try:
                name, bars = fetch_kline(code, secid=secid)
                self.q.put(("ok", code, name, bars))
            except Exception as e:          # noqa: BLE001 - 界面上要给人话
                log("拉数据失败 {}：{}".format(code, e))
                self.q.put(("err", code, "", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            kind, code, name, payload = self.q.get_nowait()
        except queue.Empty:
            self.root.after(120, self._poll)
            return
        self.loading = False
        if kind == "rename":
            if name:
                for item in self.watch:
                    if item[0] == code and item[1] == code:
                        item[1] = name
                save_watch(self.watch)
                self._fill_list()
                if code == self.code:
                    self.name = name
                    self._update_head()
        elif kind == "add":
            self.watch.append([code, name or code])
            save_watch(self.watch)
            self.code, self.name = code, name or code
            self.entry_code.delete(0, "end")
            self.entry_code.insert(0, code)
            self._fill_list()
            self._load()
        elif kind == "add_err":
            self.lbl_status.configure(text="加不进去：{}".format(payload), fg=UP)
        elif kind == "search":
            self._show_results(code, payload)
        elif kind == "search_err":
            self._say("搜索失败：{}".format(payload), UP)
        elif kind == "err":
            self.lbl_status.configure(text="加载失败：{}".format(payload), fg=UP)
            self.txt_notes.configure(state="normal")
            self.txt_notes.delete("1.0", "end")
            self.txt_notes.insert("end", "没拿到数据：{}\n\n检查网络，或确认代码写对了。".format(payload), "up")
            self.txt_notes.configure(state="disabled")
        elif kind == "news":
            self._show_news(payload)
        elif kind == "org":
            self._show_org(code, payload)
        elif kind == "org_err":
            self.lbl_org_head.configure(text="公司资料没拿到：{}".format(payload),
                                        fg=MUTED)
            log("公司资料失败 {}：{}".format(code, payload))
        elif kind == "quote":
            self._apply_quote(payload)
        elif kind == "minute":
            klt, bars = payload
            self._show_minute(klt, bars)
        elif kind == "minute_err":
            klt, msg = payload
            self.lbl_status.configure(text="{} 分钟线没拿到：{}".format(klt, msg), fg=UP)
        elif kind == "quote_err":
            self.lbl_live.configure(text="实时拿不到价（{}）".format(payload), fg=MUTED)
        else:
            self.name = name or self.name
            self.bars = payload
            self.analysis = analyze(self.bars)
            self._reset_period()
            self.lbl_status.configure(text="数据：{} 根，最新 {}".format(
                len(self.bars), self.bars[-1]["date"]), fg=MUTED)
            self._update_head()
            self._update_notes()
            self._update_decision()
            self._draw()
            self._fill_list()
            self._load_news()
            self._load_org()
            self._apply_tab_from_env()
            self.root.after(150, self._ask_quote)
        self.root.after(120, self._poll)

    # ---- 右侧文字 ----
    def _update_head(self):
        b = self.bars[-1]
        prev = self.bars[-2]["close"] if len(self.bars) > 1 else b["open"]
        amt = b["close"] - prev
        chg = (amt / prev * 100) if prev else 0.0
        color = UP if amt >= 0 else DOWN
        self.lbl_quote.configure(text=self.name or self.code)
        self.lbl_code.configure(text=self.code)
        self.lbl_price.configure(text="{:.2f}".format(b["close"]), fg=color)
        self.lbl_chg.configure(text="{}{:.2f}　{}{:.2f}%".format(
            "+" if amt >= 0 else "", amt, "+" if chg >= 0 else "", chg), fg=color)
        if self.view_bars:
            self.lbl_meta.configure(text="{} 分钟线 {} 根　{} ~ {}".format(
                self.period, len(self.view_bars),
                self.view_bars[0]["date"][:16], self.view_bars[-1]["date"][:16]))
        else:
            self.lbl_meta.configure(text="共 {} 根日线　{} ~ {}".format(
                len(self.bars), self.bars[0]["date"], self.bars[-1]["date"]))
        try:
            self.root.title("股市助手 — {} {}".format(self.name or "", self.code))
        except tk.TclError:
            pass

    def _update_notes(self):
        a = self.analysis
        self.txt_notes.configure(state="normal")
        self.txt_notes.delete("1.0", "end")
        for k, v, color in today_notes(self.bars, a):
            tag = "up" if color == UP else ("down" if color == DOWN else ("muted" if color == MUTED else "b"))
            self.txt_notes.insert("end", k + "\n", ("b",))
            self.txt_notes.insert("end", "    " + v + "\n", (tag,))
            self.txt_notes.insert("end", "\n")
        self.txt_notes.configure(state="disabled")

        self.v_bt.set("{:+.1f}%".format(a["rule_ret"]))
        self.v_hold.set("{:+.1f}%".format(a["hold_ret"]))
        gap = a["rule_ret"] - a["hold_ret"]
        lines = [
            "统计区间 {} ~ {}（{} 根日线）".format(
                self.bars[0]["date"], self.bars[-1]["date"], len(self.bars)),
            "",
            "{} 笔交易　胜率 {:.1f}%".format(a["n"], a["win_rate"]),
            "盈亏比 {}".format("—" if a["ratio"] is None else "{:.2f}".format(a["ratio"])),
            "最大回撤 {:.1f}%".format(a["mdd"]),
            "",
            ("同一段时间，" + ("规则跑赢" if gap > 0 else "规则跑输") +
             "「买了不动」{:.1f} 个百分点。".format(abs(gap))),
            "",
            "记住：这是过去的成绩，不是以后的保证。",
        ]
        self.txt_be.configure(state="normal")
        self.txt_be.delete("1.0", "end")
        self.txt_be.insert("end", "\n".join(lines))
        self.txt_be.configure(state="disabled")

    # ---- 今天怎么办 ----
    def _update_decision(self):
        if not self.bars or not self.analysis:
            return
        d = decide(self.bars, self.analysis, holding=bool(self.var_holding.get()))
        self.lbl_verdict.configure(text=d["verdict"], fg=d["tone"])
        self.lbl_score.configure(text="评分 {:+d}　（满分 {} 分，正数偏买、负数偏卖）".format(
            d["score"], d["top"]))
        self.txt_dec.configure(state="normal")
        self.txt_dec.delete("1.0", "end")
        for it in d["items"]:
            dl = it["delta"]
            tag = "up" if dl > 0 else ("down" if dl < 0 else "muted")
            mark = "+{}".format(dl) if dl > 0 else ("{}".format(dl) if dl < 0 else " 0")
            self.txt_dec.insert("end", "{:>3}　".format(mark), tag)
            self.txt_dec.insert("end", it["text"] + "\n", "b" if abs(dl) >= 2 else "n")
        self.txt_dec.configure(state="disabled")

        a = self.analysis
        gap = a["rule_ret"] - a["hold_ret"]
        warn = ""
        if gap < 0:
            warn = "⚠ 这套规则在这只股票上过去跑输买入不动 {:.1f} 个点，别照单全收。\n".format(abs(gap))
        ma20 = a["ma20"][-1] if a.get("ma20") and a["ma20"][-1] else 0.0
        ma60 = a["ma60"][-1] if a.get("ma60") and a["ma60"][-1] else 0.0
        tail = ""
        if ma20 and ma60:
            close = self.bars[-1]["close"]
            if close > ma20:
                tail = "\n规则在哪改口：收盘跌破 MA20 {:.2f} → 变卖点；".format(ma20)
            else:
                tail = "\n规则在哪改口：收盘站回 MA20 {:.2f} → 才重新算买点；".format(ma20)
            if close > ma60:
                tail += "跌破 MA60 {:.2f} → 直接离场。".format(ma60)
            else:
                tail += "站回 MA60 {:.2f} → 中期趋势才转多。".format(ma60)
        self.lbl_dec_note.configure(
            text=warn + "这套机械规则过去 {} 笔、胜率 {:.0f}%、收益 {:+.1f}%（买入不动 {:+.1f}%，"
                 "{} {:.1f} 个点）。规则写死、可复核；它不是预测，下次也不保证一样。{}".format(
                     a["n"], a["win_rate"], a["rule_ret"], a["hold_ret"],
                     "跑赢" if gap > 0 else "跑输", abs(gap), tail))

    # ---- 新闻页 ----
    # ---- 公司简介 ----
    def _load_org(self):
        code = self.code
        self.lbl_org_head.configure(text="正在拉「{}」的公司资料……".format(self.name))
        self.txt_org.configure(state="normal")
        self.txt_org.delete("1.0", "end")
        self.txt_org.configure(state="disabled")

        def work():
            try:
                self.q.put(("org", code, "", fetch_org(code)))
            except Exception as e:                  # noqa: BLE001 - 页面上要给人话
                self.q.put(("org_err", code, "", str(e)[:80]))

        threading.Thread(target=work, daemon=True).start()

    def _apply_tab_from_env(self):
        """调试用：环境变量 DSH_TAB=0..3 让人一打开就停在那页（给截图脚本用）。"""
        tab = os.environ.get("DSH_TAB", "")
        if tab.isdigit():
            try:
                self.note.select(int(tab))
            except tk.TclError:
                pass

    def _show_org(self, code, p):
        if not p or code != self.code:
            return
        self.lbl_org_head.configure(
            text="{}　{}　{}".format(p["name"] or self.name, self.code, p["industry"]))
        t = self.txt_org
        t.configure(state="normal")
        t.delete("1.0", "end")

        def line(k, v, tag="n"):
            if v not in (None, "", "—"):
                t.insert("end", k + "　", "k")
                t.insert("end", str(v) + "\n", tag)

        if p.get("profile"):
            t.insert("end", "一、这家公司是干什么的\n", "sec")
            t.insert("end", p["profile"] + "\n", "n")
        t.insert("end", "二、基本信息\n", "sec")
        line("公司全称", p.get("full_name"), "big")
        line("曾用名", p.get("former"))
        line("上市时间", "{}　{}".format(p.get("list_date") or "—", p.get("market") or ""))
        line("所属行业", p.get("industry"))
        line("证监会分类", p.get("industry_csrc"))
        if p.get("employees"):
            try:
                line("员工人数", "{:,} 人".format(int(p["employees"])))
            except (TypeError, ValueError):
                line("员工人数", p["employees"])
        if p.get("capital"):
            try:
                line("注册资本", "{:,.2f} 亿元".format(float(p["capital"]) / 10000.0))
            except (TypeError, ValueError):
                line("注册资本", p["capital"])
        line("董事长", p.get("chairman"))
        line("法人代表", p.get("legal"))
        line("公司地址", p.get("address"))
        line("联系电话", p.get("tel"))
        line("公司网站", p.get("web"))

        t.insert("end", "三、主营与经营范围\n", "sec")
        t.insert("end", "主营：", "k")
        t.insert("end", (p.get("main_business") or "—") + "\n", "n")
        t.insert("end", "经营范围：", "k")
        t.insert("end", (p.get("scope") or "—") + "\n", "n")

        t.insert("end", "\n", "n")
        t.insert("end", "数据来源：{}。这里只是把公开资料搬过来，不构成任何买卖建议。\n".format(
            p.get("src") or "东财"), "k")
        t.configure(state="disabled")

    def _load_news(self):
        code = self.code
        self.lbl_news_head.configure(text="正在拉「{}」的公告和研报……".format(self.name), fg=MUTED)
        self.txt_news.configure(state="normal")
        self.txt_news.delete("1.0", "end")
        self.txt_news.configure(state="disabled")
        self.news_urls = []
        self.txt_impact.configure(state="normal")
        self.txt_impact.delete("1.0", "end")
        self.txt_impact.configure(state="disabled")

        def work():
            payload = {"code": code, "anns": [], "reports": [], "problems": []}
            try:
                payload["anns"] = fetch_anns(code, pages=2)
            except Exception as e:                 # noqa: BLE001 - 页面上要给人话
                payload["problems"].append("公告：{}".format(str(e)[:50]))
            try:
                payload["reports"] = fetch_reports(code, count=8)
            except Exception as e:                 # noqa: BLE001
                payload["problems"].append("研报：{}".format(str(e)[:50]))
            self.q.put(("news", code, "", payload))

        threading.Thread(target=work, daemon=True).start()

    def _show_news(self, payload):
        if payload.get("code") != self.code:
            return                                  # 已经切到别的股票了，丢掉
        anns = payload.get("anns") or []
        reps = payload.get("reports") or []
        problems = payload.get("problems") or []

        n_good = sum(1 for a in anns if a["tag"] == "偏多")
        head = "{}　公告 {} 条·像利好 {}".format(self.name, len(anns), n_good)
        if problems:
            head += "\n有接口没通：{}".format("；".join(problems))
        self.lbl_news_head.configure(text=head, fg=TEXT if (anns or reps) else UP)

        self.txt_news.configure(state="normal")
        self.txt_news.delete("1.0", "end")
        self.news_urls = []

        def clean(title):
            """把标题里重复的公司名前缀去掉，省点地方。"""
            t = title
            for pref in (self.name + ":", self.name + "："):
                if t.startswith(pref):
                    t = t[len(pref):]
            for pref in (self.name + ":", self.name + "："):
                t = t.replace(pref, "")
            return t

        for it in anns[:40]:
            self.txt_news.insert("end", (it["date"] or "")[5:] + " ", "muted")
            self.txt_news.insert("end", it["etype"] + " ", "muted")
            self.txt_news.insert("end", clean(it["title"]) + "\n", "title")
            self.news_urls.append(it["url"])
        if len(anns) > 40:
            self.txt_news.insert("end", "（只有前 40 条；统计用的是全部 {} 条）\n".format(len(anns)),
                                 "muted")
            self.news_urls.append("")
        if reps:
            self.txt_news.insert("end", "\n机构研报（评级=机构观点，不是事实）\n", "muted")
            self.news_urls.append("")
            for it in reps:
                tg = {"偏多": "good", "偏空": "bad"}.get(it["tag"], "muted")
                self.txt_news.insert("end", (it["date"] or "")[5:] + " ", "muted")
                self.txt_news.insert("end", (it.get("rating") or "研报") + " ", tg)
                self.txt_news.insert("end", clean(it["title"]) + "\n", "title")
                self.news_urls.append(it["url"])
        if not anns and not reps:
            self.txt_news.insert("end", "没拉到公告/研报：可能网络不通，或这只是 ETF/指数，"
                                       "本来就没有公司公告。\n")
            self.news_urls.append("")
        self.txt_news.configure(state="disabled")

        self._render_impact(anns)

    def _render_impact(self, anns):
        dates = sorted({a["date"] for a in anns if a.get("date")})
        stat = impact_stats(self.bars, dates)
        lines = ["公告后涨跌（{} 条 / {} 个交易日）".format(len(anns), len(dates)), ""]
        if not stat:
            lines.append("没有可用的公告日期，算不了。")
        else:
            r1 = "{:>7}{:>7}{:>7}".format("1日", "3日", "5日")
            r2 = "{:>7}{:>7}{:>7}".format(*[
                "—" if not (stat.get(h) or {}).get("ann")
                else "{:+.1f}%".format(stat[h]["ann"]["avg"] - stat[h]["base"]["avg"])
                for h in (1, 3, 5)])
            r3 = "{:>7}{:>7}{:>7}".format(*[
                "—" if not (stat.get(h) or {}).get("ann")
                else "{:.0f}%".format(stat[h]["ann"]["win"])
                for h in (1, 3, 5)])
            lines.append("       " + r1)
            lines.append("比平时 " + r2)
            lines.append("上涨率 " + r3)
            lines.append("")
            groups = group_impact(self.bars, anns, h=5, min_n=4)[:3]
            if groups:
                lines.append("按公告种类（5日后）：")
                for g in groups:
                    lines.append("{} {:+.1f}%（{}次）".format(g["type"], g["avg"], g["n"]))
        lines.append("")
        lines.append("正数=比平时偏涨；样本少、公告还可能扎堆在")
        lines.append("某个月，这点差别别当因果，更别当指令。")
        self.txt_impact.configure(state="normal")
        self.txt_impact.delete("1.0", "end")
        self.txt_impact.insert("end", "\n".join(lines))
        self.txt_impact.configure(state="disabled")

    def _open_news(self, event=None):
        try:
            line = int(self.txt_news.index("insert").split(".")[0]) - 1
        except (tk.TclError, ValueError):
            return
        if 0 <= line < len(self.news_urls) and self.news_urls[line]:
            webbrowser.open(self.news_urls[line])

    # ---- 画图 ----
    def _visible(self):
        bars = self._disp()
        n = len(bars)
        if self.view_n == 0 or self.view_n >= n:
            return bars, 0
        return bars[-self.view_n:], n - self.view_n

    def _disp(self):
        """当前要画的K线（分钟线优先）。"""
        return self.view_bars if self.view_bars else self.bars

    def _disp_ma(self):
        return self.view_ma if self.view_bars else self.analysis

    def _sync_period_buttons(self):
        for b, klt in getattr(self, "period_btns", []):
            on = (klt == self.period)
            b.configure(bg="#1a73e8" if on else "#f7f9fc",
                        fg="#ffffff" if on else TEXT)

    def _reset_period(self, draw=False):
        self.view_bars, self.view_ma, self.period = None, None, 101
        self.view_n = 250
        self._sync_period_buttons()
        self._sync_view_buttons()
        for b, _n in getattr(self, "view_btns", []):
            b.configure(state="normal")

    def _set_period(self, klt):
        if klt == 101:
            self._reset_period()
            if self.bars:
                self._update_head()
            self._draw()
            return
        if not self.bars:
            return
        self.lbl_status.configure(text="正在取 {} 分钟线……".format(klt), fg=MUTED)
        self._pending_klt = klt
        code = self.code
        scale = dict((k, sc) for k, _l, sc in PERIODS)[klt]

        def work():
            try:
                bars = fetch_min_bars(code, scale=scale)
                self.q.put(("minute", code, "", (klt, bars)))
            except Exception as e:          # noqa: BLE001
                log("分钟线失败 {} {}分：{}".format(code, klt, e))
                self.q.put(("minute_err", code, "", (klt, str(e))))

        threading.Thread(target=work, daemon=True).start()

    def _show_minute(self, klt, bars):
        if not bars or klt != self._pending_klt:
            return
        closes = [b["close"] for b in bars]
        self.view_bars = bars
        self.view_ma = {"ma5": moving_average(closes, 5),
                        "ma20": moving_average(closes, 20),
                        "ma60": moving_average(closes, 60),
                        "buys": [], "sells": []}
        self.period = klt
        self.view_n = min(len(bars), 240)
        self._sync_period_buttons()
        self._sync_view_buttons()
        for b, _n in getattr(self, "view_btns", []):
            b.configure(state="disabled")
        self._update_head()
        self._draw()
        self.lbl_status.configure(
            text="{} 分钟线 · 新浪接口 · 最多只能回溯 {}".format(
                klt, PERIOD_SPAN.get(klt, "")), fg=MUTED)

    def _sync_view_buttons(self):
        for b, bn in getattr(self, "view_btns", []):
            on = (bn == self.view_n)
            b.configure(bg="#1a73e8" if on else "#f7f9fc",
                        fg="#ffffff" if on else TEXT)

    def _set_view(self, n):
        self.view_n = n
        self._sync_view_buttons()
        self._draw()

    def _on_wheel(self, event):
        total = len(self._disp())
        cur = self.view_n or total
        step = max(10, int(cur * 0.15))
        if event.delta > 0:
            self.view_n = max(30, cur - step)
        else:
            self.view_n = min(total, cur + step)
        self._draw()

    def _pan(self, direction):
        total = len(self._disp())
        self.view_n = max(30, min(total, (self.view_n or total) + direction * 10))
        self._draw()

    def _draw(self):
        c = self.canvas
        c.delete("all")
        if not self._disp():
            c.create_text(c.winfo_width() // 2, c.winfo_height() // 2,
                          text="没有数据", fill=MUTED, font=FONT)
            return
        view, start = self._visible()
        a = self._disp_ma()
        ma5 = a["ma5"][start:] if self.view_n else a["ma5"]
        ma20 = a["ma20"][start:] if self.view_n else a["ma20"]
        ma60 = a["ma60"][start:] if self.view_n else a["ma60"]

        w, h = c.winfo_width(), c.winfo_height()
        if w < 200 or h < 200:
            return
        pl, pr, pt, pb = 60, 56, 14, 26
        vol_h = int((h - pt - pb) * 0.2)
        gap = 18
        p_bottom = h - pb - vol_h - gap
        vol_top = p_bottom + gap
        plot_w = w - pl - pr
        n = len(view)
        bw = plot_w / n

        pmin = min(b["low"] for b in view)
        pmax = max(b["high"] for b in view)
        pad = (pmax - pmin) * 0.06 or 1
        pmin -= pad
        pmax += pad

        def y_of(p):
            return pt + (pmax - p) / (pmax - pmin) * (p_bottom - pt)

        def x_of(i):
            return pl + (i + 0.5) * bw

        def fmt_price(p):
            return "{:.2f}".format(p) if pmax < 100 else "{:.0f}".format(p)

        # 横向网格 + 价格刻度
        for k in range(5):
            p = pmin + (pmax - pmin) * k / 4
            y = y_of(p)
            c.create_line(pl, y, pl + plot_w, y, fill=GRID)
            c.create_text(pl - 8, y, text=fmt_price(p), anchor="e", fill=MUTED, font=FONT_S)

        # 均线
        for series, color, width in ((ma60, MA60_C, 1), (ma20, MA20_C, 2), (ma5, MA5_C, 1)):
            pts = []
            for i, v in enumerate(series):
                if v is None:
                    if len(pts) >= 4:
                        c.create_line(*pts, fill=color, width=width)
                    pts = []
                else:
                    pts += [x_of(i), y_of(v)]
            if len(pts) >= 4:
                c.create_line(*pts, fill=color, width=width)

        # 蜡烛
        half = max(0.6, bw * 0.3)
        for i, b in enumerate(view):
            x = x_of(i)
            up = b["close"] >= b["open"]
            color = UP if up else DOWN
            c.create_line(x, y_of(b["high"]), x, y_of(b["low"]), fill=color)
            y1, y2 = y_of(b["open"]), y_of(b["close"])
            if abs(y1 - y2) < 1:
                c.create_line(x - half, y1, x + half, y1, fill=color)
            else:
                c.create_rectangle(x - half, min(y1, y2), x + half, max(y1, y2),
                                   fill=color, outline=color)

        # 买卖点（只有日线才有规则买卖点）
        for s in ([] if self.view_bars else a["buys"]):
            if s["i"] < start:
                continue
            x, y = x_of(s["i"] - start), y_of(view[s["i"] - start]["low"])
            c.create_polygon(x, y + 6, x - 5, y + 15, x + 5, y + 15, fill=UP, outline="")
        for s in ([] if self.view_bars else a["sells"]):
            if s["i"] < start:
                continue
            x, y = x_of(s["i"] - start), y_of(view[s["i"] - start]["high"])
            c.create_polygon(x, y - 6, x - 5, y - 15, x + 5, y - 15, fill=DOWN, outline="")

        # 成交量
        vmax = max(b["vol"] for b in view) or 1
        for i, b in enumerate(view):
            x = x_of(i)
            y = vol_top + (1 - b["vol"] / vmax) * (h - pb - vol_top)
            color = UP if b["close"] >= b["open"] else DOWN
            c.create_rectangle(x - half, y, x + half, h - pb, fill=color, outline=color)

        c.create_text(pl - 8, vol_top + 4, text="成交量", anchor="ne", fill="#9aa3af", font=FONT_S)
        c.create_text(pl + plot_w + 6, vol_top + 4,
                      text="{:.0f}万手".format(vmax / 10000) if vmax >= 10000
                      else "{:.0f}手".format(vmax),
                      anchor="nw", fill="#9aa3af", font=FONT_S)

        # 最新价虚线 + 右侧价签
        last = view[-1]
        y_last = y_of(last["close"])
        c.create_line(pl, y_last, pl + plot_w, y_last, fill="#c2ccd6", dash=(4, 4))
        tag = fmt_price(last["close"])
        c.create_rectangle(pl + plot_w + 2, y_last - 10, pl + plot_w + 44, y_last + 10,
                           fill=UP if last["close"] >= last["open"] else DOWN, outline="")
        c.create_text(pl + plot_w + 23, y_last, text=tag, fill="#ffffff", font=FONT_S)

        # 日期刻度
        step = max(1, n // 8)
        for i in range(0, n, step):
            c.create_text(x_of(i), h - pb + 12,
                          text=view[i].get("label") or view[i]["date"][5:],
                          fill=MUTED, font=FONT_S)

        # 图例
        lx = pl + 2
        for label, color in (("MA5", MA5_C), ("MA20", MA20_C), ("MA60", MA60_C)):
            c.create_line(lx, pt - 6, lx + 16, pt - 6, fill=color, width=2)
            c.create_text(lx + 20, pt - 6, text=label, anchor="w", fill=MUTED, font=FONT_S)
            lx += 62
        c.create_text(pl + plot_w, pt - 6,
                      text="分钟线：只画价格和均线" if self.view_bars
                      else "▲ 买点触发　▼ 卖点触发", anchor="e",
                      fill="#9aa3af", font=FONT_S)

        # 保存画图参数，鼠标移动时用来换算
        self._geo = dict(view=view, start=start, pl=pl, plot_w=plot_w, bw=bw,
                         pt=pt, p_bottom=p_bottom, h=h, pb=pb, pmin=pmin, pmax=pmax,
                         vol_top=vol_top)
        self._draw_cross_from_state()

    def _draw_cross_from_state(self):
        if getattr(self, "_hover_i", None) is not None:
            self._draw_cross(self._hover_i)

    def _clear_cross(self):
        self.canvas.delete("cross")
        self._hover_i = None

    def _on_motion(self, event):
        g = getattr(self, "_geo", None)
        if not g:
            return
        i = int((event.x - g["pl"]) / g["bw"])
        if i < 0 or i >= len(g["view"]):
            self._clear_cross()
            return
        self._hover_i = i
        self._draw_cross(i)

    def _draw_cross(self, i):
        g = self._geo
        c = self.canvas
        c.delete("cross")
        view, start = g["view"], g["start"]
        b = view[i]
        x = g["pl"] + (i + 0.5) * g["bw"]
        a = self._disp_ma()

        def y_of(p):
            return g["pt"] + (g["pmax"] - p) / (g["pmax"] - g["pmin"]) * (g["p_bottom"] - g["pt"])

        y = y_of(b["close"])
        c.create_line(x, g["pt"], x, g["h"] - g["pb"], fill="#b9bdc4", dash=(4, 3), tags="cross")
        c.create_line(g["pl"], y, g["pl"] + g["plot_w"], y, fill="#b9bdc4", dash=(4, 3), tags="cross")

        prev = view[i - 1]["close"] if i > 0 else b["open"]
        chg = (b["close"] - prev) / prev * 100
        idx = start + i
        m5 = a["ma5"][idx]
        m20 = a["ma20"][idx]
        m60 = a["ma60"][idx]
        lines = [
            "{}".format(b["date"]),
            "开 {:.2f}　收 {:.2f}".format(b["open"], b["close"]),
            "高 {:.2f}　低 {:.2f}".format(b["high"], b["low"]),
            "涨跌 {}{:.2f}%".format("+" if chg >= 0 else "", chg),
            ("量 {:.0f} 手".format(b["vol"]) if self.view_bars
             else "量 {:.0f} 万手".format(b["vol"] / 10000)),
            "MA5 {}  MA20 {}  MA60 {}".format(
                "—" if m5 is None else "{:.2f}".format(m5),
                "—" if m20 is None else "{:.2f}".format(m20),
                "—" if m60 is None else "{:.2f}".format(m60)),
        ]
        hit = [s for s in a["buys"] + a["sells"] if s["i"] == idx]
        if hit:
            lines.append(("▲ 买入信号　" if hit[0] in a["buys"] else "▼ 卖出信号　") + hit[0]["text"])

        tw, th = 210, 18 * len(lines) + 12
        tx = x + 14 if x + 14 + tw < g["pl"] + g["plot_w"] else x - 14 - tw
        ty = min(max(g["pt"] + 8, 8), g["h"] - g["pb"] - th - 8)
        c.create_rectangle(tx, ty, tx + tw, ty + th, fill="#ffffff", outline="#d6d9de", tags="cross")
        for k, line in enumerate(lines):
            color = MUTED if k == 0 else TEXT
            c.create_text(tx + 10, ty + 8 + k * 18, text=line, anchor="nw",
                          fill=color, font=FONT_S, tags="cross")

        c.create_text(g["pl"] - 8, y, text="{:.2f}".format(b["close"]), anchor="e",
                      fill=TEXT, font=FONT_S, tags="cross")

    # ---- 交互 ----
    def _on_pick(self, event):
        sel = self.listbox.curselection()
        if not sel:
            return
        code, name = self.watch[sel[0]]
        if code == self.code and self.bars:
            return
        self.code, self.name = code, name
        self.secid = None
        self.entry_code.delete(0, "end")
        self.entry_code.insert(0, code)
        self._load()

    def _add_watch(self, code=None):
        code = (code or self.entry_add.get()).strip()
        if not code or not code.isdigit() or len(code) != 6:
            self.lbl_status.configure(text="加自选要输 6 位数字代码", fg=UP)
            log("加自选失败（不是 6 位代码）：" + code)
            return
        if any(c == code for c, _ in self.watch):
            self.lbl_status.configure(text="{} 已经在自选股里了".format(code), fg=MUTED)
            return
        # 先无条件加进自选（不依赖网络），名字先用代码顶着，随后后台补名字
        self.entry_add.delete(0, "end")
        self.watch.append([code, code])
        save_watch(self.watch)
        self._fill_list()
        log("加入自选：" + code)
        self.lbl_status.configure(text="已加入 {}，正在查名字……".format(code), fg=MUTED)

        def work():
            try:
                name, _bars = fetch_kline(code, count=5)
                self.q.put(("rename", code, name, ""))
            except Exception as e:          # noqa: BLE001
                log("补名字失败 {}：{}".format(code, e))
                self.q.put(("rename", code, "", ""))

        threading.Thread(target=work, daemon=True).start()
        # 顺便把这只打开看看
        self.code, self.secid = code, None
        self.entry_code.delete(0, "end")
        self.entry_code.insert(0, code)
        self._load()

    def _remove_watch(self):
        """把自选股里选中的那只删掉。"""
        sel = self.listbox.curselection()
        if not sel:
            self.lbl_status.configure(text="先在左列表里点一只，再删", fg=MUTED)
            return
        code, name = self.watch[sel[0]]
        del self.watch[sel[0]]
        save_watch(self.watch)
        self._fill_list()
        log("删除自选：" + code)
        self.lbl_status.configure(text="已从自选股删除 {} {}".format(code, name), fg=MUTED)

    def _focus_search(self):
        self.entry_search.focus_set()
        self.entry_search.selection_range(0, "end")
        self._say("输名字 / 拼音 / 6 位代码，回车")

    def _on_search_top(self):
        """顶栏那个搜索框：转到同一个搜索流程。"""
        kw = self.entry_top.get().strip()
        if not kw:
            self._focus_search()
            return
        self.entry_top.delete(0, "end")
        self.entry_search.delete(0, "end")
        self.entry_search.insert(0, kw)
        self._on_search()


def main():
    log("—— 启动 股市助手（带搜索版）——")
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
