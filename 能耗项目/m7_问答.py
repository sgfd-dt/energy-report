import requests

KEY = open(r"D:\ai的文件\agent入门\key.txt", encoding="utf-8").read().strip()
REPORT = open(r"D:\ai的文件\python练习\能耗项目\报告.txt", encoding="utf-8").read()

def ask(question):
    payload = {"model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是能源工程师，8 字内，只用我给的数据。"},
            {"role": "user", "content": question + "\n" + REPORT}],
        "temperature": 0}
    r = requests.post("https://api.deepseek.com/chat/completions",
        headers={"Authorization": "Bearer " + KEY}, json=payload, timeout=60)
    return r.json()["choices"][0]["message"]["content"]

while True:
    q = input("问一句（q 退出）：").strip()
    if q in ("q", ""):
        break
    print(ask(q))