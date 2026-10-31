import csv
import os
import time

print("我在跑:", os.path.abspath(__file__))
print("现在时间：", time.strftime("%Y-%m-%d %H:%M:S"))

FILE ="能耗示例.csv" 
with open(FILE, encoding="utf-8") as f:
    rows = list(csv.reader(f))
print("表头：", rows[0])
print("行数:", len(rows) - 1)
for r in rows[1:6]:
    print(r)
print("一共", len(rows) - 1, "条")
    