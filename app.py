import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Price Watchdog v1.0", layout="wide")

st.title("🛡️ Raw Material Price Watchdog")

tab1, tab2, tab3 = st.tabs(["🚨 Variance Analysis", "📧 Email Generator", "📂 Data Management"])

# ==========================================
# TAB 3: Data Upload & Parsing (双数据源版)
# ==========================================
with tab3:
    st.subheader("Step 1: Upload Market Price Data (市场行情表)")
    market_file = st.file_uploader("Upload Material.csv", type="csv", key="market_upload")
    
    if market_file:
        try:
            # 读取市场价文件，跳过可能的乱码行或特殊格式
            df_market = pd.read_csv(market_file)
            
            # 找到材料名称列和美金价格列
            mat_col = [c for c in df_market.columns if 'Material' in c or 'Grade' in c][0]
            price_col = [c for c in df_market.columns if 'USD' in c or 'Cost' in c][0]
            
            # 清洗成字典格式，例如: {"ADC12 (Al Alloy)": 2.75}
            market_dict = dict(zip(df_market[mat_col].astype(str), df_market[price_col]))
            st.session_state['market_dict'] = market_dict
            st.success(f"✅ Market data loaded! Found {len(market_dict)} materials.")
        except Exception as e:
            st.error(f"Error parsing market data: {e}")

    st.markdown("---")
    
    st.subheader("Step 2: Upload Original Price Book (历史报价单)")
    uploaded_file = st.file_uploader("Upload Supplier CSV", type="csv", key="pricebook_upload")
    
    if uploaded_file:
        encodings_to_try = ['utf-8', 'gb18030', 'utf-8-sig', 'latin1']
        successful_encoding = None
        preview = None
        
        for enc in encodings_to_try:
            try:
                uploaded_file.seek(0)
                preview = pd.read_csv(uploaded_file, header=None, nrows=50, encoding=enc)
                successful_encoding = enc
                break
            except Exception:
                continue
                
        if successful_encoding is None:
            st.error("Special file encoding detected. Please open the file in Excel and 'Save As -> CSV (UTF-8)' before uploading.")
        else:
            try:
                header_idx = 0
                for i, row in preview.iterrows():
                    row_str = " ".join([str(x) for x in row.values])
                    if 'Part Number' in row_str or '料号' in row_str:
                        header_idx = i
                        break
                
                uploaded_file.seek(0) 
                df = pd.read_csv(uploaded_file, header=header_idx, encoding=successful_encoding)
                df.columns = df.columns.astype(str).str.replace('\n', ' ', regex=False).str.strip()
                
                mapping = {
                    'Part Number': 'Part_No', 
                    'Material U/P': 'Contract_UP', 
                    'Vendor': 'Supplier',
                    'Raw material': 'Material',
                    'Material Spec': 'Material',
                    '材质': 'Material'
                }
                
                final_cols = {}
                for col in df.columns:
                    for k in mapping:
                        if k.lower() in col.lower():
                            final_cols[col] = mapping[k]
                            break 
                
                if 'Part_No' not in final_cols.values():
                    st.error("Cannot find the core column 'Part Number'. Please check your file format.")
                else:
                    df_clean = df[list(final_cols.keys())].rename(columns=final_cols)
                    df_clean['Contract_UP'] = pd.to_numeric(df_clean['Contract_UP'].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce')
                    
                    st.session_state['master_data'] = df_clean.dropna(subset=['Part_No', 'Contract_UP'])
                    st.success("✅ Supplier Price Book parsed successfully!")
                    
            except Exception as e:
                st.error(f"Error processing data: {e}")

# ==========================================
# Sidebar: Dynamic Market Board (智能回填)
# ==========================================
st.sidebar.header("📡 Market Live Feed")
market_prices = {} 
market_dict_db = st.session_state.get('market_dict', {})

if 'master_data' in st.session_state and 'Material' in st.session_state['master_data'].columns:
    st.sidebar.markdown("Auto-matched Market Prices (USD/kg):")
    
    unique_materials = st.session_state['master_data']['Material'].dropna().unique()
    
    for mat in unique_materials:
        # --- 智能模糊匹配逻辑 ---
        matched_price = 2.95 # 如果没找到，给个默认值
        for db_mat, db_price in market_dict_db.items():
            # 如果供应商写的材料名(如ADC12) 包含在 市场材料名(如 ADC12 (Al Alloy)) 中，或者反过来
            if str(mat).lower() in str(db_mat).lower() or str(db_mat).lower() in str(mat).lower():
                try:
                    matched_price = float(db_price)
                    break
                except:
                    pass
        
        # 自动填充匹配到的价格，但用户依然可以在侧边栏手动修改
        market_prices[mat] = st.sidebar.number_input(f"{mat}", value=matched_price, step=0.01)
else:
    st.sidebar.info("Please upload both Market Data and Price Book in the Data Management tab.")

# ==========================================
# TAB 1: Variance Analysis
# ==========================================
with tab1:
    if 'master_data' in st.session_state:
        df = st.session_state['master_data'].copy()
        
        if 'Material' in df.columns:
            df['Market_Price'] = df['Material'].map(market_prices)
            cols = ['Part_No', 'Material', 'Contract_UP', 'Market_Price']
            df = df[cols + [c for c in df.columns if c not in cols]]
            df['Variance_%'] = ((df['Market_Price'] - df['Contract_UP']) / df['Contract_UP'] * 100).round(2)
            
            st.subheader("Price Comparison Details")
            st.write("Note: A **negative, red Variance** means the current market price is lower than the contract price.")
            st.dataframe(df.style.background_gradient(cmap='RdYlGn', subset=['Variance_%']))
        else:
            st.warning("No material info found in Price Book.")
    else:
        st.warning("Please upload a file in Data Management first.")

# ==========================================
# TAB 2: Email Generator
# ==========================================
with tab2:
    st.write("Email generator is ready for the next phase.")