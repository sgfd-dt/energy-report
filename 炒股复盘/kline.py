# -*- coding: utf-8 -*-
"""
========================================================
  K 线图查看器  kline.py  v1.0
  双击 看K线.bat，或 python kline.py
========================================================

它做三件事：
  1. 从东方财富拉你自选股的日 K 线（前复权，要联网）
  2. 画成一张真正的 K 线图（红涨绿跌、MA5/MA20/MA60、成交量）
  3. 在图上标出规则提醒器 signal.py 的买点（▲）和卖点（▼），鼠标放上去能看到原因

生成的是一个单独的 HTML 文件，双击就能在浏览器里看：
能缩放、能拖动、鼠标悬停看每天的四个价格。
图是自带的（ECharts 已内嵌进 HTML），断网也能看。

用法：
    python kline.py            菜单（最常用）
    python kline.py 600519     直接看某只
    python kline.py 600519 120 只看最近 120 根
    python kline.py list       列出自选股
"""

import csv
import json
import os
import sys
import urllib.request
import webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WATCH_FILE = os.path.join(BASE_DIR, "自选股.csv")
ECHARTS_FILE = os.path.join(BASE_DIR, "echarts.min.js")
OUT_FILE = os.path.join(BASE_DIR, "K线图.html")

WATCH_HEADER = ["代码", "名称"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# ECharts 的备用地址：本地 echarts.min.js 不在时才用（需要联网）
ECHARTS_CDN = "https://unpkg.com/echarts@5.5.1/dist/echarts.min.js"


# ---------------- 一、自选股 ----------------

def load_watch():
    """读自选股.csv：每行『代码,名称』。没有文件就建一份默认的。"""
    if not os.path.exists(WATCH_FILE):
        rows = [
            ["600519", "贵州茅台"],
            ["600900", "长江电力"],
            ["000001", "平安银行"],
            ["300750", "宁德时代"],
        ]
        with open(WATCH_FILE, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(WATCH_HEADER)
            w.writerows(rows)
        return rows

    rows = []
    with open(WATCH_FILE, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            code = (row.get("代码") or "").strip()
            if code:
                rows.append([code, (row.get("名称") or "").strip()])
    return rows


def name_of(code, watch):
    for c, n in watch:
        if c == code:
            return n
    return ""


# ---------------- 二、取数据 ----------------

def market_of(code):
    """沪市代码以 6 开头（含 688），其余当深市。这是东财 secid 的规矩。"""
    return "1" if code.startswith("6") else "0"


def fetch_kline(code, count=500):
    """取日 K 线。返回 (名称, 列表)，每项是字典：日期/开/收/高/低/量。"""
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        "?secid=" + market_of(code) + "." + code +
        "&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57"
        "&klt=101&fqt=1&end=20500101&lmt=" + str(count)
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw = resp.read().decode("utf-8", "ignore")

    block = json.loads(raw).get("data")
    if not block or not block.get("klines"):
        raise RuntimeError("没拿到 K 线数据（代码对不对？网络通不通？）")

    name = block.get("name", "")
    bars = []
    for line in block["klines"]:
        p = line.split(",")
        bars.append({
            "date": p[0],
            "open": float(p[1]),
            "close": float(p[2]),
            "high": float(p[3]),
            "low": float(p[4]),
            "vol": float(p[5]),
        })
    return name, bars


# ---------------- 三、算均线和信号 ----------------

def moving_average(values, n):
    """简单移动平均：第 i 天 = 前 n 天（含当天）的平均；不够 n 天就是 None。"""
    out = []
    for i in range(len(values)):
        if i + 1 < n:
            out.append(None)
        else:
            out.append(sum(values[i + 1 - n:i + 1]) / n)
    return out


def find_signals(bars, ma20, ma60):
    """把 signal.py 的四条规则搬过来，找出买点和卖点。

    买点：昨天收盘在 MA20 下方、今天收盘站上 MA20（且 MA20 在 MA60 上方）
    卖点：昨天收盘在 MA20 上方、今天收盘跌破 MA20
    """
    buys, sells = [], []
    for i in range(1, len(bars)):
        c0, c1 = bars[i - 1]["close"], bars[i]["close"]
        if ma20[i] is None or ma20[i - 1] is None or ma60[i] is None:
            continue
        above = ma20[i] > ma60[i]
        if c0 < ma20[i - 1] and c1 >= ma20[i] and above:
            buys.append({
                "i": i,
                "type": "买",
                "price": bars[i]["low"],
                "text": "买入信号 {}  {}  收盘上穿 MA20（{:.2f}→{:.2f}），且 MA20>MA60".format(
                    bars[i]["date"], bars[i]["close"], ma20[i - 1], ma20[i]),
            })
        if c0 > ma20[i - 1] and c1 <= ma20[i]:
            sells.append({
                "i": i,
                "type": "卖",
                "price": bars[i]["high"],
                "text": "卖出信号 {}  {}  收盘下穿 MA20（{:.2f}→{:.2f}）".format(
                    bars[i]["date"], bars[i]["close"], ma20[i - 1], ma20[i]),
            })
    return buys, sells


# ---------------- 四、拼 HTML ----------------

HEAD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  html, body {{ margin: 0; height: 100%; background: #f7f8fa;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif; }}
  #wrap {{ display: flex; flex-direction: column; height: 100%; }}
  #head {{ padding: 10px 16px; background: #fff; border-bottom: 1px solid #e6e8eb; }}
  #head .t {{ font-size: 17px; font-weight: 700; color: #1f2328; }}
  #head .t .up {{ color: #ef232a; }}
  #head .t .down {{ color: #14b143; }}
  #head .s {{ margin-top: 4px; font-size: 12px; color: #6b7280; line-height: 1.7; }}
  #chart {{ flex: 1; }}
</style>
</head>
<body>
<div id="wrap">
  <div id="head">
    <div class="t">{head_title}</div>
    <div class="s">{head_sub}</div>
  </div>
  <div id="chart"></div>
</div>
"""

TAIL_HTML = """
<script>
{echarts}
</script>
<script>
(function () {{
  var D = {data};
  var chart = echarts.init(document.getElementById('chart'), null, {{ renderer: 'canvas' }});

  function shortDate(d) {{ return d.slice(5); }}

  var upColor = '#ef232a', downColor = '#14b143';

  var option = {{
    animation: false,
    backgroundColor: '#ffffff',
    legend: {{
      data: ['MA5', 'MA20', 'MA60'],
      top: 6, right: 16, itemWidth: 14, itemHeight: 10,
      textStyle: {{ fontSize: 12, color: '#374151' }}
    }},
    tooltip: {{
      trigger: 'axis',
      axisPointer: {{ type: 'cross' }},
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#d1d5db',
      textStyle: {{ color: '#1f2328', fontSize: 12 }},
      formatter: function (ps) {{
        var k = null, i = -1;
        for (var n = 0; n < ps.length; n++) {{
          if (ps[n].seriesName === 'K线') {{ k = ps[n]; i = ps[n].dataIndex; break; }}
        }}
        if (!k) {{
          for (var m = 0; m < ps.length; m++) {{
            if (ps[m].data && ps[m].data[2]) {{ return ps[m].data[2]; }}
          }}
          return '';
        }}
        var b = D.bars[i];
        var prev = i > 0 ? D.bars[i - 1].close : b.open;
        var chg = ((b.close - prev) / prev) * 100;
        var col = b.close >= b.open ? upColor : downColor;
        var s = '<div style="font-weight:700;margin-bottom:4px">' + b.date + '</div>';
        s += '开 ' + b.open.toFixed(2) + '　收 <b style="color:' + col + '">' + b.close.toFixed(2) + '</b>';
        s += '　高 ' + b.high.toFixed(2) + '　低 ' + b.low.toFixed(2) + '<br>';
        s += '涨跌 <b style="color:' + (chg >= 0 ? upColor : downColor) + '">' +
             (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%</b>';
        s += '　量 ' + Math.round(b.vol / 10000) + ' 万手<br>';
        s += 'MA5 ' + (D.ma5[i] === null ? '—' : D.ma5[i].toFixed(2)) +
             '　MA20 ' + (D.ma20[i] === null ? '—' : D.ma20[i].toFixed(2)) +
             '　MA60 ' + (D.ma60[i] === null ? '—' : D.ma60[i].toFixed(2));
        var hits = [];
        if (D.buyIdx[i]) hits.push('<span style="color:' + upColor + '">▲ 买入信号</span>');
        if (D.sellIdx[i]) hits.push('<span style="color:' + downColor + '">▼ 卖出信号</span>');
        if (hits.length) s += '<br>' + hits.join('　');
        return s;
      }}
    }},
    axisPointer: {{ link: [{{ xAxisIndex: 'all' }}] }},
    grid: [
      {{ left: 64, right: 24, top: 38, height: '56%' }},
      {{ left: 64, right: 24, top: '66%', bottom: 56 }}
    ],
    xAxis: [
      {{
        type: 'category', data: D.dates, boundaryGap: true,
        axisLine: {{ lineStyle: {{ color: '#c9ccd1' }} }},
        axisLabel: {{ formatter: shortDate, fontSize: 11, color: '#6b7280' }},
        splitLine: {{ show: false }},
        min: 'dataMin', max: 'dataMax'
      }},
      {{
        type: 'category', gridIndex: 1, data: D.dates, boundaryGap: true,
        axisLine: {{ lineStyle: {{ color: '#c9ccd1' }} }},
        axisLabel: {{ show: false }}, axisTick: {{ show: false }},
        splitLine: {{ show: false }},
        min: 'dataMin', max: 'dataMax'
      }}
    ],
    yAxis: [
      {{
        scale: true,
        splitArea: {{ show: true, areaStyle: {{ color: ['#ffffff', '#fafbfc'] }} }},
        axisLabel: {{ fontSize: 11, color: '#6b7280', formatter: function (v) {{ return v.toFixed(0); }} }},
        axisLine: {{ show: false }}, axisTick: {{ show: false }},
        splitLine: {{ lineStyle: {{ color: '#eff1f3' }} }}
      }},
      {{
        scale: true, gridIndex: 1, splitNumber: 2,
        axisLabel: {{ show: false }}, axisLine: {{ show: false }},
        axisTick: {{ show: false }}, splitLine: {{ show: false }}
      }}
    ],
    dataZoom: [
      {{ type: 'inside', xAxisIndex: [0, 1], start: {zoom_start}, end: 100 }},
      {{
        type: 'slider', xAxisIndex: [0, 1], start: {zoom_start}, end: 100,
        bottom: 12, height: 18,
        borderColor: '#dcdfe3', fillerColor: 'rgba(64,128,255,0.12)',
        handleStyle: {{ color: '#9aa2ad' }}, textStyle: {{ fontSize: 10, color: '#9aa2ad' }}
      }}
    ],
    series: [
      {{
        name: 'K线', type: 'candlestick', data: D.ohlc,
        itemStyle: {{ color: upColor, color0: downColor,
                     borderColor: upColor, borderColor0: downColor }}
      }},
      {{
        name: 'MA5', type: 'line', data: D.ma5, smooth: true, showSymbol: false,
        lineStyle: {{ width: 1, color: '#e6a23c' }}, itemStyle: {{ color: '#e6a23c' }}
      }},
      {{
        name: 'MA20', type: 'line', data: D.ma20, smooth: true, showSymbol: false,
        lineStyle: {{ width: 1.6, color: '#3b82f6' }}, itemStyle: {{ color: '#3b82f6' }}
      }},
      {{
        name: 'MA60', type: 'line', data: D.ma60, smooth: true, showSymbol: false,
        lineStyle: {{ width: 1.6, color: '#8b5cf6' }}, itemStyle: {{ color: '#8b5cf6' }}
      }},
      {{
        name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: D.vols,
        itemStyle: {{ color: function (p) {{ return D.upClose[p.dataIndex] ? upColor : downColor; }} }}
      }},
      {{
        name: '买点', type: 'scatter', symbol: 'triangle', symbolSize: 12,
        itemStyle: {{ color: upColor, borderColor: '#fff', borderWidth: 1 }},
        data: D.buys, z: 10,
        tooltip: {{ formatter: function (p) {{ return p.data[2]; }} }}
      }},
      {{
        name: '卖点', type: 'scatter', symbol: 'triangle', symbolRotate: 180, symbolSize: 12,
        itemStyle: {{ color: downColor, borderColor: '#fff', borderWidth: 1 }},
        data: D.sells, z: 10,
        tooltip: {{ formatter: function (p) {{ return p.data[2]; }} }}
      }}
    ]
  }};

  chart.setOption(option);
  window.addEventListener('resize', function () {{ chart.resize(); }});
}})();
</script>
</body>
</html>
"""


def color_text(pct):
    cls = "up" if pct >= 0 else "down"
    sign = "+" if pct >= 0 else ""
    return '<span class="{}">{}{:.2f}%</span>'.format(cls, sign, pct)


def build_html(code, name, bars, window=250, zoom_start=40):
    """把数据拼成一个完整的 HTML 字符串。"""
    bars = bars[-window:] if len(bars) > window else bars
    closes = [b["close"] for b in bars]
    ma5 = moving_average(closes, 5)
    ma20 = moving_average(closes, 20)
    ma60 = moving_average(closes, 60)

    buys, sells = find_signals(bars, ma20, ma60)
    buy_idx = {b["i"]: 1 for b in buys}
    sell_idx = {s["i"]: 1 for s in sells}

    last = bars[-1]
    prev = bars[-2]["close"] if len(bars) > 1 else last["open"]
    chg = (last["close"] - prev) / prev * 100

    head_title = '{} {}　最新 {}　{}'.format(
        name or "", code, "{:.2f}".format(last["close"]), color_text(chg)
    )
    head_sub = (
        "前复权日线 · 共 {n} 根（{d0} ~ {d1}）　红涨绿跌　"
        "▲=收盘上穿MA20且MA20&gt;MA60（买点提示）　▼=收盘下穿MA20（卖点提示）<br>"
        "鼠标悬停看每天价格，底部滑块可缩放；"
        "<b>图上的三角形只是「规则在哪里触发过」，不是任何建议。</b>"
    ).format(n=len(bars), d0=bars[0]["date"], d1=last["date"])

    data = {
        "dates": [b["date"] for b in bars],
        "bars": [{"date": b["date"], "open": b["open"], "close": b["close"],
                  "high": b["high"], "low": b["low"], "vol": b["vol"]} for b in bars],
        # ECharts 的蜡烛顺序是 [开, 收, 最低, 最高]
        "ohlc": [[b["open"], b["close"], b["low"], b["high"]] for b in bars],
        "vols": [b["vol"] for b in bars],
        "upClose": [1 if b["close"] >= b["open"] else 0 for b in bars],
        "ma5": ma5, "ma20": ma20, "ma60": ma60,
        "buys": [[b["i"], b["price"], b["text"]] for b in buys],
        "sells": [[s["i"], s["price"], s["text"]] for s in sells],
        "buyIdx": buy_idx, "sellIdx": sell_idx,
    }

    # 图表库：优先用本地 echarts.min.js（直接内嵌，断网也能看）
    if os.path.exists(ECHARTS_FILE):
        with open(ECHARTS_FILE, "r", encoding="utf-8", errors="ignore") as f:
            echarts_js = f.read()
    else:
        echarts_js = "(function(){var s=document.createElement('script');"
        echarts_js += "s.src='" + ECHARTS_CDN + "';document.head.appendChild(s);})();"

    html = HEAD_HTML.format(title=head_title, head_title=head_title, head_sub=head_sub)
    html += TAIL_HTML.format(
        echarts=echarts_js,
        data=json.dumps(data, ensure_ascii=False),
        zoom_start=zoom_start,
    )
    return html


# ---------------- 五、主流程 ----------------

def make_chart(code, name, window=250, zoom_start=40, open_it=True):
    print("正在拉 {} {} 的日 K 线……".format(name or "", code))
    real_name, bars = fetch_kline(code, count=max(window + 60, 320))
    name = real_name or name
    if len(bars) < 30:
        print("只有 {} 根数据，画不出图（是不是新股？）".format(len(bars)))
        return None

    html = build_html(code, name, bars, window, zoom_start)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    last = bars[-1]
    prev = bars[-2]["close"]
    chg = (last["close"] - prev) / prev * 100
    print("已生成：{}".format(OUT_FILE))
    print("  {} {}  最新 {}  {}{:.2f}%   画了最近 {} 根".format(
        name, code, "{:.2f}".format(last["close"]),
        "+" if chg >= 0 else "", chg, min(len(bars), window)))
    if open_it:
        webbrowser.open("file:///" + OUT_FILE.replace("\\", "/"))
        print("  已在浏览器里打开（关掉浏览器标签不影响下次生成）")
    return OUT_FILE


def menu():
    watch = load_watch()
    print()
    print("=" * 60)
    print("  K 线图查看器")
    print("=" * 60)
    for i, (code, name) in enumerate(watch, 1):
        print("  {}. {} {}".format(i, code, name))
    print("  c. 输入其他代码")
    print("  0. 退出")
    print("=" * 60)

    choice = input("  看哪只？输入编号：").strip()
    if choice == "0" or choice == "":
        return
    if choice.lower() == "c":
        code = input("  股票代码（6 位，如 601398）：").strip()
        if not code:
            return
        make_chart(code, "")
        return
    if not choice.isdigit() or not (1 <= int(choice) <= len(watch)):
        print("  没这个编号。")
        return
    code, name = watch[int(choice) - 1]
    make_chart(code, name)


def main():
    args = sys.argv[1:]
    if not args:
        menu()
        return
    if args[0] == "list":
        for code, name in load_watch():
            print("  {}  {}".format(code, name))
        return
    code = args[0]
    window = int(args[1]) if len(args) > 1 and args[1].isdigit() else 250
    make_chart(code, name_of(code, load_watch()), window=window)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as e:
        print("网络不通，拿不到数据：{}".format(e))
        print("（这个程序要联网拉行情，检查一下网络或稍后再试）")
    except Exception as e:
        print("出错了：{}: {}".format(type(e).__name__, e))
    input("\n按回车关闭……")
