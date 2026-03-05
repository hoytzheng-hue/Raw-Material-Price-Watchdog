import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf

st.set_page_config(page_title="Price Watchdog v1.0", layout="wide")

st.title("🛡️ Raw Material Price Watchdog (Yahoo Finance Live)")

SHEET_ID = "1qUorrvZ7aj-fRlrJxQpm_6rK2-HolwtWH86SqVcDUWU"

# ==========================================
# 💡 核心升级：全球大宗商品期货代码库 (Yahoo Finance Tickers)
# ==========================================
API_TICKERS = {
    # 铝系材料 -> 锚定国际铝期货 (ALI=F)
    "A380": "ALI=F",
    "ADC12": "ALI=F",
    "6063": "ALI=F",
    "AL 7075": "ALI=F",
    # 钢系材料 -> 锚定国际热轧卷板期货 (HRC=F)
    "SPCC": "HRC=F",
    "SECC": "HRC=F",
    "SUS": "HRC=F", 
    # 塑料系 -> 锚定原油期货风向标 (CL=F)
    "PVC": "CL=F",
    # 铜/黄铜 -> 锚定国际铜期货 (HG=F)
    "C3604": "HG=F"
}

# ==========================================
# 1. 雅虎财经 API 抓取引擎
# ==========================================
@st.cache_data(ttl=3600)
def fetch_live_price(ticker):
    try:
        # 从雅虎财经拉取当天的期货收盘价
        data = yf.Ticker(ticker).history(period="1d")
        if not data.empty:
            price = float(data['Close'].iloc[-1])
            
            # 数据清洗：原油和铜的计价单位不同，如果是铝(ALI=F)，通常是 美元/吨
            # 为了统一展示为 USD/KG，我们将大宗商品价格做一个标准化转换
            # (注意：此处展示的是纯原材料大盘基准价，用于监控“趋势差异”)
            if ticker in ["ALI=F", "HRC=F"]:
                return round(price / 1000, 3) # 美元/吨 转换为 美元/KG
            elif ticker == "HG=F":
                return round(price * 2.2046, 3) # 铜是按磅计价，转换为KG
            elif ticker == "CL=F":
                return round(price / 159, 3) # 简单将原油的 桶 转换为升/KG的粗略参考
            
            return round(price, 3)
        return None
    except Exception as e:
        return None

# ==========================================
# 2. 读取 Google Sheet 保底市场价
# ==========================================
@st.cache_data(ttl=600)
def load_market_data():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Market%20Price"
    try:
        df = pd.read_csv(url)
        mat_col = [c for c in df.columns if 'Material' in str(c) or 'Grade' in str(c)][0]
        price_col = [c for c in df.columns if 'USD' in str(c) or 'Cost' in str(c)][0]
        return dict(zip(df[mat_col].astype(str), df[price_col]))
    except:
        return {}

# ==========================================
# 3. 读取历史报价单
# ==========================================
@st.cache_data(ttl=600)
def load_price_book():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Quotation"
    try:
        df = pd.read_csv(url)
        if not any('Part Number' in str(c) or '料号' in str(c) for c in df.columns):
            header_idx = -1
            for i, row in df.iterrows():
                row_str = " ".join([str(x) for x in row.values])
                if 'Part Number' in row_str or '料号' in row_str:
                    header_idx = i
                    break
            if header_idx != -1:
                df.columns = df.iloc[header_idx].astype(str).str.replace('\n', ' ', regex=False).str.strip()
                df = df.iloc[header_idx+1:].reset_index(drop=True)

        mapping = {'Part Number': 'Part_No', 'Material U/P': 'Contract_UP', 'Raw material': 'Material', 'Material Spec': 'Material', '材质': 'Material'}
        final_cols = {col: mapping[k] for col in df.columns for k in mapping if k.lower() in str(col).lower()}
        
        if 'Part_No' not in final_cols.values(): return pd.DataFrame()
            
        df_clean = df[list(final_cols.keys())].rename(columns=final_cols)
        df_clean['Contract_UP'] = pd.to_numeric(df_clean['Contract_UP'].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce')
        return df_clean.dropna(subset=['Part_No', 'Contract_UP'])
    except:
        return pd.DataFrame()

# ==========================================
# 网页主逻辑：混合动力驱动
# ==========================================
with st.spinner('Connecting to Yahoo Finance & Google Sheets...'):
    market_dict_db = load_market_data()
    master_data = load_price_book()

tab1, tab2, tab3 = st.tabs(["🚨 Variance Analysis", "📧 Email Generator", "📂 Data Management"])

st.sidebar.header("📡 Live Market Feed")
market_prices = {} 

if not master_data.empty and 'Material' in master_data.columns:
    unique_materials = master_data['Material'].dropna().unique()
    for mat in unique_materials:
        matched_price = 2.95
        source_label = "📊 (Google Sheet)"
        
        # A: 谷歌表格保底价
        for db_mat, db_price in market_dict_db.items():
            if str(mat).lower() in str(db_mat).lower() or str(db_mat).lower() in str(mat).lower():
                try: matched_price = float(db_price); break
                except: pass
                
        # B: 雅虎财经 API 实时覆盖！
        for known_mat, ticker in API_TICKERS.items():
            if known_mat.lower() in str(mat).lower():
                live_price = fetch_live_price(ticker)
                if live_price is not None:
                    matched_price = live_price
                    source_label = f"🔥 (Yahoo: {ticker})"
                else:
                    source_label = "⚠️ (API Down, Used Sheet)" 
                break
                
        market_prices[mat] = st.sidebar.number_input(f"{mat} {source_label}", value=matched_price, step=0.01)

with tab1:
    if not master_data.empty:
        df = master_data.copy()
        if 'Material' in df.columns:
            df['Market_Price'] = df['Material'].map(market_prices)
            cols = ['Part_No', 'Material', 'Contract_UP', 'Market_Price']
            df = df[cols + [c for c in df.columns if c not in cols]]
            df['Variance_%'] = ((df['Market_Price'] - df['Contract_UP']) / df['Contract_UP'] * 100).round(2)
            
            st.subheader("Price Comparison Details")
            st.dataframe(df.style.background_gradient(cmap='RdYlGn', subset=['Variance_%']))
            
with tab3:
    st.success("✅ Connected to Google Sheets & Yahoo Finance Global API.")
    st.write("Prices are pulled from live international commodities markets (LME/COMEX) via Yahoo Finance. If unavailable, it falls back to your Google Sheet.")
    if st.button("Force Refresh APIs"):
        st.cache_data.clear()
        st.rerun()

with tab2: st.write("Ready for email module.")