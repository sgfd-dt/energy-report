import pandas as pd

df = pd.read_csv("能耗示例.csv")
print(df)
print(df.shape)
print(df.columns)
s = df.groupby("设备")["电量kWh"].sum()
print(s)
print(s.sum())
print(s.sort_values(ascending=False))