print("=== ① ===")
try:
    print("1")
    y = float("三")
    print("2")
except ValueError:
    print("3")
print("4")

print("=== ② ===")
skipped = 5
skipped += 1
skipped += 1
print(f"跳过 {skipped} 行")

print("=== ③ ===")
rows = [["表头","设备","电量"], ["1","泵A"], ["2","泵B","30"]]
total = 0
for r in rows[1:]:
    try:
        total += float(r[2])
    except IndexError:
        print("少一列:", r[1])
print(total)