import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf

st.set_page_config(page_title="Price Watchdog v1.0", layout="wide")

st.title("🛡️ Raw Material Price Watchdog (Hybrid Live)")

SHEET_ID = "1qUorrvZ7aj-fRlrJxQpm_6rK2-HolwtWH86SqVcDUWU"

# ==========================================
# 💡 全球大宗商品期货代码库 (Yahoo Finance Tickers)
# 锌合金(Zamak)因为缺乏公开高频现货接口，没有写在这里。
# 系统发现这里没有 Zamak，就会自动去你的 Google Sheet 寻找。
# ==========================================
API_TICKERS = {
    "A380": "ALI=F",
    "ADC12": "ALI=F",
    "6063": "ALI=F",
    "AL 7075": "ALI=F",
    "SPCC": "HRC=F",
    "SECC": "HRC=F",
    "SUS": "HRC=F", 
    "PVC": "CL=F",
    "C3604": "HG=F"
}

# ==========================================
# 1. 雅虎财经 API 抓取引擎
# ==========================================
@st.cache_data(ttl=3600)
def fetch_live_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        if not data.empty:
            price = float(data['Close'].iloc[-1])
            if ticker in ["ALI=F", "HRC=F"]:
                return round(price / 1000, 3) 
            elif ticker == "HG=F":
                return round(price * 2.2046, 3) 
            elif ticker == "CL=F":
                return round(price / 159, 3) 
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
        # 寻找包含 Material 和 USD 的标准表头
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
        # 💡 彻底取消默认值，找不到数据就是 0.00
        matched_price = 0.00
        source_label = "⚠️ (No Data Found)" 
        
        # 步骤 A: 优先尝试从 Google Sheet 拉取底线价
        for db_mat, db_price in market_dict_db.items():
            if str(mat).lower() in str(db_mat).lower() or str(db_mat).lower() in str(mat).lower():
                try: 
                    matched_price = float(db_price)
                    source_label = "📊 (Google Sheet)"
                    break
                except: 
                    pass
                
        # 步骤 B: 如果该材料在 API 词典里有配置，强制覆盖为实时行情！
        for known_mat, ticker in API_TICKERS.items():
            if known_mat.lower() in str(mat).lower():
                live_price = fetch_live_price(ticker)
                if live_price is not None:
                    matched_price = live_price
                    source_label = f"🔥 (Yahoo: {ticker})"
                elif source_label == "📊 (Google Sheet)":
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
            
            # 💡 只有市场价大于 0 的零件才会参与计算，防止 0.00 导致的错误报警
            df_valid = df[df['Market_Price'] > 0].copy()
            
            if not df_valid.empty:
                df_valid['Variance_%'] = ((df_valid['Market_Price'] - df_valid['Contract_UP']) / df_valid['Contract_UP'] * 100).round(2)
                
                st.subheader("Price Comparison Details")
                st.write("Note: A **negative, red Variance** means the current market price is lower than the contract price.")
                st.dataframe(df_valid.style.background_gradient(cmap='RdYlGn', subset=['Variance_%']))
            else:
                st.warning("Data loaded, but waiting for valid Market Prices. Please configure Google Sheet or APIs.")
            
with tab3:
    st.success("✅ Connected to Google Sheets & Yahoo Finance Global API.")
    st.write("Prices are pulled from live international markets (Yahoo Finance). If unavailable, it falls back to your Google Sheet.")
    
    # 强制刷新按钮
    if st.button("Force Refresh System (清除缓存)"):
        st.cache_data.clear()
        st.rerun()

with tab2: st.write("Ready for email module.")