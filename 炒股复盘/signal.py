# -*- coding: utf-8 -*-
"""
========================================================
  规则提醒器  v1.0
  它会把「规则今天有没有触发」和「这条规则过去两年赚不赚钱」
  一起摆在你面前。
========================================================

它不预测涨跌。它做三件事：
  1. 用一套写死的、公开的规则（MA20 上穿/下穿）扫你的自选股
  2. 每条提示都写清「因为哪个数字触发了哪条规则」
  3. 同时把这条规则在这只股票过去两年的胜率算给你看

用法：
    python signal.py            菜单
    python signal.py today      今日体检（最常用）
    python signal.py backtest 600519   单独体检一条规则
    python signal.py watch      看自选股
    python signal.py add 600519 加自选

数据来源：东方财富公开日 K 线接口（前复权），需要联网。
"""

import csv
import json
import os
import sys
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WATCH_FILE = os.path.join(BASE_DIR, "自选股.csv")
WATCH_HEADER = ["代码", "名称"]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


# ---------------- 一、自选股 ----------------

def load_watch():
    if not os.path.exists(WATCH_FILE):
        # 第一次运行，给几只不同行业的股票当例子
        rows = [
            ["600519", "贵州茅台"],
            ["600900", "长江电力"],
            ["000001", "平安银行"],
            ["300750", "宁德时代"],
        ]
        save_watch(rows)
        return rows
    rows = []
    with open(WATCH_FILE, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("代码"):
                rows.append([row["代码"].strip(), row.get("名称", "").strip()])
    return rows


def save_watch(rows):
    with open(WATCH_FILE, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(WATCH_HEADER)
        for r in rows:
            w.writerow(r)


# ---------------- 二、取数据（东方财富公开接口）----------------

def market_of(code):
    """沪市代码以 6 开头（含 688），其余当深市。"""
    return "1" if code.startswith("6") else "0"


def fetch_kline(code, count=500):
    """取日 K 线（前复权）。返回 list，每项是字典：日期/开/收/高/低/量。"""
    secid = market_of(code) + "." + code
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        "?secid=" + secid +
        "&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57"
        "&klt=101&fqt=1&end=20500101&lmt=" + str(count)
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    data = json.loads(raw)
    block = data.get("data")
    if not block or not block.get("klines"):
        return [], ""
    name = block.get("name", "")
    bars = []
    for line in block["klines"]:
        p = line.split(",")
        if len(p) < 6:
            continue
        bars.append({
            "日期": p[0],
            "开": float(p[1]),
            "收": float(p[2]),
            "高": float(p[3]),
            "低": float(p[4]),
            "量": float(p[5]),
        })
    return bars, name


# ---------------- 三、指标（只用收盘价，简单可检验）----------------

def ma(bars, n, idx):
    """第 idx 根 K 线（含）往前 n 根的收盘均价；不够 n 根返回 None。"""
    if idx + 1 < n:
        return None
    total = 0.0
    for k in range(idx - n + 1, idx + 1):
        total = total + bars[k]["收"]
    return total / n


def pct(a, b):
    """a 相对 b 的百分比（b 是基准）。"""
    if b == 0:
        return 0.0
    return (a - b) / b * 100


# ---------------- 四、规则引擎：四条规则，全部写死公开 ----------------
# R1 趋势过滤：收盘 > MA20 > MA60 才允许考虑买
# R2 入场：昨天的收盘在 MA20 下方、今天的收盘在 MA20 上方（上穿）
# R3 离场：昨天的收盘在 MA20 上方、今天的收盘在 MA20 下方（下穿）
# R4 风险提示：收盘偏离 MA20 超过 8%（追高），或跌破 MA60（趋势坏了）

def cross_up(closes, mas, i):
    return closes[i - 1] <= mas[i - 1] and closes[i] > mas[i]


def cross_down(closes, mas, i):
    return closes[i - 1] >= mas[i - 1] and closes[i] < mas[i]


def build_series(bars):
    closes = [b["收"] for b in bars]
    ma20 = [ma(bars, 20, i) for i in range(len(bars))]
    ma60 = [ma(bars, 60, i) for i in range(len(bars))]
    return closes, ma20, ma60


def today_signals(bars):
    """只看最后一根 K 线，返回 (信号列表, 概况字典)。"""
    closes, ma20, ma60 = build_series(bars)
    i = len(bars) - 1
    if i < 61 or ma20[i] is None or ma60[i] is None:
        return [], {}

    last = bars[i]
    c = closes[i]
    m20 = ma20[i]
    m60 = ma60[i]

    if c > m20 > m60:
        trend = "多头排列"
    elif c < m20 < m60:
        trend = "空头排列"
    else:
        trend = "纠缠（方向不明）"

    sigs = []

    if cross_up(closes, ma20, i):
        sigs.append((
            "【入场信号】上穿 MA20",
            "昨天收盘 %.2f 在 MA20（%.2f）下方，今天收盘 %.2f 站上去了 → 触发规则 R2。"
            % (closes[i - 1], ma20[i - 1], c)
            + ("\n      趋势过滤 R1：" + trend + "，"
               + ("符合（多头排列）" if trend == "多头排列" else "不符合，这条信号要打折看")),
        ))

    if cross_down(closes, ma20, i):
        sigs.append((
            "【离场信号】跌破 MA20",
            "昨天收盘 %.2f 在 MA20（%.2f）上方，今天收盘 %.2f 掉下来了 → 触发规则 R3。"
            % (closes[i - 1], ma20[i - 1], c),
        ))

    if cross_down(closes, ma60, i):
        sigs.append((
            "【离场信号】跌破 MA60",
            "今天收盘 %.2f 跌破 MA60（%.2f），中期趋势由涨转跌 → 触发规则 R4。"
            % (c, m60),
        ))

    dev = pct(c, m20)
    if dev > 8:
        sigs.append((
            "【风险提示】追高",
            "收盘价已经比 MA20 高出 %.1f%%，短期涨得太快 → 触发规则 R4，此时入场容易买在短线高点。"
            % dev,
        ))

    if i >= 20:
        high20 = max(b["高"] for b in bars[i - 19:i + 1])
        if last["高"] >= high20 - 0.001:
            sigs.append((
                "【提示】站上 20 日最高",
                "今天的最高价 %.2f 就是过去 20 个交易日的最高价 → 突破前高，但突破本身不等于会继续涨。"
                % last["高"],
            ))

    info = {
        "收盘": c,
        "涨跌": pct(c, closes[i - 1]),
        "MA20": m20,
        "MA60": m60,
        "趋势": trend,
        "偏离MA20": dev,
        "日期": last["日期"],
    }
    return sigs, info


# ---------------- 五、规则体检：同一套规则，过去两年到底赚不赚 ----------------

def backtest(bars):
    """按 R2 买入、R3 卖出，逐笔记录。返回统计字典。"""
    closes, ma20, ma60 = build_series(bars)
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    trades = []
    holding = False
    buy_price = 0.0
    buy_date = ""

    for i in range(62, len(bars)):
        if ma20[i] is None:
            continue
        if not holding and cross_up(closes, ma20, i):
            holding = True
            buy_price = closes[i]
            buy_date = bars[i]["日期"]
        elif holding and cross_down(closes, ma20, i):
            ret = (closes[i] - buy_price) / buy_price
            trades.append({
                "买": buy_date, "买价": buy_price,
                "卖": bars[i]["日期"], "卖价": closes[i],
                "收益": ret * 100,
            })
            equity = equity * (1 + ret)
            if equity > peak:
                peak = equity
            if peak - equity > max_dd:
                max_dd = peak - equity
            holding = False

    total_ret = (equity - 1) * 100
    first = closes[62]
    last = closes[-1]
    hold_ret = (last - first) / first * 100

    wins = [t for t in trades if t["收益"] > 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0
    gain = sum(t["收益"] for t in trades if t["收益"] > 0)
    loss = abs(sum(t["收益"] for t in trades if t["收益"] < 0))
    pf = gain / loss if loss > 0 else 0.0

    return {
        "笔数": len(trades),
        "胜率": win_rate,
        "盈亏比": pf,
        "规则收益": total_ret,
        "持有收益": hold_ret,
        "最大回撤": max_dd * 100,
        "交易": trades,
        "区间": bars[62]["日期"] + " ~ " + bars[-1]["日期"],
    }


def render_signal_block(code, name, bars):
    """把一只股票的信号 + 体检结果排成一段文字。"""
    sigs, info = today_signals(bars)
    if not info:
        return "  " + name + " " + code + "：数据不足（少于 62 根 K 线），无法判断。"
    bt = backtest(bars)

    lines = []
    lines.append("  " + name + " " + code + "   " + info["日期"])
    lines.append("    收盘 %.2f（%+.2f%%）  MA20 %.2f（偏离 %+.1f%%）  MA60 %.2f"
                 % (info["收盘"], info["涨跌"], info["MA20"], info["偏离MA20"], info["MA60"]))
    lines.append("    趋势：" + info["趋势"])

    if not sigs:
        lines.append("    今日触发：无。规则没话可说——这本身就是一种结论，别硬找理由。")
    for title, reason in sigs:
        lines.append("    " + title)
        lines.append("      原因：" + reason)

    lines.append("    规则体检（%s，%d 笔）：胜率 %.1f%%，盈亏比 %.2f，规则收益 %+.1f%%，"
                 "同期买入不动 %+.1f%%，最大回撤 %.1f%%"
                 % (bt["区间"], bt["笔数"], bt["胜率"], bt["盈亏比"],
                    bt["规则收益"], bt["持有收益"], bt["最大回撤"]))
    if bt["规则收益"] < bt["持有收益"]:
        lines.append("      ⚠ 同一段时间里，这条规则跑输「买入后什么都不做」%.1f 个百分点。"
                     % (bt["持有收益"] - bt["规则收益"]))
    lines.append("")
    return "\n".join(lines)


# ---------------- 六、命令 ----------------

def cmd_today():
    watch = load_watch()
    print()
    print("=" * 66)
    print("  今日体检  规则：MA20 上穿买 / 下穿卖，MA20>MA60 才算多头")
    print("  下面全是「规则触发 + 具体数字」，不是建议，我不替你决定。")
    print("=" * 66)
    print()
    for code, name in watch:
        try:
            bars, real_name = fetch_kline(code)
            if not bars:
                print("  " + name + " " + code + "：没取到数据（代码对不对？）")
                continue
            print(render_signal_block(code, real_name or name, bars))
        except Exception as e:
            print("  " + name + " " + code + "：取数据失败 —— " + str(e))
    print("=" * 66)
    print("  记住：规则体检里的胜率是「过去」，不是「以后」。")
    print("=" * 66)
    print()


def cmd_backtest(code):
    try:
        bars, name = fetch_kline(code)
    except Exception as e:
        print("  取数据失败：" + str(e))
        return
    if not bars:
        print("  没取到 " + code + " 的数据，检查一下代码。")
        return
    bt = backtest(bars)
    print()
    print("=" * 60)
    print("  规则体检：" + name + " " + code)
    print("  区间 " + bt["区间"] + "（前复权日线）")
    print("=" * 60)
    print("  交易笔数      %d" % bt["笔数"])
    print("  胜率          %.1f%%" % bt["胜率"])
    print("  盈亏比        %.2f" % bt["盈亏比"])
    print("  规则累计收益  %+.1f%%" % bt["规则收益"])
    print("  同期买入不动  %+.1f%%" % bt["持有收益"])
    print("  规则最大回撤  %.1f%%" % bt["最大回撤"])
    print("-" * 60)
    print("  最近 10 笔：")
    for t in bt["交易"][-10:]:
        print("    %s 买 %.2f  →  %s 卖 %.2f   %+5.1f%%"
              % (t["买"], t["买价"], t["卖"], t["卖价"], t["收益"]))
    print("=" * 60)
    print("  这张表的意义：让你在相信一条规则之前，先看见它的全部历史。")
    print()


def cmd_watch():
    watch = load_watch()
    print()
    print("  自选股（%d 只）：" % len(watch))
    for code, name in watch:
        print("    " + code + "  " + name)
    print()
    print("  加：python signal.py add 600519          （会自动补名称）")
    print("  删：直接编辑 自选股.csv")
    print()


def cmd_add(code):
    bars, name = fetch_kline(code, count=5)
    if not bars:
        print("  " + code + " 取不到数据，代码可能不对。")
        return
    watch = load_watch()
    for c, _ in watch:
        if c == code:
            print("  " + code + " 已经在自选股里了。")
            return
    watch.append([code, name])
    save_watch(watch)
    print("  ✓ 已加入自选股：" + code + " " + name)


MENU = """
========================================================
            规则提醒器  v1.0
  规则写死公开，触发就告诉你；同时告诉你它有多不靠谱
========================================================
  1  今日体检（看自选股今天触发了什么）
  2  单独体检一条规则（输入代码，如 600519）
  3  看自选股
  4  加自选股（输入代码）
  0  退出
--------------------------------------------------------
"""


def menu():
    while True:
        print(MENU)
        try:
            choice = input("选择：").strip()
        except EOFError:
            break
        if choice == "0":
            break
        elif choice == "1":
            cmd_today()
        elif choice == "2":
            cmd_backtest(input("股票代码：").strip())
        elif choice == "3":
            cmd_watch()
        elif choice == "4":
            cmd_add(input("股票代码：").strip())
        else:
            print("  没有这个选项。")


def main():
    if len(sys.argv) == 1:
        menu()
        return
    cmd = sys.argv[1].lower()
    if cmd == "today":
        cmd_today()
    elif cmd == "backtest" and len(sys.argv) > 2:
        cmd_backtest(sys.argv[2])
    elif cmd == "watch":
        cmd_watch()
    elif cmd == "add" and len(sys.argv) > 2:
        cmd_add(sys.argv[2])
    else:
        print("用法：python signal.py [today | backtest 代码 | watch | add 代码]")


if __name__ == "__main__":
    main()
