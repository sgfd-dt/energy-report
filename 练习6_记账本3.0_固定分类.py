"""练习6：记账本 3.0 —— 分类不再让人随便打字

为什么改？
练习5 里分类是自由输入的，结果你的账本里同时出现了「吃饭」和「吃饭、」——
同一个意思被记成了两个分类。数据一乱，后面的统计就全错了。

改法：把分类变成固定选项，用户只能输入 1/2/3/4，由程序翻译成分类名。
这在工程上叫「枚举」：能用固定集合，就别用自由文本。

和练习5 比，只改了两处（标了 【改】）：
1. 加了一个 CATEGORIES 字典（编号 -> 分类名）
2. 记一笔时问编号，而不是问文字

【观察点】旧数据里的「吃饭、」「未分类」不会被改掉——
历史数据就是历史数据，新代码只能决定以后怎么写，不能回头改用户已经存下的东西。
"""

import json
import os
import time

# 自查三行：每次运行先报出「我在跑哪个文件、几点跑的、数据在哪」
print("我在跑:", os.path.abspath(__file__))
print("现在时间:", time.strftime("%Y-%m-%d %H:%M:%S"))
print("数据文件:", os.path.abspath("账本.json"))

FILE = "账本.json"

# 【改】编号 -> 分类名。以后要加分类，只改这一个字典
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


def ask_category():
    """【改】问编号，返回分类名。输入不合法就重新问。"""
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
        print("\n===== 我的账本 3.0 =====")
        print("1 记一笔    2 看全部    3 看总额    4 删最后一笔    0 退出")
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

        elif choice == "0":
            print(f"记账本已关闭，记录已保存在 {FILE}")
            break

        else:
            print("没有这个选项，请输入 0-4")


main()
