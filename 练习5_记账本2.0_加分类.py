"""练习5：记账本 2.0 —— 给每一笔加一个分类

和练习4 比，只改了三处（都标了 【改】）：
1. 记一笔时多问一句分类
2. 存的时候每笔多一个元素
3. 看全部时把分类也打出来

注意最后一处【兼容】：旧账本里每笔只有 2 个元素，新的是 3 个。
读旧数据时不能直接写 record[2]，否则会报 IndexError。
"""

import json
import os

FILE = "账本.json"


def load():
    """读账本。文件不存在或坏掉，都从空列表开始，不让程序崩。"""
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
        # 【兼容】旧记录只有 2 个元素，取 r[2] 会报错，所以先判长度
        category = r[2] if len(r) > 2 else "未分类"
        print(f"{i}. [{category}] {note}  {amount:.2f} 元")


def main():
    records = load()
    print(f"打开账本，已有 {len(records)} 笔记录")

    while True:
        print("\n===== 我的账本 2.0 =====")
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
            category = input("什么分类（吃饭/交通/学习/其他）：").strip()
            if category == "":
                category = "其他"
            # 【改】每笔现在是 3 个元素：备注、金额、分类
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
