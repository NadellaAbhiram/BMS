import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import io

# Optimize page layout for data density
st.set_page_config(page_title="Fast BMS Viewer", layout="wide")

st.title("⚡ High-Performance Battery Log Analyzer")

# --- Performance Setting ---
with st.sidebar:
    st.header("🚀 Performance Settings")
    # Downsampling slider: 1 = all data, 10 = 1 in 10 points
    downsample_rate = st.slider("Chart Resolution (Higher = Faster)", 1, 100, 10)
    st.caption(f"Plotting 1 out of every {downsample_rate} data points.")

# --- Helper: Fast Parse Log File ---
@st.cache_data
def parse_log_file(uploaded_file):
    # distinct function to keep logic clean and cached
    try:
        content = uploaded_file.getvalue().decode("utf-8", errors='replace').splitlines()
        
        # 1. Quick Scan for Header
        header_row = 0
        file_type = "unknown"
        metadata = {}
        
        for i, line in enumerate(content[:100]):
            if line.startswith("Sample,DateTime"):
                header_row = i
                file_type = "data"
                break
            if "Error Code" in line:
                header_row = i
                file_type = "error"
                break
            # Grab metadata
            if '=' in line and file_type == "unknown":
                parts = line.split('=', 1)
                if len(parts) == 2:
                    metadata[parts[0].strip()] = parts[1].strip()

        if file_type == "unknown":
            return "unknown", {}, None

        # 2. Load CSV
        # We join only the necessary part to avoid memory overhead
        raw_data = "\n".join(content[header_row:])
        df = pd.read_csv(io.StringIO(raw_data))
        
        # Strip whitespace from headers
        df.columns = [c.strip() for c in df.columns]

        # DateTime Optimization: only parse if column exists
        if 'DateTime' in df.columns:
            df['DateTime'] = pd.to_datetime(df['DateTime'], errors='coerce')
        elif 'Time' in df.columns:
             df['Time'] = pd.to_datetime(df['Time'], errors='coerce')

        return file_type, metadata, df

    except Exception as e:
        return "error", {}, None

# --- Main App Logic ---
uploaded_files = st.file_uploader("Upload Log Files", type=['log', 'csv', 'txt'], accept_multiple_files=True)

if uploaded_files:
    # Use tabs for organization
    tab_data, tab_errors = st.tabs(["📈 Data Analysis", "⚠️ Error Logs"])
    
    data_dfs = {}
    error_dfs = {}

    # Process Files
    for file in uploaded_files:
        ftype, meta, df = parse_log_file(file)
        if ftype == "data" and df is not None:
            data_dfs[file.name] = df
        elif ftype == "error" and df is not None:
            error_dfs[file.name] = df

    # --- TAB 1: DATA ANALYSIS ---
    with tab_data:
        if data_dfs:
            selected_file = st.selectbox("Select File", list(data_dfs.keys()))
            df = data_dfs[selected_file]
            
            # APPLY DOWNSAMPLING
            df_plot = df.iloc[::downsample_rate, :]

            # 1. Voltage & Current (WebGL Optimized)
            st.subheader("Voltage & Current Profile")
            fig_vi = go.Figure()
            
            # Use Scattergl for GPU acceleration
            fig_vi.add_trace(go.Scattergl(
                x=df_plot['DateTime'], y=df_plot['Voltage']/1000, 
                name="Voltage (V)", line=dict(color='blue', width=1.5)
            ))
            fig_vi.add_trace(go.Scattergl(
                x=df_plot['DateTime'], y=df_plot['Current']/1000, 
                name="Current (A)", line=dict(color='red', width=1.5), yaxis='y2'
            ))
            
            fig_vi.update_layout(
                height=500,
                yaxis=dict(title="Voltage (V)"),
                yaxis2=dict(title="Current (A)", overlaying='y', side='right'),
                hovermode="x unified",
                margin=dict(l=10, r=10, t=30, b=10)
            )
            st.plotly_chart(fig_vi, use_container_width=True)

            # 2. Cell Balancing (Optimized)
            st.subheader("Cell Voltages")
            cell_cols = [c for c in df.columns if c.startswith('CellVolt')]
            if cell_cols:
                fig_cells = go.Figure()
                for col in cell_cols:
                    fig_cells.add_trace(go.Scattergl(
                        x=df_plot['DateTime'], y=df_plot[col],
                        name=col, mode='lines'
                    ))
                fig_cells.update_layout(height=400, hovermode="x unified", title="Individual Cell Voltages (mV)")
                st.plotly_chart(fig_cells, use_container_width=True)

            # 3. Raw Data (Paginated)
            with st.expander("View Raw Data"):
                st.dataframe(df.head(1000)) # Only show first 1000 rows to prevent lag
        else:
            st.info("Upload a Data Log to view charts.")

    # --- TAB 2: ERROR ANALYSIS ---
    with tab_errors:
        if error_dfs:
            for name, df_err in error_dfs.items():
                st.subheader(f"Errors in {name}")
                
                if 'Error Code' in df_err.columns:
                    # Simple bar chart is fast
                    err_counts = df_err['Error Code'].value_counts().reset_index()
                    err_counts.columns = ['Error Code', 'Count']
                    st.bar_chart(err_counts.set_index('Error Code'))
                    
                st.dataframe(df_err)
        else:
            st.info("Upload an Error Log to view analysis.")

else:
    st.info("Waiting for files...")
