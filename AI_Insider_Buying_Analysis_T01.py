"""
台股內部人增持排行抓取工具
資料來源：MoneyDJ 董監質設異動清單
網址：https://www.moneydj.com/Z/ZE/ZEU/ZEU.djhtm

執行環境需求：
    pip install requests beautifulsoup4 pandas

用法：
    python moneydj_insider_buying.py
    python moneydj_insider_buying.py --days 30 --top 50
    python moneydj_insider_buying.py --days 60 --top 100 --output result.csv
"""

import argparse
import time
from datetime import datetime, timedelta
from collections import defaultdict

import requests
from bs4 import BeautifulSoup
import pandas as pd


# ── 設定區 ────────────────────────────────────────────────────────────────
BASE_URL = "https://www.moneydj.com/Z/ZE/ZEU/ZEU.djhtm"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.moneydj.com/",
}

# 內部人身份對應（Big5 頁面中文欄位）
INSIDER_ROLES = {
    "董事": "董事",
    "監察人": "監察人",
    "經理人": "經理人",
    "大股東": "大股東（>10%）",
    "董事長": "董事長",
    "副董事長": "副董事長",
    "總經理": "總經理",
    "法人董事": "法人董事",
    "法人監察人": "法人監察人",
}
# ── 設定區結束 ─────────────────────────────────────────────────────────────


def fetch_page(session: requests.Session, page: int = 1) -> str | None:
    """抓取單頁資料，回傳 UTF-8 字串；失敗回傳 None。"""
    params = {"a": page} if page > 1 else {}
    try:
        resp = session.get(BASE_URL, headers=HEADERS, params=params, timeout=20)
        resp.raise_for_status()
        # MoneyDJ 使用 Big5 編碼
        raw = resp.content
        try:
            text = raw.decode("big5", errors="replace")
        except Exception:
            text = raw.decode("utf-8", errors="replace")
        return text
    except requests.RequestException as e:
        print(f"  [警告] 第 {page} 頁抓取失敗：{e}")
        return None


def parse_date(date_str: str, current_year: int) -> datetime | None:
    """把 'MM/DD' 轉為 datetime，年份以 current_year 補足。"""
    try:
        return datetime.strptime(f"{current_year}/{date_str.strip()}", "%Y/%m/%d")
    except ValueError:
        return None


def parse_table(html: str, cutoff_date: datetime) -> tuple[list[dict], bool]:
    """
    解析單頁 HTML 表格。
    回傳 (records_list, should_continue)
    should_continue=False 表示遇到早於 cutoff 的資料，可停止翻頁。
    """
    soup = BeautifulSoup(html, "html.parser")
    records = []
    should_continue = True
    now_year = datetime.now().year

    # MoneyDJ 主表格通常是第一個有多欄的 table
    tables = soup.find_all("table")
    target_table = None
    for tbl in tables:
        rows = tbl.find_all("tr")
        if len(rows) > 5:
            # 判斷是否含有「公司名稱」或「申報日」等關鍵字
            header_text = tbl.get_text()
            if any(kw in header_text for kw in ["申報日", "買進", "轉讓", "持股"]):
                target_table = tbl
                break

    if target_table is None:
        # fallback：取最大 table
        target_table = max(tables, key=lambda t: len(t.find_all("tr")), default=None)

    if target_table is None:
        return records, should_continue

    rows = target_table.find_all("tr")

    # 找欄位索引（依表頭判斷）
    col_idx = {
        "date": None,       # 申報日
        "role": None,       # 身份
        "name": None,       # 姓名
        "company": None,    # 公司
        "buy": None,        # 買進（張）
        "sell": None,       # 賣出（張）
        "hold": None,       # 持股餘額
        "total": None,      # 總持股
        "pct": None,        # 持股%
    }

    header_row = rows[0] if rows else None
    if header_row:
        cells = header_row.find_all(["th", "td"])
        for i, cell in enumerate(cells):
            t = cell.get_text(strip=True)
            if "申報日" in t or "日期" in t:
                col_idx["date"] = i
            elif "公司" in t or "名稱" in t:
                col_idx["company"] = i
            elif "身份" in t or "職稱" in t:
                col_idx["role"] = i
            elif "姓名" in t or "代表人" in t:
                col_idx["name"] = i
            elif "買進" in t:
                col_idx["buy"] = i
            elif "賣出" in t or "轉讓" in t:
                col_idx["sell"] = i
            elif "持股餘額" in t or "持股數" in t:
                col_idx["hold"] = i
            elif "持股%" in t or "持股比" in t:
                col_idx["pct"] = i

    for row in rows[1:]:
        cells = row.find_all("td")
        if not cells or len(cells) < 3:
            continue

        def get(idx):
            if idx is not None and idx < len(cells):
                return cells[idx].get_text(strip=True)
            return ""

        # 嘗試解析日期
        date_str = get(col_idx["date"]) if col_idx["date"] is not None else (
            cells[0].get_text(strip=True)
        )
        dt = parse_date(date_str, now_year)
        if dt is None:
            # 嘗試備用：第一欄
            dt = parse_date(cells[0].get_text(strip=True), now_year)

        if dt and dt < cutoff_date:
            should_continue = False
            break

        # 買進張數
        buy_str = get(col_idx["buy"]) if col_idx["buy"] is not None else ""
        if not buy_str:
            # 若找不到明確欄位，嘗試從所有數字欄中找「正數且非零」的第一個
            for c in cells[1:]:
                txt = c.get_text(strip=True).replace(",", "")
                if txt.isdigit() and int(txt) > 0:
                    buy_str = txt
                    break

        try:
            buy_shares = int(buy_str.replace(",", ""))
        except ValueError:
            buy_shares = 0

        if buy_shares <= 0:
            continue

        # 其他欄位
        company_raw = get(col_idx["company"]) if col_idx["company"] is not None else ""
        role = get(col_idx["role"]) if col_idx["role"] is not None else ""
        person = get(col_idx["name"]) if col_idx["name"] is not None else ""
        hold_str = get(col_idx["hold"]) if col_idx["hold"] is not None else ""
        try:
            hold_shares = int(hold_str.replace(",", ""))
        except ValueError:
            hold_shares = 0

        # 從 <a> 抓公司代碼（MoneyDJ 連結通常含股票代號）
        stock_code = ""
        company_name = company_raw
        link = row.find("a")
        if link and link.get("href"):
            href = link["href"]
            # 例：/z/zc/zck/zck_2330.djhtm
            import re
            m = re.search(r"_(\d{4,5})\.djhtm", href)
            if m:
                stock_code = m.group(1)
        if not company_name and link:
            company_name = link.get_text(strip=True)

        records.append({
            "申報日": date_str.strip(),
            "股票代號": stock_code,
            "公司名稱": company_name,
            "身份": role,
            "姓名": person,
            "買進（張）": buy_shares,
            "持股餘額（張）": hold_shares,
        })

    return records, should_continue


def fetch_all_records(days: int = 30, max_pages: int = 20, delay: float = 1.5) -> list[dict]:
    """
    翻頁抓取，直到超過 days 天前的資料或達到 max_pages。
    delay：每頁請求間隔秒數，避免被封鎖。
    """
    cutoff = datetime.now() - timedelta(days=days)
    session = requests.Session()
    all_records = []

    print(f"抓取近 {days} 天資料（截止日：{cutoff.strftime('%Y/%m/%d')}）…")

    for page in range(1, max_pages + 1):
        print(f"  第 {page} 頁…", end=" ", flush=True)
        html = fetch_page(session, page)
        if html is None:
            print("失敗，停止。")
            break

        records, should_continue = parse_table(html, cutoff)
        print(f"找到 {len(records)} 筆買進申報")
        all_records.extend(records)

        if not should_continue:
            print("  已達截止日期，停止翻頁。")
            break

        if page < max_pages:
            time.sleep(delay)

    print(f"\n合計抓取 {len(all_records)} 筆原始買進申報。")
    return all_records


def aggregate_top_n(records: list[dict], top_n: int = 50) -> pd.DataFrame:
    """
    依「公司」彙總買進張數，回傳前 top_n 名 DataFrame。
    同一公司多筆申報（不同人/日期）會合計。
    """
    company_agg = defaultdict(lambda: {
        "股票代號": "",
        "公司名稱": "",
        "買進合計（張）": 0,
        "申報次數": 0,
        "申報人員": [],
        "最新申報日": "",
    })

    for rec in records:
        key = rec["股票代號"] or rec["公司名稱"]
        d = company_agg[key]
        d["股票代號"] = rec["股票代號"] or d["股票代號"]
        d["公司名稱"] = rec["公司名稱"] or d["公司名稱"]
        d["買進合計（張）"] += rec["買進（張）"]
        d["申報次數"] += 1
        person_role = f"{rec['姓名']}（{rec['身份']}）" if rec["身份"] else rec["姓名"]
        if person_role and person_role not in d["申報人員"]:
            d["申報人員"].append(person_role)
        # 保留最新日期（假設字串比較 MM/DD 在同年有效）
        if rec["申報日"] > d["最新申報日"]:
            d["最新申報日"] = rec["申報日"]

    rows = []
    for key, d in company_agg.items():
        rows.append({
            "股票代號": d["股票代號"],
            "公司名稱": d["公司名稱"],
            "買進合計（張）": d["買進合計（張）"],
            "申報次數": d["申報次數"],
            "申報人員": "；".join(d["申報人員"]),
            "最新申報日": d["最新申報日"],
        })

    df = (
        pd.DataFrame(rows)
        .sort_values("買進合計（張）", ascending=False)
        .reset_index(drop=True)
    )
    df.index += 1
    df.index.name = "排名"
    return df.head(top_n)


def display_table(df: pd.DataFrame) -> None:
    """在終端機印出格式化排行表。"""
    print("\n" + "═" * 72)
    print(f"  台股內部人增持排行（資料來源：MoneyDJ 董監質設異動清單）")
    print("═" * 72)
    header = f"{'排名':>4}  {'代號':<6}  {'公司名稱':<14}  {'買進合計(張)':>12}  {'次數':>4}  {'最新申報日'}"
    print(header)
    print("─" * 72)
    for rank, row in df.iterrows():
        print(
            f"{rank:>4}  "
            f"{row['股票代號']:<6}  "
            f"{row['公司名稱']:<14}  "
            f"{row['買進合計（張）']:>12,}  "
            f"{row['申報次數']:>4}  "
            f"{row['最新申報日']}"
        )
    print("═" * 72)
    print(f"  合計 {len(df)} 家公司，共 {df['買進合計（張）'].sum():,} 張\n")


def main():
    parser = argparse.ArgumentParser(
        description="MoneyDJ 台股內部人增持排行抓取工具"
    )
    parser.add_argument(
        "--days", type=int, default=30,
        help="抓取近幾天的申報資料（預設：30）"
    )
    parser.add_argument(
        "--top", type=int, default=50,
        help="顯示前幾名（預設：50）"
    )
    parser.add_argument(
        "--output", type=str, default="",
        help="輸出 CSV 檔案路徑（選填，留空則只印出結果）"
    )
    parser.add_argument(
        "--max-pages", type=int, default=30,
        help="最多翻幾頁（預設：30）"
    )
    parser.add_argument(
        "--delay", type=float, default=1.5,
        help="每頁請求間隔秒數（預設：1.5）"
    )
    args = parser.parse_args()

    print(f"\n{'─'*50}")
    print(f"  MoneyDJ 內部人增持排行抓取工具")
    print(f"  抓取區間：近 {args.days} 天  │  顯示前 {args.top} 名")
    print(f"{'─'*50}\n")

    records = fetch_all_records(
        days=args.days,
        max_pages=args.max_pages,
        delay=args.delay,
    )

    if not records:
        print("未抓取到任何資料，請確認網路連線及網站結構是否有變動。")
        return

    df = aggregate_top_n(records, top_n=args.top)
    display_table(df)

    if args.output:
        df.to_csv(args.output, encoding="utf-8-sig")
        print(f"已儲存至：{args.output}")
    else:
        default_name = f"insider_buying_{datetime.now().strftime('%Y%m%d')}.csv"
        df.to_csv(default_name, encoding="utf-8-sig")
        print(f"已儲存至：{default_name}")


if __name__ == "__main__":
    main()
