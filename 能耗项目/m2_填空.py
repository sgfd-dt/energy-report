# m2_填空.py —— 只补 6 个空，其余不用改
# 规则：每个空允许翻 Python速查表.md / 每日符号卡.md；不许打开 m2_汇总.py
# 判分：跑出 4 行设备占比 + 合计 2056.3 度 就算通过

import csv

with open("能耗示例.csv", encoding="utf-8") as f:
    rows = list(csv.reader(f))

d = {}
for r in rows[1:]:
    
    

    # ② 用设备名当钥匙，查这台设备之前累计多少（没有就当 0），加上 num，写回字典
    #    提示：查字典用 d.get(钥匙, 0)；赋值是 d[钥匙] = 值
    d[r[1]] = d.get(r[1],0) +float(r[2])
print(d)

# ③ 把字典变成 (设备, 电量) 对的列表，并按电量从大到小排
#    提示：d.items() 变形；sorted(..., key=lambda x: x[1], reverse=True)

# ④ 把字典里所有值加起来，得到总电量
#    提示：sum(...) + d.values()
total = sum(d.values())
items=sorted(d.items(), key=lambda x:x[1], reverse=True)
for name, val in items:
    
     
    print(name,val, "{:.1f}%".format(val/total*100))


# ⑥ 循环外：打印合计（电量保留 1 位小数）
#    提示：round(total, 1)
print("合计", round(total,1),"度")

# ===== 答案（写不出来再看，看完关掉重来一遍）=====
# ① num = float(r[2])
# ② d[r[1]] = d.get(r[1], 0) + num
# ③ items = sorted(d.items(), key=lambda x: x[1], reverse=True)
# ④ total = sum(d.values())
# ⑤ print(name, val, "{:.1f}%".format(val / total * 100))
# ⑥ print("合计", round(total, 1), "度")
