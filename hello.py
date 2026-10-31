# hello.py —— 你的第一个 Python 程序
# 运行方法：在这个文件上按 VS Code 右上角的 ▷，或终端里敲 python hello.py

name = input("你叫什么名字？")
print(f"你好，{name}！我们开始学 Python。")

print("\n下面这段是循环：1 到 5 的平方")
for i in range(1, 11):
    
    print(f"  {i} 的平方是 {i * i}")

print("\n改一改试试：把 range(1, 6) 改成 range(1, 11)，再运行一次。")