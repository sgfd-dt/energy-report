import csv
import os
import time 

print("我在跑:", os.path.abspath(__file__))
print("现在时间：", time.strftime("%Y-%m-%d %H:%M:%S")) 

import csv

with open("能耗示例.csv", encoding="utf-8") as f:
    rows = list(csv.reader(f))

d = {}
for r in rows[1:]:
    d[r[1]] = d.get(r[1], 0) + float(r[2])        
print(d)
total=sum(d.values())
print(d.items())
items=sorted(d.items(), key=lambda x:x[1], reverse=True)

print(items)
for name, valve in items:
    print(name, valve, "{:.1f}%".format(valve/total*100))
print("合计",round(total, 1),"度")