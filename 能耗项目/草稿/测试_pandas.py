import pandas as pd

df = pd.read_csv("能耗示例.csv")
s = df.groupby("设备")["电量kWh"].sum()

print("--- Q1 ---")
print("shape[0]:", df.shape[0])
print("shape[1]:", df.shape[1])

print("--- Q2 ---")
print("len(s):", len(s))
print("s.sum():", s.sum())

print("--- Q3 ---")
print("运行小时总和:", df["运行小时"].sum())

print("--- Q4 ---")
for name, val in s.items():
    print(name, val)