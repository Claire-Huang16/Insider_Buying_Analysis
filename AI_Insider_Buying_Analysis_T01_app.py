import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import time

# twstock 提供台股公司名稱本地查詢（不需網路）
try:
    import twstock as _twstock
    _TW_CODES = _twstock.codes
    _USE_TWSTOCK = True
except ImportError:
    _TW_CODES = {}
    _USE_TWSTOCK = False

st.set_page_config(
    page_title="內部人交易分析系統",
    page_icon="🔍",
    layout="wide"
)

# ==================== 交易類型資料（美股 SEC Form 4）====================
TRANSACTION_CODES = {
    'P-Purchase': {'中文': '公開市場購買', '價值': '⭐⭐⭐⭐⭐', '類別': '一般交易代碼', '說明': '用真金白銀買入 - 最強看好信號'},
    'S-Sale': {'中文': '公開市場出售', '價值': '⭐⭐', '類別': '一般交易代碼', '說明': '需結合其他交易判斷'},
    'V-Voluntary': {'中文': '自願提前申報', '價值': 'ℹ️', '類別': '一般交易代碼', '說明': '僅表示申報時間'},
    'A-Award': {'中文': '獎勵授予', '價值': '⭐', '類別': 'Rule 16b-3 豁免交易代碼', '說明': '薪酬計劃無分析價值'},
    'D-Return': {'中文': '回售公司', '價值': '⭐', '類別': 'Rule 16b-3 豁免交易代碼', '說明': '技術性交易'},
    'F-InKind': {'中文': '以股支付', '價值': '⭐', '類別': 'Rule 16b-3 豁免交易代碼', '說明': '常與M和S組合出現'},
    'I-Discretionary': {'中文': '全權委託交易', '價值': '⭐⭐', '類別': 'Rule 16b-3 豁免交易代碼', '說明': '可能有意義需查看上下文'},
    'M-Exempt': {'中文': '行權/轉換豁免', '價值': '⭐', '類別': 'Rule 16b-3 豁免交易代碼', '說明': '薪酬計劃到期'},
    'C-Conversion': {'中文': '衍生品轉換', '價值': '⭐', '類別': '衍生證券代碼', '說明': '技術性操作'},
    'E-ExpireShort': {'中文': '空頭部位到期', '價值': '⭐', '類別': '衍生證券代碼', '說明': '技術性操作'},
    'H-ExpireLong': {'中文': '多頭部位到期', '價值': '⭐', '類別': '衍生證券代碼', '說明': '技術性操作'},
    'O-OutOfTheMoney': {'中文': '價外行權', '價值': '⭐', '類別': '衍生證券代碼', '說明': '罕見情況'},
    'X-InTheMoney': {'中文': '價內行權', '價值': '⭐⭐', '類別': '衍生證券代碼', '說明': '正常行權操作'},
    'G-Gift': {'中文': '贈與', '價值': '❌', '類別': '其他Section 16(b)豁免交易代碼', '說明': '無投資價值'},
    'L-Small': {'中文': '小額收購', '價值': '⭐', '類別': '其他Section 16(b)豁免交易代碼', '說明': '金額太小通常忽略'},
    'W-Will': {'中文': '遺囑/繼承', '價值': '❌', '類別': '其他Section 16(b)豁免交易代碼', '說明': '無投資價值'},
    'Z-Trust': {'中文': '信託操作', '價值': '⭐', '類別': '其他Section 16(b)豁免交易代碼', '說明': '技術性操作'},
    'J-Other': {'中文': '其他交易', '價值': '❓', '類別': '特殊交易代碼', '說明': '需要查看註腳'},
    'K-Swap': {'中文': '股權互換', '價值': '⭐⭐', '類別': '特殊交易代碼', '說明': '複雜金融操作'},
    'U-Tender': {'中文': '要約收購', '價值': '⭐⭐⭐', '類別': '特殊交易代碼', '說明': '公司併購相關'}
}

# ==================== 台股董監事申報類型 ====================
TW_TRANSACTION_TYPES = {
    '買進': {'說明': '董監事於公開市場買進股票 - 看好信號', '價值': '⭐⭐⭐⭐⭐'},
    '賣出': {'說明': '董監事於公開市場賣出股票 - 需結合背景判斷', '價值': '⭐⭐'},
    '轉讓': {'說明': '股份轉讓（非公開市場），如贈與或信託', '價值': '⭐'},
    '受讓': {'說明': '接受股份轉讓', '價值': '⭐'},
    '認購': {'說明': '參與現金增資認購新股', '價值': '⭐⭐⭐'},
    '行使認股權': {'說明': '行使員工認股權', '價值': '⭐'},
    '設定質押': {'說明': '股份設定質押借款 - 注意財務壓力風險', '價值': '⚠️'},
    '解除質押': {'說明': '解除股份質押 - 財務壓力減輕', '價值': 'ℹ️'},
}

# ==================== 美股 API 函數（FMP /stable/ 端點）====================

@st.cache_data(ttl=3600)
def get_company_profile(symbol, api_key):
    """獲取美股公司基本資料（使用 /stable/ 端點）"""
    url = f"https://financialmodelingprep.com/stable/profile?symbol={symbol}&apikey={api_key}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data and len(data) > 0:
            return data[0]
        return None
    except Exception as e:
        st.error(f"獲取公司資料失敗: {str(e)}")
        return None

@st.cache_data(ttl=1800)
def get_insider_trading_by_symbol(symbol, api_key):
    """按美股公司代碼獲取內部人交易（使用 /stable/ 端點）"""
    url = f"https://financialmodelingprep.com/stable/insider-trading/search?symbol={symbol}&page=0&limit=100&apikey={api_key}"
    try:
        response = requests.get(url, timeout=15)
        data = response.json()
        if data and isinstance(data, list):
            return data
        return []
    except Exception as e:
        st.error(f"獲取內部人交易資料失敗: {str(e)}")
        return []

@st.cache_data(ttl=1800)
def get_insider_trading_by_cik(cik, api_key):
    """按內部人 CIK 獲取美股交易記錄（使用 /stable/ 端點）"""
    url = f"https://financialmodelingprep.com/stable/insider-trading/search?reportingCik={cik}&page=0&limit=100&apikey={api_key}"
    try:
        response = requests.get(url, timeout=15)
        data = response.json()
        if data and isinstance(data, list):
            return data
        return []
    except Exception as e:
        st.error(f"獲取內部人交易資料失敗: {str(e)}")
        return []

# ==================== FinMind API 函數（台股，Backer 付費等級）====================
# 注意：FinMind 沒有董監事個人申報異動資料集
# 正確資料來源：公開資訊觀測站（MOPS）的董監事持股異動申報
# FinMind 提供的是：股東持股分級、外資持股、三大法人等籌碼面資料

FINMIND_BASE_URL = "https://api.finmindtrade.com/api/v4/data"

def _finmind_headers(token):
    """FinMind v4 正確驗證方式：Authorization Bearer header"""
    return {"Authorization": f"Bearer {token}"}


@st.cache_data(ttl=1800)
def get_finmind_stock_price(stock_code, finmind_token):
    """取得台股最新股價（TaiwanStockPrice）"""
    from datetime import timedelta
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_code,
        "start_date": start,
        "end_date": end,
    }
    try:
        resp = requests.get(FINMIND_BASE_URL, headers=_finmind_headers(finmind_token),
                            params=params, timeout=15)
        result = resp.json()
        if result.get("status") != 200:
            return None
        data = result.get("data", [])
        if not data:
            return None
        df = pd.DataFrame(data)
        if "close" in df.columns:
            return float(df["close"].iloc[-1])
        return None
    except Exception:
        return None


@st.cache_data(ttl=1800)
def get_finmind_holding_shares_per(stock_code, finmind_token, start_date="2020-01-01"):
    """
    股東持股分級表 TaiwanStockHoldingSharesPer（需 Backer 付費等級）
    顯示各持股區間的股東人數與持股比例，反映籌碼集中度
    """
    params = {
        "dataset": "TaiwanStockHoldingSharesPer",
        "data_id": stock_code,
        "start_date": start_date,
    }
    try:
        resp = requests.get(FINMIND_BASE_URL, headers=_finmind_headers(finmind_token),
                            params=params, timeout=20)
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") != 200:
            msg = result.get("msg", "未知錯誤")
            return pd.DataFrame(), f"FinMind API 錯誤：{msg}"
        data = result.get("data", [])
        if not data:
            return pd.DataFrame(), None
        return pd.DataFrame(data), None
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        msg = ""
        try:
            msg = e.response.json().get("detail", "")
        except Exception:
            pass
        return pd.DataFrame(), f"HTTP {status}：{msg or str(e)}"
    except Exception as e:
        return pd.DataFrame(), str(e)


@st.cache_data(ttl=1800)
def get_finmind_institutional_investors(stock_code, finmind_token, start_date="2023-01-01"):
    """
    三大法人買賣表 TaiwanStockInstitutionalInvestorsBuySell
    外資、投信、自營商的買賣超，反映機構持股動向
    """
    params = {
        "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
        "data_id": stock_code,
        "start_date": start_date,
    }
    try:
        resp = requests.get(FINMIND_BASE_URL, headers=_finmind_headers(finmind_token),
                            params=params, timeout=20)
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") != 200:
            msg = result.get("msg", "未知錯誤")
            return pd.DataFrame(), f"FinMind API 錯誤：{msg}"
        data = result.get("data", [])
        if not data:
            return pd.DataFrame(), None
        return pd.DataFrame(data), None
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        msg = ""
        try:
            msg = e.response.json().get("detail", "")
        except Exception:
            pass
        return pd.DataFrame(), f"HTTP {status}：{msg or str(e)}"
    except Exception as e:
        return pd.DataFrame(), str(e)


# ==================== MOPS 公開資訊觀測站 — 董監事持股異動申報 ====================

MOPS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*",
    "Referer": "https://mops.twse.com.tw/",
}

@st.cache_data(ttl=1800)
def get_mops_insider_changes(stock_code, year_roc=None):
    """
    公開資訊觀測站：董監事持股異動申報
    API: https://mops.twse.com.tw/mops/web/ajax_t51sb06
    year_roc: 民國年，預設查當年度
    回傳 (DataFrame, error_msg)
    """
    if year_roc is None:
        year_roc = datetime.now().year - 1911

    url = "https://mops.twse.com.tw/mops/web/ajax_t51sb06"
    form_data = {
        "encodeURIComponent": "1",
        "step": "1",
        "firstin": "1",
        "off": "1",
        "queryName": "co_id",
        "inpuType": "co_id",
        "TYPEK": "all",
        "isnew": "false",
        "co_id": stock_code,
        "year": str(year_roc),
    }
    try:
        resp = requests.post(url, data=form_data, headers=MOPS_HEADERS, timeout=20)
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            return pd.DataFrame(), f"MOPS HTTP {resp.status_code}"

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")

        # 找所有表格
        tables = soup.find_all("table")
        if not tables:
            return pd.DataFrame(), "MOPS 無資料（該年度無申報記錄）"

        dfs = []
        for tbl in tables:
            try:
                sub = pd.read_html(str(tbl))
                for df in sub:
                    if df.shape[0] > 0 and df.shape[1] >= 4:
                        dfs.append(df)
            except Exception:
                continue

        if not dfs:
            return pd.DataFrame(), "MOPS 解析失敗（找不到有效資料表）"

        df = pd.concat(dfs, ignore_index=True)
        # 攤平多層欄位
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [" ".join(str(c) for c in col if "Unnamed" not in str(c)).strip()
                          for col in df.columns]
        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(how="all").reset_index(drop=True)
        return df, None

    except requests.exceptions.Timeout:
        return pd.DataFrame(), "MOPS 請求逾時"
    except requests.exceptions.ConnectionError:
        return pd.DataFrame(), "無法連線至 MOPS"
    except Exception as e:
        return pd.DataFrame(), str(e)




# ==================== 台股資料來源：Goodinfo.tw ====================
# 關鍵發現：goodinfo StockList 的資料藏在 <div id="txtStockListData"> 內
# 用標準 requests 即可取得，不需要 Playwright
# StockDirectorSharehold 為 JS 動態頁，改用 POST 方式繞過

from bs4 import BeautifulSoup

GOODINFO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://goodinfo.tw/tw/index.asp",
}


def _goodinfo_get(url, params=None, timeout=20):
    """GET 請求 goodinfo，回傳 (html, error)"""
    time.sleep(1)  # 避免被限速
    try:
        r = requests.get(url, params=params, headers=GOODINFO_HEADERS, timeout=timeout)
        r.encoding = "utf-8"
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        if not r.text.strip():
            return None, "回傳空頁面"
        return r.text, None
    except requests.exceptions.Timeout:
        return None, "請求逾時，請稍後再試"
    except requests.exceptions.ConnectionError:
        return None, "無法連線至 goodinfo.tw"
    except Exception as e:
        return None, str(e)


def _parse_txtStockListData(html):
    """
    解析 goodinfo StockList 頁面。
    資料藏在 <div id="txtStockListData"> 內的 table。
    使用 pandas.read_html 解析多層表頭。
    回傳 DataFrame。
    """
    import pandas as pd
    soup = BeautifulSoup(html, "html.parser")
    div = soup.find("div", id="txtStockListData")
    if not div:
        return pd.DataFrame()
    try:
        dfs = pd.read_html(div.prettify())
        # 過濾掉只有 1 行或 1 欄的空表
        dfs = [df for df in dfs if df.shape[0] > 1 and df.shape[1] > 2]
        if not dfs:
            return pd.DataFrame()
        df = dfs[0]
        # 攤平多層欄位名稱
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [" ".join(str(c) for c in col if str(c) != "Unnamed").strip()
                          for col in df.columns]
        df.columns = [str(c).strip() for c in df.columns]
        # 移除全為 NaN 的列
        df = df.dropna(how="all").reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()


def _parse_director_table(html):
    """
    解析個股董監持股頁面（StockDirectorSharehold）。
    goodinfo 用 requests 抓到的是靜態骨架，
    實際資料在 <div id="divDetail"> 或最大表格內。
    回傳 DataFrame。
    """
    import pandas as pd
    soup = BeautifulSoup(html, "html.parser")

    # 嘗試多種 container
    container = (
        soup.find("div", id="divDetail") or
        soup.find("table", id="tblDetail") or
        soup.find("div", id="divStockDetail")
    )

    target_html = container.prettify() if container else html

    try:
        dfs = pd.read_html(target_html)
        dfs = [df for df in dfs if df.shape[0] > 1 and df.shape[1] > 2]
        if not dfs:
            # 找最大的 table
            tables = soup.find_all("table")
            best = max(tables, key=lambda t: len(t.find_all("tr")), default=None)
            if best:
                dfs = pd.read_html(best.prettify())
                dfs = [df for df in dfs if df.shape[0] > 1 and df.shape[1] > 2]
        if not dfs:
            return pd.DataFrame()
        df = dfs[0]
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [" ".join(str(c) for c in col if "Unnamed" not in str(c)).strip()
                          for col in df.columns]
        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(how="all").reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_tw_company_profile(stock_code):
    """公司名稱用 twstock 本地資料庫（不需網路）"""
    profile = {
        "stockCode": stock_code,
        "companyName": stock_code,
        "industry": "",
        "market": "台股",
    }
    if _USE_TWSTOCK:
        info = _TW_CODES.get(stock_code)
        if info:
            profile["companyName"] = info.name
            profile["industry"] = getattr(info, "group", "")
            profile["market"] = getattr(info, "market", "台股")
    return profile


@st.cache_data(ttl=1800)
def get_tw_insider_holdings(stock_code):
    """
    個股董監持股。
    URL: https://goodinfo.tw/tw/StockDirectorSharehold.asp?STOCK_ID={code}
    回傳 (DataFrame, error)
    """
    import pandas as pd
    html, err = _goodinfo_get(
        "https://goodinfo.tw/tw/StockDirectorSharehold.asp",
        params={"STOCK_ID": stock_code}
    )
    if err:
        return pd.DataFrame(), err

    df = _parse_director_table(html)
    return df, None


@st.cache_data(ttl=1800)
def get_tw_insider_ranking(rank_range=300):
    """
    全體上市公司董監持股排行。
    URL: goodinfo StockList（用戶提供）
    關鍵：資料在 <div id="txtStockListData">
    回傳 (DataFrame, error)
    """
    import pandas as pd
    html, err = _goodinfo_get(
        "https://goodinfo.tw/tw/StockList.asp",
        params={
            "MARKET_CAT": "熱門排行",
            "INDUSTRY_CAT": "全體董監持股比例(%)@@全體董監@@持股比例(%)",
            "SHEET": "董監持股",
            "RPT_TIME": "最新資料",
            "RANK_RANGE": str(rank_range),
        }
    )
    if err:
        return pd.DataFrame(), err

    df = _parse_txtStockListData(html)
    if df.empty:
        # debug：存原始 HTML 供分析
        try:
            with open("/tmp/goodinfo_debug.html", "w", encoding="utf-8") as f:
                f.write(html)
        except Exception:
            pass
        return pd.DataFrame(), "解析失敗：找不到 #txtStockListData（已將原始 HTML 存至 /tmp/goodinfo_debug.html 供檢查）"

    return df, None

# ==================== 數據處理函數 ====================

def process_insider_data(raw_data):
    """處理美股內部人交易數據（修正：使用 url 欄位而非 link）"""
    if not raw_data:
        return pd.DataFrame()

    processed_data = []

    for trade in raw_data:
        # 計算交易金額
        transaction_value = trade.get('securitiesTransacted', 0) * trade.get('price', 0)

        processed_data.append({
            '交易日期': trade.get('transactionDate', ''),
            '股票代碼': trade.get('symbol', ''),
            '內部人姓名': trade.get('reportingName', ''),
            '內部人代碼': trade.get('reportingCik', ''),
            '職位': trade.get('typeOfOwner', ''),
            '交易類型': trade.get('transactionType', ''),
            '交易股數': trade.get('securitiesTransacted', 0),
            '交易價格': trade.get('price', 0),
            '交易金額': transaction_value,
            '交易後持股': trade.get('securitiesOwned', 0),
            'SEC_URL': trade.get('url', '')   # ✅ 修正：使用 url 而非 link
        })

    df = pd.DataFrame(processed_data)

    if not df.empty and '交易日期' in df.columns:
        df = df.sort_values('交易日期', ascending=False)

    return df

def process_tw_insider_data(raw_data, fields):
    """處理台股董監事持股異動數據"""
    if not raw_data or not fields:
        return pd.DataFrame()
    try:
        df = pd.DataFrame(raw_data, columns=fields)
        return df
    except Exception as e:
        st.error(f"處理台股資料失敗: {str(e)}")
        return pd.DataFrame()

def format_number(num):
    """格式化數字為千分位"""
    try:
        return f"{int(num):,}"
    except:
        return str(num)

def format_currency(num, currency="$"):
    """格式化為貨幣（預設美元）"""
    try:
        return f"{currency}{num:,.2f}"
    except:
        return str(num)

def create_transaction_table(df):
    """創建美股顯示用的交易表格"""
    if df.empty:
        return pd.DataFrame()

    display_df = df.copy()

    display_df['交易股數'] = display_df['交易股數'].apply(format_number)
    display_df['交易價格'] = display_df['交易價格'].apply(lambda x: format_currency(x, "$"))
    display_df['交易金額'] = display_df['交易金額'].apply(lambda x: format_currency(x, "$"))
    display_df['交易後持股'] = display_df['交易後持股'].apply(format_number)

    final_columns = [
        '交易日期', '股票代碼', '內部人姓名', '內部人代碼', '職位',
        '交易類型', '交易股數', '交易價格', '交易金額',
        '交易後持股', 'SEC_URL'
    ]

    return display_df[final_columns]

# ==================== 主程式 ====================
st.title("🔍 內部人交易分析系統")
st.markdown("---")

# ==================== 側邊欄 ====================
with st.sidebar:
    st.header("⚙️ 系統設定")

    # ── 市場選擇 ──
    st.subheader("🌏 市場選擇")
    market_choice = st.radio(
        "選擇分析市場",
        options=["🇹🇼 台股（FinMind 申報）", "🇺🇸 美股（SEC Form 4）"],
        index=0,
        help="台股：透過 FinMind API 查詢董監事持股異動；美股：查詢 SEC Form 4 內部人申報"
    )
    is_tw_market = "台股" in market_choice

    st.markdown("---")

    # ── API 金鑰 ──
    if is_tw_market:
        st.subheader("🔑 API 金鑰")
        finmind_api_key = st.text_input(
            "FinMind API Key *",
            type="password",
            help="用於獲取台股董監事持股異動資料（FinMind Backer 付費等級）"
        )
        fmp_api_key = ""
    else:
        st.subheader("🔑 API 金鑰")
        fmp_api_key = st.text_input(
            "FMP API Key *",
            type="password",
            help="用於獲取美股內部人交易資料（Financial Modeling Prep）"
        )
        finmind_api_key = ""

    st.markdown("---")

    # ── 查詢設定 ──
    st.subheader("🔍 查詢設定")

    if is_tw_market:
        st.markdown("**🏢 台股代號** *")
        symbol_input = st.text_input(
            "台股代號",
            placeholder="例如: 2330",
            help="輸入台灣股票代號（4位數字）",
            label_visibility="collapsed"
        ).strip()
        st.caption("ℹ️ 輸入台灣證券交易所股票代號，例如: 2330（台積電）")
        cik_input = ""  # 台股不使用 CIK

        st.markdown("")
        st.markdown("**📅 董監事持股異動年度**")
        current_roc = datetime.now().year - 1911
        year_options = list(range(current_roc, current_roc - 6, -1))
        chosen_roc = st.selectbox(
            "查詢民國年度",
            options=year_options,
            format_func=lambda y: f"民國 {y} 年（{y+1911}）",
            label_visibility="collapsed"
        )

        st.markdown("**📅 股東持股分級起始年**")
        start_year2 = st.selectbox(
            "股東持股分級起始年份",
            options=[str(y) for y in range(2020, datetime.now().year + 1)],
            index=0,
            label_visibility="collapsed",
            key="chip_year"
        )

        st.markdown("**📅 三大法人買賣起始年**")
        start_year3 = st.selectbox(
            "三大法人起始年份",
            options=[str(y) for y in range(2022, datetime.now().year + 1)],
            index=0,
            label_visibility="collapsed",
            key="inst_year"
        )
    else:
        st.markdown("**🏢 公司代碼** *")
        symbol_input = st.text_input(
            "股票代碼",
            placeholder="例如: AAPL",
            help="輸入美股代碼",
            label_visibility="collapsed"
        ).upper().strip()
        st.caption("ℹ️ 輸入美股代碼")

        st.markdown("")

        st.markdown("**👤 內部人 CIK** (可選)")
        cik_input = st.text_input(
            "內部人 CIK",
            placeholder="例如: 0001214156",
            help="從表格「內部人代碼」欄位複製",
            label_visibility="collapsed"
        ).strip()
        st.caption("ℹ️ 從表格「內部人代碼」欄位複製")

    st.markdown("---")

    run_button = st.button("🚀 執行分析", type="primary", use_container_width=True)

    st.markdown("---")

    # ── 使用說明 ──
    st.subheader("📚 使用說明")
    if is_tw_market:
        st.markdown("""
**基本使用**：
1. 輸入 FinMind API Key（必填）
2. 輸入台股代號（必填）
3. 點擊「執行分析」

**各頁籤資料來源**：
- 📋 董監事持股異動 → 公開資訊觀測站（免費）
- 📊 股東持股分級 → FinMind Backer
- 🏦 三大法人買賣 → FinMind（一般會員可用）
        """)
    else:
        st.markdown("""
**基本使用**：
1. 輸入公司股票代碼（必填）
2. 點擊「執行分析」
3. 查看「公司交易明細」頁籤

**查詢特定內部人**：
1. 從表格複製「內部人代碼」
2. 貼到左側「內部人 CIK」輸入框
3. 點擊「執行分析」
4. 切換到「內部人交易明細」頁籤
        """)

    st.markdown("---")
    st.caption("### ⚠️ 免責聲明")
    st.caption("""
本系統僅供學術研究與教育用途，資料來源為公開資訊。
**不構成投資建議或財務建議**。請使用者自行判斷投資決策，並承擔相關風險。
    """)

# ==================== 主要內容區域 ====================

# ── 美股入口驗證 ──
if not is_tw_market:
    if not fmp_api_key:
        st.info("👈 請在左側輸入 FMP API Key 開始使用")
        st.stop()

# ── 共用：等待執行 ──
if not run_button:
    st.info("👈 請在左側輸入股票代碼，然後點擊「執行分析」開始")
    st.markdown("""
## 🎯 系統功能

本系統支援 **美股** 與 **台股** 兩種市場的內部人交易分析：

### 🇺🇸 美股（SEC Form 4）
- 查詢公司所有內部人 SEC Form 4 申報交易
- 依內部人 CIK 查詢跨公司交易記錄
- 20 種交易類型完整說明與價值評級
- 提供 SEC 官方文件連結

### 🇹🇼 台股（混合資料來源）
- 📋 **董監事持股異動**：公開資訊觀測站（MOPS）免費資料，按民國年度查詢
- 📊 **股東持股分級**：FinMind `TaiwanStockHoldingSharesPer`（Backer）
- 🏦 **三大法人買賣**：FinMind `TaiwanStockInstitutionalInvestorsBuySell`

### 📋 共同功能
- 完整交易明細顯示
- CSV 格式下載匯出
- 交易類型教育說明
    """)
    st.stop()

# ── 共用：股票代碼驗證 ──
if not symbol_input:
    st.error("❌ 請輸入股票代碼")
    st.stop()

# ==================== 台股分析流程 ====================
if is_tw_market:
    # ── 台股入口驗證 ──
    if not finmind_api_key:
        st.info("👈 請在左側輸入 FinMind API Key 開始使用")
        st.markdown("""
> **如何取得 FinMind API Key？**
> 1. 前往 [FinMind](https://finmindtrade.com/) 註冊帳號
> 2. 升級至 **Backer** 付費等級（可解鎖股東持股分級等資料集）
> 3. 至帳號設定頁面複製 Token，貼入左側輸入框
>
> **注意：** 董監事持股異動（MOPS）頁籤不需要 FinMind，輸入任意值即可
        """)
        st.stop()

    # 公司基本資訊（twstock 本地）
    with st.spinner(f"正在取得 {symbol_input} 公司資訊..."):
        tw_profile = get_tw_company_profile(symbol_input)
        price_val = get_finmind_stock_price(symbol_input, finmind_api_key)
        if price_val:
            tw_profile["price"] = price_val

    company_title = tw_profile.get("companyName", symbol_input)
    industry_txt  = tw_profile.get("industry", "")
    market_txt    = tw_profile.get("market", "台股")
    st.subheader(f"🇹🇼 {symbol_input} - {company_title}")
    col1, col2, col3 = st.columns(3)
    with col1:
        pv = tw_profile.get("price")
        st.metric("最新股價", f"NT${pv:,.1f}" if pv else "—")
    with col2:
        st.metric("產業", industry_txt or "—")
    with col3:
        st.metric("市場", market_txt or "台股")

    st.markdown("---")

    # 台股頁籤
    tab_tw1, tab_tw2, tab_tw3, tab_tw4 = st.tabs([
        "📋 董監事持股異動",
        "📊 股東持股分級（籌碼）",
        "🏦 三大法人買賣",
        "📚 台股申報說明"
    ])

    # ── 頁籤1：董監事持股異動（MOPS 公開資訊觀測站）──
    with tab_tw1:
        st.subheader(f"📋 {symbol_input} 董監事持股異動申報")
        st.caption("資料來源：公開資訊觀測站（MOPS）— 董監事持股異動申報表（t51sb06）")

        with st.spinner(f"正在從公開資訊觀測站取得 {symbol_input} 民國 {chosen_roc} 年資料..."):
            df_mops, mops_err = get_mops_insider_changes(symbol_input, year_roc=chosen_roc)

        if mops_err:
            st.error(f"❌ {mops_err}")
            st.info(f"📎 可直接至 [公開資訊觀測站](https://mops.twse.com.tw/mops/web/t51sb06) 查詢")
        elif df_mops.empty:
            st.warning(f"⚠️ 民國 {chosen_roc} 年無 {symbol_input} 的董監事持股異動申報記錄")
        else:
            st.info(f"共 {len(df_mops)} 筆申報記錄")
            st.dataframe(df_mops, use_container_width=True, height=500, hide_index=True)
            st.markdown("---")
            csv1 = df_mops.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "📥 下載董監事持股異動 CSV", csv1,
                file_name=f"mops_insider_{symbol_input}_{chosen_roc}.csv",
                mime="text/csv"
            )
            st.markdown(f"🔗 [至公開資訊觀測站查看原始資料](https://mops.twse.com.tw/mops/web/t51sb06)")

    # ── 頁籤2：股東持股分級（FinMind Backer）──
    with tab_tw2:
        st.subheader(f"📊 {symbol_input} 股東持股分級（籌碼集中度）")
        st.caption("資料來源：FinMind API — TaiwanStockHoldingSharesPer（需 Backer 付費等級）")

        with st.spinner(f"正在從 FinMind 取得 {symbol_input} 股東持股分級..."):
            df_holding, holding_err = get_finmind_holding_shares_per(symbol_input, finmind_api_key, start_date=f"{start_year2}-01-01")

        if holding_err:
            st.error(f"❌ {holding_err}")
            st.info("請確認 FinMind API Key 正確且為 Backer 付費等級")
        elif df_holding.empty:
            st.warning("⚠️ 無股東持股分級資料")
        else:
            # 取最新一期
            if "date" in df_holding.columns:
                latest_date = df_holding["date"].max()
                df_latest = df_holding[df_holding["date"] == latest_date].copy()
                st.info(f"最新資料日期：{latest_date}　共 {len(df_holding)} 筆歷史記錄")

                col_map_h = {
                    "date": "日期", "stock_id": "股票代號",
                    "HoldingSharesLevel": "持股區間", "people": "股東人數",
                    "percent": "持股比例(%)", "unit": "持股張數"
                }
                df_latest = df_latest.rename(columns={k: v for k, v in col_map_h.items() if k in df_latest.columns})
                st.subheader(f"最新期（{latest_date}）持股分佈")
                st.dataframe(df_latest, use_container_width=True, height=400, hide_index=True)
            else:
                st.dataframe(df_holding, use_container_width=True, height=400, hide_index=True)

            st.markdown("---")
            csv2 = df_holding.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "📥 下載股東持股分級 CSV", csv2,
                file_name=f"holding_per_{symbol_input}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

    # ── 頁籤3：三大法人買賣（FinMind）──
    with tab_tw3:
        st.subheader(f"🏦 {symbol_input} 三大法人買賣超")
        st.caption("資料來源：FinMind API — TaiwanStockInstitutionalInvestorsBuySell")

        with st.spinner(f"正在從 FinMind 取得 {symbol_input} 三大法人資料..."):
            df_inst, inst_err = get_finmind_institutional_investors(symbol_input, finmind_api_key, start_date=f"{start_year3}-01-01")

        if inst_err:
            st.error(f"❌ {inst_err}")
        elif df_inst.empty:
            st.warning("⚠️ 無三大法人資料")
        else:
            col_map_i = {
                "date": "日期", "stock_id": "股票代號", "name": "法人類別",
                "buy": "買進(張)", "sell": "賣出(張)"
            }
            df_inst = df_inst.rename(columns={k: v for k, v in col_map_i.items() if k in df_inst.columns})
            if "買進(張)" in df_inst.columns and "賣出(張)" in df_inst.columns:
                df_inst["買賣超(張)"] = pd.to_numeric(df_inst["買進(張)"], errors="coerce") - pd.to_numeric(df_inst["賣出(張)"], errors="coerce")
            if "日期" in df_inst.columns:
                df_inst = df_inst.sort_values("日期", ascending=False)

            st.info(f"共 {len(df_inst)} 筆記錄（{start_year3} 年起）")

            # 統計卡片
            if "法人類別" in df_inst.columns and "買賣超(張)" in df_inst.columns:
                col1, col2, col3 = st.columns(3)
                for col_w, investor_name in zip([col1, col2, col3], ["外資", "投信", "自營商"]):
                    sub = df_inst[df_inst["法人類別"].str.contains(investor_name, na=False)]
                    total_net = pd.to_numeric(sub["買賣超(張)"], errors="coerce").sum()
                    with col_w:
                        st.metric(f"{investor_name} 累計買賣超", f"{int(total_net):,} 張",
                                  delta=f"{'↑' if total_net > 0 else '↓'} {abs(int(total_net)):,}")
                st.markdown("---")

            st.dataframe(df_inst, use_container_width=True, height=450, hide_index=True)
            st.markdown("---")
            csv3 = df_inst.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "📥 下載三大法人買賣 CSV", csv3,
                file_name=f"institutional_{symbol_input}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

    # ── 頁籤4：台股申報說明 ──
    with tab_tw4:
        st.subheader("📚 台股董監事持股申報說明")

        st.markdown("""
### 🏛️ 台灣內部人申報制度
台灣上市公司董事、監察人及持股超過 **10%** 的大股東，
依《證券交易法》第22條之2及相關規定，須於持股變動後申報。

### 📋 常見申報類型
        """)

        type_data = []
        for t_type, info in TW_TRANSACTION_TYPES.items():
            type_data.append({
                "申報類型": t_type,
                "參考價值": info["價值"],
                "說明": info["說明"]
            })
        tw_type_df = pd.DataFrame(type_data)
        st.dataframe(tw_type_df, use_container_width=True, hide_index=True)

        st.markdown("""
### ⚠️ 特別注意：股份質押
- 董監事**設定質押**比例過高，可能代表財務壓力
- 若遭**強制平倉**，可能對股價造成短期衝擊

### 💡 分析建議
1. **持股比例高且持續增加**：通常代表董監事對公司前景看好
2. **買進筆數 >> 賣出筆數**：籌碼集中信號
3. **質押比例**：留意財務風險

### 🔗 延伸查詢
- [FinMind 台股資料](https://finmindtrade.com/)
- [公開資訊觀測站](https://mops.twse.com.tw)
        """)

        tw_codes_csv = tw_type_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 下載台股申報類型說明 CSV", tw_codes_csv,
            file_name="tw_transaction_types.csv", mime="text/csv"
        )

# ==================== 美股分析流程 ====================
else:
    with st.spinner(f"正在獲取 {symbol_input} 的資料..."):
        company_profile = get_company_profile(symbol_input, fmp_api_key)
        company_trades = get_insider_trading_by_symbol(symbol_input, fmp_api_key)

    insider_trades = []
    if cik_input:
        with st.spinner("正在獲取內部人交易記錄..."):
            insider_trades = get_insider_trading_by_cik(cik_input, fmp_api_key)

    # ── 創建美股頁籤 ──
    tab1, tab2 = st.tabs(["📊 公司交易明細", "👤 內部人交易明細"])

    # ── 頁籤 1: 公司交易明細 ──
    with tab1:
        if company_profile:
            st.subheader(f"📊 {symbol_input} - {company_profile.get('companyName', 'N/A')}")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("當前價格", f"${company_profile.get('price', 0):.2f}")
            with col2:
                sector_info = company_profile.get('sector', company_profile.get('industry', 'N/A'))
                st.metric("產業", sector_info)
            with col3:
                # ✅ 修正：使用 marketCap 而非 mktCap
                market_cap = company_profile.get('marketCap', 0)
                if market_cap > 1e12:
                    st.metric("市值", f"${market_cap/1e12:.2f}T")
                elif market_cap > 1e9:
                    st.metric("市值", f"${market_cap/1e9:.2f}B")
                else:
                    st.metric("市值", f"${market_cap/1e6:.2f}M")
        else:
            st.subheader(f"📊 {symbol_input}")

        st.markdown("---")

        if not company_trades:
            st.warning(f"⚠️ 未找到 {symbol_input} 的內部人交易記錄")
        else:
            st.info(f"📅 顯示最近 {len(company_trades)} 筆交易記錄")
            df_company = process_insider_data(company_trades)

            if not df_company.empty:
                st.subheader("📋 內部人交易明細")
                display_df = create_transaction_table(df_company)

                st.dataframe(
                    display_df,
                    column_config={
                        '交易日期': st.column_config.DateColumn('交易日期', format='YYYY-MM-DD'),
                        '內部人代碼': st.column_config.TextColumn(
                            '內部人代碼',
                            help='複製此代碼到左側輸入框，可查詢該內部人的所有交易'
                        ),
                        'SEC_URL': st.column_config.LinkColumn(
                            'SEC FORM 4',
                            help='點擊查看 SEC 官方申報文件',
                            display_text='🔗 查看'
                        )
                    },
                    use_container_width=True,
                    height=500,
                    hide_index=True
                )

                st.info("💡 提示：複製「內部人代碼」到左側輸入框，切換到「內部人交易明細」頁籤可查詢該內部人的所有交易")

                st.markdown("---")
                csv_data = display_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 下載公司交易明細 CSV",
                    data=csv_data,
                    file_name=f"insider_trading_{symbol_input}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )

    # ── 頁籤 2: 內部人交易明細 ──
    with tab2:
        if not cik_input:
            st.info("ℹ️ 請在左側輸入內部人 CIK")
            st.markdown("""
### 💡 如何使用

1. 切換到「公司交易明細」頁籤
2. 從表格中找到想查詢的內部人
3. 複製該內部人的「內部人代碼」
4. 貼到左側的「內部人 CIK」輸入框
5. 點擊「執行分析」
6. 返回此頁籤查看結果

**範例**：
- Tim Cook (Apple CEO) 的 CIK: `0001214156`
- Satya Nadella (Microsoft CEO) 的 CIK: `0001618159`
            """)
        elif not insider_trades:
            st.warning(f"⚠️ 未找到 CIK {cik_input} 的交易記錄")
        else:
            insider_name = insider_trades[0].get('reportingName', 'N/A')
            st.subheader(f"👤 {insider_name} 的所有交易記錄")
            st.info(f"📅 顯示最近 {len(insider_trades)} 筆交易記錄 | CIK: {cik_input}")

            st.markdown("---")
            df_insider = process_insider_data(insider_trades)

            if not df_insider.empty:
                st.subheader("📋 交易明細")
                display_df = create_transaction_table(df_insider)

                st.dataframe(
                    display_df,
                    column_config={
                        '交易日期': st.column_config.DateColumn('交易日期', format='YYYY-MM-DD'),
                        '內部人代碼': st.column_config.TextColumn('內部人代碼'),
                        'SEC_URL': st.column_config.LinkColumn(
                            'SEC FORM 4',
                            help='點擊查看 SEC 官方申報文件',
                            display_text='🔗 查看'
                        )
                    },
                    use_container_width=True,
                    height=500,
                    hide_index=True
                )

                st.markdown("---")
                st.subheader("📊 交易統計")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("總交易筆數", f"{len(df_insider)} 筆")
                with col2:
                    buy_count = len(df_insider[df_insider['交易類型'].str.contains('P', na=False)])
                    st.metric("買入相關", f"{buy_count} 筆")
                with col3:
                    sell_count = len(df_insider[df_insider['交易類型'].str.contains('S', na=False)])
                    st.metric("賣出相關", f"{sell_count} 筆")
                with col4:
                    unique_companies = df_insider['股票代碼'].nunique()
                    st.metric("涉及公司", f"{unique_companies} 家")

                st.markdown("---")
                csv_data = display_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 下載內部人交易明細 CSV",
                    data=csv_data,
                    file_name=f"insider_trading_{cik_input}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )

    # ── 美股：交易類型說明（頁籤外共用）──
    st.markdown("---")
    st.markdown("---")

    with st.expander("📚 美股交易類型說明 - 點擊展開", expanded=False):
        st.markdown("以下是 SEC Form 4 中可能出現的交易類型及其含義：")

        st.markdown("### ⭐⭐⭐⭐⭐ 重要參考")
        high_value_codes = {k: v for k, v in TRANSACTION_CODES.items() if '⭐⭐⭐⭐⭐' in v['價值']}
        for code, info in high_value_codes.items():
            st.markdown(f"**{code}** | {info['中文']}  \n💡 {info['說明']}")

        st.markdown("### ⭐⭐⭐ 需要分析")
        medium_value_codes = {k: v for k, v in TRANSACTION_CODES.items() if v['價值'] == '⭐⭐⭐'}
        for code, info in medium_value_codes.items():
            st.markdown(f"**{code}** | {info['中文']}  \n💡 {info['說明']}")

        st.markdown("### ⭐⭐ 補充參考")
        ref_value_codes = {k: v for k, v in TRANSACTION_CODES.items() if v['價值'] == '⭐⭐'}
        for code, info in ref_value_codes.items():
            st.markdown(f"**{code}** | {info['中文']}  \n💡 {info['說明']}")

        st.markdown("### ⭐ 技術性交易（通常可忽略）")
        low_value_codes = {k: v for k, v in TRANSACTION_CODES.items() if v['價值'] == '⭐'}
        for code, info in low_value_codes.items():
            st.markdown(f"**{code}** | {info['中文']}  \n💡 {info['說明']}")

        st.markdown("### ❌ 無分析價值（可忽略）")
        no_value_codes = {k: v for k, v in TRANSACTION_CODES.items() if v['價值'] == '❌'}
        for code, info in no_value_codes.items():
            st.markdown(f"**{code}** | {info['中文']}  \n💡 {info['說明']}")

        st.markdown("---")
        st.markdown("### 📖 完整交易類型清單")
        codes_data = []
        for code, info in TRANSACTION_CODES.items():
            codes_data.append({
                '代碼': code,
                '中文名稱': info['中文'],
                '交易類別': info['類別'],
                '說明': info['說明']
            })
        codes_df = pd.DataFrame(codes_data)
        st.dataframe(codes_df, use_container_width=True, hide_index=True)

        codes_csv = codes_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下載交易類型清單 CSV",
            data=codes_csv,
            file_name="transaction_codes.csv",
            mime="text/csv"
        )

        st.markdown("""
---
### 💡 如何判斷計劃性變現 vs 主動交易

**計劃性變現的特徵**（正常薪酬兌現）：
- 在 ±2 天內出現 M-Exempt + F-InKind + S-Sale 的組合
- 這是公司股權激勵計劃到期的正常流程

**主動交易**：
- 單純的 P-Purchase 或 S-Sale，沒有 M-Exempt 和 F-InKind
- 代表內部人主動決定買入或賣出，但仍然需要到 SEC 官網確認其交易資訊，請勿單獨使用此資訊判斷進出場訊號
- 確認方式請依照課程影片中的閱讀 SEC FORM 4 教學判別

建議：查看同一內部人在相近日期（±2天）的其他交易來判斷。
        """)
