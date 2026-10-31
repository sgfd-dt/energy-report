# 练习 4：让账本记住东西（v0 → 1.0）
# 和前几题最大的区别：这次数据存在一个文件里，关掉程序再打开，记录还在。
# 运行方式：按右上角 ▷

import json

FILE = "账本.json"      # 账本文件就放在这个 .py 旁边

# ---------- 启动时：从文件读回来 ----------
try:
    with open(FILE, "r", encoding="utf-8") as f:
        records = json.load(f)          # json.load 把文件内容变回 Python 列表
except FileNotFoundError:
    records = []                        # 第一次运行没有这个文件，很正常，从空列表开始

# ---------- 把当前 records 写回文件 ----------
def save():
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)   # ensure_ascii=False 让中文不被转成 \u4f60

print(f"打开账本，已有 {len(records)} 笔记录")

while True:
    print("\n===== 我的账本 1.0 =====")
    print("1 记一笔    2 看全部    3 看总额    4 删最后一笔    0 退出")
    choice = input("选一个数字：")

    if choice == "1":
        note = input("这笔花在哪：")
        amount = float(input("多少钱："))
        records.append([note, amount])       # 注意这里用方括号，json 存不了元组
        save()
        print(f"已记下并保存：{note} {amount:.2f} 元")

    elif choice == "2":
        if len(records) == 0:
            print("还没有任何记录")
        else:
            for i in range(len(records)):
                note, amount = records[i]
                print(f"{i + 1}. {note}  {amount:.2f} 元")

    elif choice == "3":
        total = 0.0
        for note, amount in records:
            total = total + amount
        print(f"一共花了 {total:.2f} 元")

    elif choice == "4":
        if len(records) == 0:
            print("没有记录可以删除")
        else:
            removed = records.pop()
            save()
            print(f"已删除并保存：{removed[0]} {removed[1]:.2f} 元"

    elif choice == "0":
        print("记账本已关闭，记录已保存在 账本.json")
        break

    else:
        print("没有这个选项，请输入 0-4")

# 跑通之后，按顺序做，每做完一个立刻运行验证：
# 1) 跑一次记两笔，然后退出、重新运行 → 记录应该还在（这就是「持久化」）
# 2) 用 VS Code 打开旁边的 账本.json 看一眼，看懂它的结构（它就是一个列表）
# 3) 把 FILE 改成 "账本2.json"，再跑一次，观察会发生什么（提示：新文件、空账本）
# 4) 想一想：如果 账本.json 被你自己改坏了（比如少了一个括号），程序会怎么报错？