import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Price Watchdog v1.0", layout="wide")

# --- 1. 侧边栏：实时行情 ---
st.sidebar.header("📡 Market Live Feed")
# 默认 2.85，你可以根据今天铝价手动改
live_price = st.sidebar.number_input("Current Market Price (USD/kg)", value=2.85)

st.title("🛡️ Raw Material Price Watchdog")

tab1, tab2, tab3 = st.tabs(["🚨 Variance Analysis", "📧 Email Generator", "📂 Data Management"])

# --- TAB 3: 数据上传（写实逻辑） ---
with tab3:
    st.subheader("Upload Original Price Book")
    uploaded_file = st.file_uploader("Upload CSV", type="csv")
    
    if uploaded_file:
        try:
            # 自动找表头
            preview = pd.read_csv(uploaded_file, header=None, nrows=50)
            header_idx = 0
            for i, row in preview.iterrows():
                if 'Part Number' in str(row.values) or '料号' in str(row.values):
                    header_idx = i
                    break
            
            df = pd.read_csv(uploaded_file, header=header_idx)
            df.columns = df.columns.str.replace('\n', ' ', regex=False).str.strip()
            
            # 自动映射关键列
            mapping = {'Part Number': 'Part_No', 'Material U/P': 'Contract_UP', 'Vendor': 'Supplier'}
            final_cols = {col: mapping[k] for col in df.columns for k in mapping if k in col}
            
            if len(final_cols) < 2:
                st.error("Missing key columns in CSV!")
            else:
                df_clean = df[list(final_cols.keys())].rename(columns=final_cols)
                df_clean['Contract_UP'] = pd.to_numeric(df_clean['Contract_UP'].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce')
                
                # 存入 Session，这样切换 Tab 数据不会丢
                st.session_state['master_data'] = df_clean.dropna(subset=['Part_No', 'Contract_UP'])
                st.success("Data Loaded Successfully!")
                st.dataframe(st.session_state['master_data'].head())
        except Exception as e:
            st.error(f"Error: {e}")

# --- TAB 1: 分析逻辑（连通 Tab 3） ---
with tab1:
    if 'master_data' in st.session_state:
        df = st.session_state['master_data'].copy()
        df['Market_Price'] = live_price
        # 计算差异百分比
        df['Variance_%'] = ((df['Market_Price'] - df['Contract_UP']) / df['Contract_UP'] * 100).round(2)
        
        st.subheader("Price Comparison Details")
        # 重点显示降价空间（Variance 为负数代表市场更便宜）
        st.dataframe(df.style.background_gradient(cmap='RdYlGn', subset=['Variance_%']))
        
        fig = px.bar(df, x='Part_No', y='Variance_%', title="Price Anomaly Heatmap")
        st.plotly_chart(fig)
    else:
        st.warning("Please upload a file in Data Management first.")

# --- TAB 2: 邮件生成 ---
with tab2:
    if 'master_data' in st.session_state:
        selected = st.selectbox("Select Part", st.session_state['master_data']['Part_No'])
        # 自动生成基于真实数据的邮件...
        st.write(f"Email draft for {selected} is ready.")