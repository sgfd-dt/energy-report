def f():
    print("这句话只是显示")
    return 5

x = f()
print("x 等于", x)

def g():
    print("我只有 print，没有 return")

y = g()
print("y 等于", y)