import json
import requests

# ---- 1. 准备好料：钥匙 + 报告 ----
KEY = open(r"D:\ai的文件\agent入门\key.txt", encoding="utf-8").read().strip()
REPORT = open(r"D:\ai的文件\python练习\能耗项目\报告.txt", encoding="utf-8").read()

URL = "https://api.deepseek.com/chat/completions"
HEADERS = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}

# ---- 2. 定义工具：每个工具就是一个普通函数 ----
def read_report(arg):
    """把报告全文交出去。arg 没用，但要接住。"""
    return REPORT

def share_of(arg):
    """在报告里找这台设备那一行（带百分比），找不到就说没找到。"""
    for line in REPORT.splitlines():
        if arg in line and "%" in line:
            return line.strip()
    return "报告里没有这台设备：" + arg

def parse_report():
    """把 '设备名  1028.00 度  50.0%' 这样的行拆成 {设备名: (电量, 占比)}"""
    data = {}
    for line in REPORT.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[-1].endswith("%"):
            try:
                data[parts[0]] = (float(parts[1]), float(parts[-1].rstrip("%")))
            except ValueError:
                pass
    return data

def sum_of(arg):
    """把几台设备加在一起。arg 传设备名，多个用 + 连，例如 空压机A+冷却塔B。
    关键：加法由这段代码做，模型只负责把结果说成人话。"""
    names = [n.strip() for n in str(arg).replace("，", "+").replace(",", "+").split("+") if n.strip()]
    data = parse_report()
    total = sum(v[0] for v in data.values())
    kwh = 0.0
    pct = 0.0
    missing = []
    for n in names:
        if n in data:
            kwh += data[n][0]
            pct += data[n][1]
        else:
            missing.append(n)
    if missing:
        return "报告里没有这些设备：" + "、".join(missing)
    return f"{' + '.join(names)} = {kwh:.2f} 度，合计占 {pct:.1f}%（全厂 {total:.2f} 度）"

TOOLS = {"read_report": read_report, "share_of": share_of, "sum_of": sum_of}

# ---- 3. 告诉模型它能用哪些工具、必须怎么回话 ----
SYSTEM = """你是工具调度员，只能输出 JSON，不要输出任何别的字。
可用工具：
- read_report：读能耗报告全文，arg 传空字符串
- share_of：查某台设备的电量与占比，arg 传设备名
- sum_of：把几台设备加在一起（给电量和占比），arg 传设备名，多个用 + 连接，例如 空压机A+冷却塔B
- finish：结束并给出最终回答，arg 传你的结论
铁律：只要涉及加法、合计、几个数相加，必须调用 sum_of，不许自己算。
输出格式：{"tool": "工具名", "arg": "参数"}"""

def ask(question):
    print("问题：", question)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question},
    ]
    # ---- 4. 循环：它要工具 → 我们执行 → 把结果还给它 → 再问 ----
    for rnd in range(1, 5):
        payload = {"model": "deepseek-chat", "messages": messages, "temperature": 0}
        r = requests.post(URL, headers=HEADERS, json=payload, timeout=60)
        text = r.json()["choices"][0]["message"]["content"].strip()
        print(f"  第{rnd}轮 → 它说：{text}")

        try:
            cmd = json.loads(text)
        except Exception:
            print("  （不是 JSON，直接当成答案）")
            return text

        tool = cmd.get("tool", "")
        arg = cmd.get("arg", "")

        if tool == "finish":
            return arg
        if tool not in TOOLS:
            return "它要了一个不存在的工具：" + str(tool)

        result = TOOLS[tool](arg)
        print(f"      执行 {tool}({arg!r}) → 结果前 60 字：{result[:60]!r}")

        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": "工具执行结果：" + result})

    # ---- 5. 轮次用完还没收尾，强制要一句话结论（防死循环）----
    print("  （轮次用完，强制要结论）")
    messages.append({"role": "user", "content": "工具轮次用完了，请直接给结论，只输出一句话。"})
    payload = {"model": "deepseek-chat", "messages": messages, "temperature": 0}
    r = requests.post(URL, headers=HEADERS, json=payload, timeout=60)
    return r.json()["choices"][0]["message"]["content"]

# ---- 6. 交互入口 ----
while True:
    question = input("请输入一个问题（这里不敲命令；输 q 或回车退出）：").strip()
    if question in ("q", ""):
        print("已退出")
        break
    answer = ask(question)
    print("最终回答：", answer)
    print("-" * 40)
