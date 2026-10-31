# 练习 3：命令行记账本 v0
# 这就是阶段一的项目「命令行记账本」的第一版：只用列表 + while 循环，先跑起来。
# 运行方式：按右上角 ▷，然后在下方终端里按菜单输入数字

records = []          # 每笔记录长这样：("早餐", 8.5)

while True:
    print("\n===== 我的账本 v0 =====")
    print("1 记一笔    2 看全部    3 看总额    4 删除最后一笔0 退出")
    choice = input("选一个数字：")

    if choice == "1":
        note = input("这笔花在哪：")
        amount = float(input("多少钱："))
        records.append((note, amount))
        print(f"已记下：{note} {amount:.2f} 元")

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
            removed_record = records.pop()
            print(f"已删除最后一笔记录：{removed_record[0]} {removed_record[1]:.2f} 元")
                                                 
    elif choice == "0":
        print("记账本已关闭")
        break    # break 跳出 while 循环，程序才会结束

    else:
        print("没有这个选项，请输入 0-4 之间的数字")

# 跑通之后，按顺序加功能，每次只加一个，加完立刻运行一次：
# 1) 加选项 4「删掉最后一笔」：用 records.pop()，记得在菜单里补上 4
# 2) 选项 1 记完之后，顺手把当前总额打印出来（复用它下面那段 for 循环的思路）
# 3) 想想：现在关掉程序，记录全没了。要让记录留下来，需要学什么？（答案：文件读写，下一题）