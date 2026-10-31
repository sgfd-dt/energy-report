# -*- coding: utf-8 -*-
"""
========================================================
  炒股复盘器  v1.0
  记录 + 统计，不预测涨跌、不推荐股票、不连券商、不下单
========================================================

它只干一件事：把你自己真实做过的交易记下来，然后算清楚
    胜率 / 盈亏比 / 期望值 / 最大回撤
并且分组告诉你：亏钱到底是「选股」的问题，还是「执行」的问题。

用法（在命令行里）：
    python journal.py            打开菜单（推荐，最省事）
    python journal.py demo       写入 8 笔样例，先看效果
    python journal.py add        命令行录入一笔
    python journal.py list       看全部记录
    python journal.py stat       出复盘报告
    python journal.py fee 10 11 1000   算这一笔的手续费
    python journal.py check      下单前的 5 个问题

数据存在同目录的 trades.csv，可以用 Excel 直接打开看。
"""

import csv
import os
import sys
from datetime import datetime

# ---------------- 路径与参数（想改费用就改这里）----------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "trades.csv")
REPORT_FILE = os.path.join(BASE_DIR, "复盘报告.txt")

COMMISSION_RATE = 0.00025   # 佣金：万分之 2.5（各家不同，可以改）
COMMISSION_MIN = 5.0        # 佣金：单笔最低 5 元
STAMP_DUTY = 0.0005         # 印花税：卖出单边 0.05%（2023-08-28 起减半）
TRANSFER_FEE = 0.00001      # 过户费：双边 万分之 0.1

# CSV 的列名（顺序不能乱，Excel 里看着也顺眼）
HEADER = [
    "平仓日期", "代码", "名称", "买入日期", "买入价", "卖出价", "股数",
    "理由", "守纪律", "备注", "手续费", "盈亏", "收益率",
]

# 买入理由的分类：复盘时最有价值的分析维度
REASONS = [
    "1 消息/群里听说",
    "2 技术形态",
    "3 基本面",
    "4 情绪冲动",
    "5 朋友推荐",
    "6 其他",
]


# ---------------- 一、费用计算（A 股真实规则）----------------

def buy_fee(amount):
    """买入要交的钱：佣金 + 过户费。买入不收印花税。"""
    return max(amount * COMMISSION_RATE, COMMISSION_MIN) + amount * TRANSFER_FEE


def sell_fee(amount):
    """卖出要交的钱：佣金 + 印花税 + 过户费。"""
    return (
        max(amount * COMMISSION_RATE, COMMISSION_MIN)
        + amount * STAMP_DUTY
        + amount * TRANSFER_FEE
    )


# ---------------- 二、读写 CSV ----------------

def load_trades():
    """把 trades.csv 读成一个列表，每个元素是「一笔交易」的字典。"""
    if not os.path.exists(CSV_FILE):
        return []
    trades = []
    # utf-8-sig 是为了让 Excel 打开时中文不乱码
    with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("平仓日期"):
                continue
            trades.append(row)
    return trades


def save_trades(trades):
    """把整个列表写回 trades.csv。"""
    with open(CSV_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        for t in trades:
            writer.writerow(t)


def append_trade(trade):
    """追加一笔：先读、加进去、再整体写回（顺便保证顺序）。"""
    trades = load_trades()
    trades.append(trade)
    save_trades(trades)


# ---------------- 三、小工具 ----------------

def ask(prompt, default=""):
    """问一个问题，用户直接回车就用默认值。"""
    tip = prompt
    if default != "":
        tip = prompt + "（回车 = " + str(default) + "）"
    answer = input(tip + "：").strip()
    if answer == "":
        return str(default)
    return answer


def ask_number(prompt, default=""):
    """反复追问，直到用户输入一个能变成数字的东西。"""
    while True:
        text = ask(prompt, default)
        try:
            return float(text)
        except ValueError:
            print("    ✗ 这个不是数字，请重新输入（例如 10.5）")


def ask_choice(prompt, options):
    """让用户在几个选项里选一个，返回选项字符串。"""
    print(prompt)
    for item in options:
        print("   " + item)
    while True:
        raw = input("输入序号：").strip()
        for item in options:
            if raw and item.startswith(raw + " "):
                return item
        print("    ✗ 请输入 1 到 " + str(len(options)) + " 之间的序号")


def money(x):
    """把数字变成 1,234.56 这种好读的样子。"""
    return format(x, ",.2f")


# ---------------- 四、录入一笔交易 ----------------

def cmd_add():
    print()
    print("=" * 52)
    print("  录入一笔【已经卖出】的交易")
    print("  （没卖的先别记，卖掉了再记，这样才算得清盈亏）")
    print("=" * 52)

    code = ask("股票代码（如 600519）")
    name = ask("股票名称（如 贵州茅台）")
    buy_date = ask("买入日期（如 2026-10-08）")
    buy_price = ask_number("买入价")
    sell_date = ask("卖出日期（如 2026-10-20）", datetime.now().strftime("%Y-%m-%d"))
    sell_price = ask_number("卖出价")
    shares = ask_number("股数（A 股 1 手 = 100 股）")

    reason = ask_choice("买入理由：", REASONS)
    discipline = ask("有没有按计划止损/止盈？（y = 有，n = 没有）", "y").lower()
    note = ask("一句话备注（当时怎么想的）", "")

    # ---- 算钱 ----
    shares = int(shares)
    buy_amount = buy_price * shares
    sell_amount = sell_price * shares
    fee = buy_fee(buy_amount) + sell_fee(sell_amount)
    pnl = sell_amount - buy_amount - fee
    cost = buy_amount + buy_fee(buy_amount)
    rate = pnl / cost * 100 if cost else 0.0

    trade = {
        "平仓日期": sell_date,
        "代码": code,
        "名称": name,
        "买入日期": buy_date,
        "买入价": "%.2f" % buy_price,
        "卖出价": "%.2f" % sell_price,
        "股数": str(shares),
        "理由": reason,
        "守纪律": "有" if discipline.startswith("y") else "没有",
        "备注": note,
        "手续费": "%.2f" % fee,
        "盈亏": "%.2f" % pnl,
        "收益率": "%.2f" % rate,
    }
    append_trade(trade)

    print()
    print("  ✓ 已记入 trades.csv")
    print("    买入金额 " + money(buy_amount) + " 元，卖出金额 " + money(sell_amount) + " 元")
    print("    手续费   " + money(fee) + " 元（来回一趟约 "
          + ("%.2f" % (fee / buy_amount * 100) if buy_amount else "0") + "%）")
    mark = "赚了" if pnl >= 0 else "亏了"
    print("    这一笔   " + mark + " " + money(abs(pnl)) + " 元，收益率 "
          + ("%.2f" % rate) + "%")
    print()


# ---------------- 五、看全部记录 ----------------

def cmd_list():
    trades = load_trades()
    if not trades:
        print()
        print("  还没有记录。先运行：python journal.py demo   看看样例")
        print()
        return

    print()
    print("-" * 96)
    print("  序 平仓日期     代码      名称            股数     盈亏       收益率")
    print("-" * 96)
    total = 0.0
    for i, t in enumerate(trades, 1):
        pnl = float(t["盈亏"])
        total = total + pnl
        print("  %2d %-11s %-9s %-14s %6s %10s %9s%%"
              % (i, t["平仓日期"], t["代码"], t["名称"][:12], t["股数"],
                 money(pnl), t["收益率"]))
    print("-" * 96)
    print("  合计 %d 笔，累计盈亏 %s 元" % (len(trades), money(total)))
    print()


# ---------------- 六、复盘报告（核心）----------------

def cmd_stat():
    trades = load_trades()
    if not trades:
        print()
        print("  还没有数据，先跑 demo 或 add 几笔再来看报告。")
        print()
        return

    # 按平仓日期排序，才能算「资金曲线」和「最大回撤」
    trades_sorted = sorted(trades, key=lambda t: t["平仓日期"])

    pnls = [float(t["盈亏"]) for t in trades_sorted]
    fees = [float(t["手续费"]) for t in trades_sorted]
    n = len(pnls)
    total = sum(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    flats = [p for p in pnls if p == 0]

    win_rate = len(wins) / n * 100
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else 0.0
    expectancy = total / n

    # 最大回撤：账户从最高点跌下来最深的那一段（元）
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        equity = equity + p
        if equity > peak:
            peak = equity
        if peak - equity > max_dd:
            max_dd = peak - equity

    lines = []
    lines.append("=" * 56)
    lines.append("             炒股复盘报告")
    lines.append("             生成时间：" + datetime.now().strftime("%Y-%m-%d %H:%M"))
    lines.append("=" * 56)
    lines.append("")
    lines.append("【总览】")
    lines.append("  交易笔数        %d 笔" % n)
    lines.append("  累计盈亏        %s 元" % money(total))
    lines.append("  累计手续费      %s 元" % money(sum(fees)))
    if total != 0:
        lines.append("  手续费/盈亏     %.1f%%" % (sum(fees) / abs(total) * 100))
    lines.append("")
    lines.append("【核心四个数】")
    lines.append("  胜率        %5.1f%%   （%d 胜 / %d 负 / %d 平）"
                 % (win_rate, len(wins), len(losses), len(flats)))
    lines.append("  盈亏比      %5.2f    （平均赚 %.2f ÷ 平均亏 %.2f）"
                 % (profit_factor, avg_win, avg_loss))
    lines.append("  期望值/笔   %8s 元   （长期看这就是你的「工资」）" % money(expectancy))
    lines.append("  最大回撤    %8s 元   （最难受的时候账户缩了多少）" % money(max_dd))
    lines.append("")

    # 分组：按「买入理由」
    lines.append("【按买入理由分组：哪种钱你根本不该碰】")
    lines.append("  %-16s %5s %10s %8s" % ("理由", "笔数", "累计盈亏", "胜率"))
    for r in REASONS:
        group = [t for t in trades_sorted if t["理由"] == r]
        if not group:
            continue
        gp = sum(float(t["盈亏"]) for t in group)
        gw = len([t for t in group if float(t["盈亏"]) > 0])
        lines.append("  %-16s %5d %10s %7.1f%%"
                     % (r, len(group), money(gp), gw / len(group) * 100))
    lines.append("")

    # 分组：按「有没有守纪律」
    lines.append("【按执行分组：纪律值多少钱】")
    for label in ("有", "没有"):
        group = [t for t in trades_sorted if t.get("守纪律") == label]
        if not group:
            continue
        gp = sum(float(t["盈亏"]) for t in group)
        gw = len([t for t in group if float(t["盈亏"]) > 0])
        lines.append("  守纪律=%s：%2d 笔，累计 %9s 元，胜率 %4.1f%%"
                     % (label, len(group), money(gp), gw / len(group) * 100))
    lines.append("")

    # 自动诊断：三条最可能的问题
    diag = []
    if n < 20:
        diag.append("样本只有 %d 笔，结论还很不稳——先攒到 20 笔以上再信这些数字。" % n)
    if win_rate < 40 and profit_factor < 1.2:
        diag.append("胜率低、盈亏比也不高：问题多半在「选股/入场」，不是执行。")
    if avg_win > 0 and avg_loss > avg_win * 2:
        diag.append("平均亏的是平均赚的 %.1f 倍：止损没执行，或者死扛。" % (avg_loss / avg_win))
    bad = [t for t in trades_sorted if t.get("守纪律") == "没有"]
    if n and len(bad) / n > 0.4:
        diag.append("有 %.0f%% 的交易没按计划执行：先把纪律弄好，再谈选股。" % (len(bad) / n * 100))
    if sum(pnls) != 0 and sum(fees) / abs(sum(pnls)) > 0.3:
        diag.append("手续费占盈亏 %.0f%%：交易太频繁，摩擦成本在吃掉你。" % (sum(fees) / abs(sum(pnls)) * 100))
    if not diag:
        diag.append("暂时没发现明显问题特征，继续积累样本。")
    lines.append("【自动诊断】")
    for d in diag:
        lines.append("  · " + d)
    lines.append("")
    lines.append("=" * 56)
    lines.append("  提醒：这张表只统计「你自己」，不预测任何股票。")
    lines.append("=" * 56)

    text = "\n".join(lines)
    print()
    print(text)
    print()
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print("  ✓ 报告已保存到 " + REPORT_FILE)
    print()


# ---------------- 七、费用计算器 ----------------

def cmd_fee():
    print()
    print("=" * 52)
    print("  算一笔交易的真实成本（A 股规则）")
    print("=" * 52)
    buy_price = ask_number("买入价")
    sell_price = ask_number("卖出价")
    shares = int(ask_number("股数（1 手 = 100 股）", "100"))

    buy_amount = buy_price * shares
    sell_amount = sell_price * shares
    bf = buy_fee(buy_amount)
    sf = sell_fee(sell_amount)
    fee = bf + sf
    pnl = sell_amount - buy_amount - fee
    cost = buy_amount + bf

    print()
    print("  买入金额  %12s 元" % money(buy_amount))
    print("  卖出金额  %12s 元" % money(sell_amount))
    print("  买入费用  %12s 元（佣金 %s + 过户费 %s）"
          % (money(bf),
             money(max(buy_amount * COMMISSION_RATE, COMMISSION_MIN)),
             money(buy_amount * TRANSFER_FEE)))
    print("  卖出费用  %12s 元（佣金 %s + 印花税 %s + 过户费 %s）"
          % (money(sf),
             money(max(sell_amount * COMMISSION_RATE, COMMISSION_MIN)),
             money(sell_amount * STAMP_DUTY),
             money(sell_amount * TRANSFER_FEE)))
    print("  " + "-" * 44)
    print("  总费用    %12s 元，占本金 %.3f%%" % (money(fee), fee / cost * 100))
    print("  到手盈亏  %12s 元，收益率 %.2f%%" % (money(pnl), pnl / cost * 100))
    print()
    need = (fee / shares) / (1 - COMMISSION_RATE - STAMP_DUTY - TRANSFER_FEE)
    print("  ⚠ 这意味着：股价至少要涨 %.3f 元（约 %.2f%%）你才回本。"
          % (need, need / buy_price * 100))
    print()


# ---------------- 八、下单前的检查清单 ----------------

CHECKLIST = [
    "它靠什么赚钱？我能用一句话说清它的生意吗？（说不清 = 别买）",
    "我为什么觉得它现在便宜？这个理由是事实，还是我的感觉？",
    "如果明天跌 8%，我卖还是不卖？卖的话亏多少我能睡着？",
    "这笔钱亏光，会不会影响我下个月吃饭和交学费？",
    "这消息是谁告诉我的？那个人靠卖我这个消息赚钱吗？",
]


def cmd_check():
    print()
    print("=" * 56)
    print("  下单前，把这 5 个问题答完再点「买入」")
    print("=" * 56)
    for i, q in enumerate(CHECKLIST, 1):
        print()
        print("  %d. %s" % (i, q))
        input("     想好了按回车继续……")
    print()
    print("  如果你有 2 个以上答不上来，那这笔交易大概率是情绪，不是决策。")
    print()


# ---------------- 九、样例数据 ----------------

def cmd_demo():
    demo = [
        # 平仓日期, 代码, 名称, 买入日, 买价, 卖价, 股数, 理由, 守纪律, 备注
        ("2026-06-12", "600519", "贵州茅台", "2026-05-20", "1580.00", "1650.00", 100,
         "3 基本面", "有", "看了年报，分红稳定"),
        ("2026-06-25", "000001", "平安银行", "2026-06-18", "11.20", "10.60", 1000,
         "1 消息/群里听说", "没有", "群里说有大资金进"),
        ("2026-07-08", "300750", "宁德时代", "2026-06-30", "182.00", "196.50", 200,
         "2 技术形态", "有", "突破平台，设了止损"),
        ("2026-07-21", "601318", "中国平安", "2026-07-15", "46.80", "45.10", 500,
         "4 情绪冲动", "没有", "看别人涨得凶，追高"),
        ("2026-08-05", "600036", "招商银行", "2026-07-28", "38.20", "40.10", 400,
         "3 基本面", "有", "估值低，等修复"),
        ("2026-08-19", "002594", "比亚迪", "2026-08-11", "255.00", "238.00", 100,
         "5 朋友推荐", "没有", "同学说必涨"),
        ("2026-09-03", "600900", "长江电力", "2026-08-26", "27.50", "28.90", 800,
         "3 基本面", "有", "现金流稳，当存钱"),
        ("2026-09-17", "688981", "中芯国际", "2026-09-10", "88.00", "84.50", 200,
         "2 技术形态", "没有", "止损位破了没走"),
    ]
    trades = []
    for row in demo:
        (sell_date, code, name, buy_date, bp, sp, shares, reason, disc, note) = row
        bp = float(bp)
        sp = float(sp)
        ba = bp * shares
        sa = sp * shares
        fee = buy_fee(ba) + sell_fee(sa)
        pnl = sa - ba - fee
        cost = ba + buy_fee(ba)
        trades.append({
            "平仓日期": sell_date, "代码": code, "名称": name, "买入日期": buy_date,
            "买入价": "%.2f" % bp, "卖出价": "%.2f" % sp, "股数": str(shares),
            "理由": reason, "守纪律": disc, "备注": note,
            "手续费": "%.2f" % fee, "盈亏": "%.2f" % pnl,
            "收益率": "%.2f" % (pnl / cost * 100),
        })
    save_trades(trades)
    print()
    print("  ✓ 已写入 8 笔样例到 trades.csv（这是一份假数据，练习用的）")
    print("  接下来运行：python journal.py stat   看看复盘报告长什么样")
    print()


# ---------------- 十、菜单 & 总入口 ----------------

MENU = """
========================================================
            炒股复盘器  v1.0
  只记录、只统计：不预测涨跌，不推荐股票，不帮你下单
========================================================
  1  录入一笔已卖出的交易
  2  查看全部记录
  3  出复盘报告（核心）
  4  算一笔交易的费用
  5  下单前的检查清单
  6  写入 8 笔样例数据
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
            print("\n  再见。记住：先攒 20 笔交易，再谈「我有策略」。\n")
            break
        elif choice == "1":
            cmd_add()
        elif choice == "2":
            cmd_list()
        elif choice == "3":
            cmd_stat()
        elif choice == "4":
            cmd_fee()
        elif choice == "5":
            cmd_check()
        elif choice == "6":
            cmd_demo()
        else:
            print("\n  没有这个选项，请输 0 到 6。\n")


def main():
    if len(sys.argv) == 1:
        menu()
        return
    cmd = sys.argv[1].lower()
    if cmd == "add":
        cmd_add()
    elif cmd == "list":
        cmd_list()
    elif cmd == "stat":
        cmd_stat()
    elif cmd == "fee":
        cmd_fee()
    elif cmd == "check":
        cmd_check()
    elif cmd == "demo":
        cmd_demo()
    else:
        print("不认识的命令：" + cmd)
        print("可用：add / list / stat / fee / check / demo，或不带参数打开菜单")


if __name__ == "__main__":
    main()
