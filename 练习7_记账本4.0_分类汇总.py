"""练习7：记账本 4.0 —— 按分类汇总

练习6 解决了「以后不再产生脏分类」，但这个练习要解决的是：
以后你不再需要手动去数，让程序自己算。

新学的一件事：用字典做累加。
    totals = {}                       # 空字典
    totals[cat] = totals.get(cat, 0) + amount
get(cat, 0) 的意思是：有就取出来，没有就给个 0——这样第一次遇到某个分类也不会报 KeyError。
这一行是所有「计数、求和、排行榜」的核心写法，以后写统计十个有八个长这样。

和练习6 比，只加了一处（标了 【改】）：菜单多一个 5，配一个 summary() 函数。
"""

import json
import os

FILE = "账本.json"

CATEGORIES = {
    "1": "吃饭",
    "2": "交通",
    "3": "学习",
    "4": "其他",
}


def load():
    if not os.path.exists(FILE):
        print("没找到账本文件，新建一个空账本")
        return []
    try:
        with open(FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print("账本文件坏了（不是合法 JSON），先当空账本用")
        return []


def save(records):
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def show(records):
    if not records:
        print("账本还是空的")
        return
    for i, r in enumerate(records, start=1):
        note = r[0]
        amount = r[1]
        category = r[2] if len(r) > 2 else "未分类"
        print(f"{i}. [{category}] {note}  {amount:.2f} 元")


def summary(records):
    """【改】按分类汇总：金额从大到小排，并给出占比。"""
    if not records:
        print("账本还是空的")
        return

    totals = {}          # 分类 -> 总金额
    counts = {}          # 分类 -> 笔数
    for r in records:
        category = r[2] if len(r) > 2 else "未分类"
        amount = r[1]
        # 核心写法：有这个分类就累加，没有就从 0 开始
        totals[category] = totals.get(category, 0) + amount
        counts[category] = counts.get(category, 0) + 1

    grand = sum(totals.values())

    print("\n----- 分类汇总 -----")
    # sorted 的 key 传一个函数，表示「按什么排序」；reverse=True 表示从大到小
    for category in sorted(totals, key=lambda c: totals[c], reverse=True):
        money = totals[category]
        percent = money / grand * 100
        bar = "█" * int(percent / 5)          # 每 5% 画一个方块，凑个简易条形图
        print(f"{category:<6} {counts[category]:>2} 笔  {money:>8.2f} 元  {percent:>5.1f}%  {bar}")
    print(f"{'合计':<6} {len(records):>2} 笔  {grand:>8.2f} 元")


def ask_category():
    print("分类：1 吃饭   2 交通   3 学习   4 其他")
    while True:
        key = input("输入分类编号：").strip()
        if key in CATEGORIES:
            return CATEGORIES[key]
        print("只能输入 1/2/3/4，再试一次")


def main():
    records = load()
    print(f"打开账本，已有 {len(records)} 笔记录")

    while True:
        print("\n===== 我的账本 4.0 =====")
        print("1 记一笔    2 看全部    3 看总额    4 删最后一笔    5 分类汇总    0 退出")
        choice = input("选一个数字：").strip()

        if choice == "1":
            note = input("这笔花在哪：").strip()
            amount_text = input("多少钱：").strip()
            try:
                amount = float(amount_text)
            except ValueError:
                print("金额必须是数字，这笔没记上")
                continue
            category = ask_category()
            records.append([note, amount, category])
            save(records)
            print(f"已记下并保存：[{category}] {note} {amount:.2f} 元")

        elif choice == "2":
            show(records)

        elif choice == "3":
            total = sum(r[1] for r in records)
            print(f"一共花了 {total:.2f} 元")

        elif choice == "4":
            if not records:
                print("账本是空的，没得删")
            else:
                gone = records.pop()
                save(records)
                print(f"已删除最后一笔：{gone[0]} {gone[1]:.2f} 元")

        elif choice == "5":
            summary(records)

        elif choice == "0":
            print(f"记账本已关闭，记录已保存在 {FILE}")
            break

        else:
            print("没有这个选项，请输入 0-5")


main()
