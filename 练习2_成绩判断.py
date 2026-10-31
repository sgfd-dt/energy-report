# 练习 2：input + if 判断
# 前提：hello.py 已经跑通过，再来跑这个。
# 运行方式：按右上角 ▷

score = int(input("输入一门课的成绩（0-100）："))

if score < 0 or score > 100:
    print("成绩超出范围，请输入 0-100 之间的成绩")
elif score >= 85:
    print("优秀")
elif score >= 75:
    print("良好")
elif score >= 60:
    print("及格")
else:
    print("不及格")

print("程序结束")

# 跑通之后，自己改三个地方，每次改完都重新运行：
# 1) 把 90 改成 85，试试输入 88 看结果怎么变
# 2) 再加一个 elif score >= 75: print("良好")，想想应该放在第几个位置
# 3) 输入 101 或 -5，看看程序会不会提醒你——不会的话，想想怎么加一行检查