import csv
import os
import sys
import time

print("我在跑:", os.path.abspath(__file__))
print("现在时间：", time.strftime("%Y-%m-%d %H:%M:%S"))

# 默认读 能耗示例.csv；也可以在命令行指定：python m2_汇总.py 能耗示例_坏数据.csv
if len(sys.argv) > 1:
    FILE = sys.argv[1]
else:
    FILE = "能耗示例.csv"
print("数据文件:", FILE)

with open(FILE, encoding="utf-8") as f:
    rows = list(csv.reader(f))

d = {}
for r in rows[1:]:
    if r[2].strip() == "":          # ① 电量是空的就跳过
        print("跳过一行空电量:", r)
        continue
    name = r[1].strip()             # ② 设备名去掉前后空格
    d[name] = d.get(name, 0) + float(r[2])

print(d)
total = sum(d.values())
items = sorted(d.items(), key=lambda x: x[1], reverse=True)

def line(name, value, total):
    print(name, value, "{:.1f}%".format(value / total * 100))

for name, val in items:
    line(name, val,total)
print("合计", round(total, 1), "度")
def find(name):
    return d.get(name)


def ask():
 while True:
        name = input("查哪台设备?").strip()
        if name in("q",""):
            break   
        num = find(name)
        if num is None:
            print("没有找到设备:", name)
            print("设备:",",".join(d.keys()))
        else:
            print(name, num, "{:.1f}%".format(num / total * 100))
ask()
