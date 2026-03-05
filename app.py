import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Price Watchdog v1.0", layout="wide")

st.title("🛡️ Raw Material Price Watchdog")

tab1, tab2, tab3 = st.tabs(["🚨 Variance Analysis", "📧 Email Generator", "📂 Data Management"])

# ==========================================
# TAB 3: Data Upload & Parsing
# ==========================================
with tab3:
    st.subheader("Upload Original Price Book")
    uploaded_file = st.file_uploader("Upload CSV", type="csv")
    
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
                    '材质': 'Material' # Kept for parsing Chinese CSV headers internally
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
                    st.success("✅ Data and Raw Material specs parsed successfully!")
                    
            except Exception as e:
                st.error(f"Error processing data: {e}")

# ==========================================
# Sidebar: Dynamic Market Board
# ==========================================
st.sidebar.header("📡 Market Live Feed")
market_prices = {} 

if 'master_data' in st.session_state and 'Material' in st.session_state['master_data'].columns:
    st.sidebar.markdown("Please update the **Live Raw Material Prices (USD/kg)** below:")
    
    unique_materials = st.session_state['master_data']['Material'].dropna().unique()
    
    for mat in unique_materials:
        market_prices[mat] = st.sidebar.number_input(f"{mat}", value=2.95, step=0.01)
else:
    st.sidebar.info("Upload a Price Book to automatically generate material-specific price inputs here.")
    universal_price = st.sidebar.number_input("Global Price (USD/kg)", value=2.95, step=0.01)

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
        else:
            df['Market_Price'] = universal_price
            
        df['Variance_%'] = ((df['Market_Price'] - df['Contract_UP']) / df['Contract_UP'] * 100).round(2)
        
        st.subheader("Price Comparison Details")
        st.write("Note: A **negative, red Variance** means the current market price is lower than the contract price, indicating **potential for price reduction**.")
        
        st.dataframe(df.style.background_gradient(cmap='RdYlGn', subset=['Variance_%']))
        
    else:
        st.warning("Please upload a file in Data Management first.")

# ==========================================
# TAB 2: Email Generator
# ==========================================
with tab2:
    st.write("Email generator is ready for the next phase.")