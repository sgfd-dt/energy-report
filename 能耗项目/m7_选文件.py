import json, os, requests
KEY = open(r"D:\ai的文件\agent入门\key.txt", encoding="utf-8").read().strip()
FILES = {"报告.txt": "4 台设备的正常数据", "报告_更坏.txt": "只剩 1 台设备的坏数据"}
question = input("请输入一个问题（这里不敲命令；输 q 或回车退出）：").strip()
if question in ("q", ""):
    print("已退出")
    raise SystemExit
SYSTEM = '只从这两个文件里选一个，只输出 JSON：{"file": "文件名"}。可选文件：' + json.dumps(FILES, ensure_ascii=False)
payload = {"model": "deepseek-chat",
           "messages": [{"role": "system", "content": SYSTEM},
                        {"role": "user", "content": question}],
           "temperature": 0}
r = requests.post("https://api.deepseek.com/chat/completions",
                  headers={"Authorization": "Bearer " + KEY}, json=payload, timeout=60)
choice = r.json()["choices"][0]["message"]["content"].strip()
print("它选了：", choice)
if choice.startswith("{"):
    choice = json.loads(choice)["file"]
    print("（它带了 JSON 外壳，我拆掉后的文件名是：", choice, "）")
path = os.path.join(r"D:\ai的文件\python练习\能耗项目", choice)
text = open(path, encoding="utf-8").read()
payload2 = {"model": "deepseek-chat",
            "messages": [{"role": "system", "content": "你是能源工程师，回答不超过 20 字，只根据我给的数据说话"},
                         {"role": "user", "content": question + "\n" + text}],
            "temperature": 0}
r2 = requests.post("https://api.deepseek.com/chat/completions",
                   headers={"Authorization": "Bearer " + KEY}, json=payload2, timeout=60)
print("答案：", r2.json()["choices"][0]["message"]["content"])
question = input("问一句（q 退出）：").strip()
if question in ("q", ""):
    print("已退出")
    raise SystemExit