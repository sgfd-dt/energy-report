import csv
import os
import sys
import time

print("我在跑:", os.path.abspath(__file__))
print("现在时间：", time.strftime("%Y-%m-%d %H:%M:%S"))

# 默认读 能耗示例.csv；也可以在命令行指定：python m2_汇总.py 能耗示例_更坏数据.csv
if len(sys.argv) > 1:
    FILE = sys.argv[1]
else:
    FILE = "能耗示例.csv"
print("数据文件:", FILE)

with open(FILE, encoding="utf-8") as f:
    rows = list(csv.reader(f))

d = {}# 逐行读数据：坏行跳过，不整条崩
skipped = 0
for r in rows[1:]:
    try:
        if r[2].strip() == "":
            print("跳过一行空电量:", r)
            skipped += 1
            continue
        name = r[1].strip()
        d[name] = d.get(name, 0) + float(r[2])
    except (ValueError, IndexError):  # 两种坏数据：转不成数字 / 少一列
        print("跳过一行坏数据:", r)
        skipped += 1

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
        name = input("查哪台设备?（输 q 或直接回车退出）").strip()
        if name in ("q", ""):
            break
        num = find(name)
        if num is None:
            print("没有找到设备:", name)
            print("设备:", ",".join(d.keys()))
        else:
            print(name, num, "{:.1f}%".format(num / total * 100))

ask()

# ---- M4：把汇总写成报告 ----
print("查询结束，开始生成报告…")
with open("报告.txt", "w", encoding="utf-8") as f:# 报告格式固定，别改顺序：跳过行 → 标题 → 时间 → 表体 → 合计
   
    f.write("能耗报告\n")
    f.write("生成时间：" + time.strftime("%Y-%m-%d %H:%M") + "\n")
    f.write("─" * 30 + "\n")
    for name, val in items:
        f.write(f"{name}  {val:.2f} 度  {val / total * 100:.1f}%\n")
    f.write("─" * 30 + "\n")
    f.write(f"合计 {total:.2f} 度\n")
    f.write(f"跳过 {skipped} 行\n")
print("报告已生成：报告.txt")
