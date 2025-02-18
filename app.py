import streamlit as st
import pandas as pd
from datetime import datetime
import json
from pathlib import Path
from modules.ai_assistant import AIFinanceAssistant
from modules.whatsapp_handler import WhatsAppHandler
from modules.data_manager import DataManager
from modules.webhook_tester import WebhookTester

# Configuração inicial do Streamlit
st.set_page_config(
    page_title="Assistente Financeiro IA",
    page_icon="💰",
    layout="wide"
)

# Inicialização dos componentes
@st.cache_resource
def initialize_components():
    data_manager = DataManager()
    ai_assistant = AIFinanceAssistant()
    whatsapp_handler = WhatsAppHandler(data_manager, ai_assistant)
    webhook_tester = WebhookTester()
    return data_manager, ai_assistant, whatsapp_handler, webhook_tester

def main():
    # Inicialização dos componentes
    data_manager, ai_assistant, whatsapp_handler, webhook_tester = initialize_components()

    # Título principal
    st.title("💰 Assistente Financeiro Inteligente")
    
    # Sidebar
    with st.sidebar:
        st.title("⚙️ Configurações")
        
        # Status das APIs
        st.subheader("Status das APIs")
        openai_status = "✅ Conectado" if st.secrets.get("OPENAI_API_KEY") else "❌ Não configurado"
        whatsapp_status = "✅ Conectado" if st.secrets.get("WHATSAPP_TOKEN") else "❌ Não configurado"
        
        st.write(f"OpenAI API: {openai_status}")
        st.write(f"WhatsApp API: {whatsapp_status}")
        
        # Teste de Webhook
        webhook_tester.render_test_interface()
    
    # Conteúdo principal
    if data_manager.has_data():
        # Tabs para diferentes visualizações
        tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📝 Registros", "🤖 Análise IA"])
        
        with tab1:
            st.subheader("Dashboard Financeiro")
            relatorio, fig = ai_assistant.gerar_relatorio_mensal(data_manager.get_dataframe())
            st.plotly_chart(fig, use_container_width=True)
            st.markdown(relatorio)
            
        with tab2:
            st.subheader("Registros de Gastos")
            st.dataframe(
                data_manager.get_dataframe(),
                column_config={
                    "data": st.column_config.DatetimeColumn("Data", format="DD/MM/YYYY HH:mm"),
                    "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                }
            )
            
        with tab3:
            st.subheader("Análise de IA")
            if st.button("🔄 Gerar Nova Análise"):
                with st.spinner("Analisando seus dados..."):
                    analise = ai_assistant.analisar_padroes(data_manager.get_dataframe())
                    st.markdown(analise)
    
    else:
        st.info("👋 Bem-vindo! Envie mensagens pelo WhatsApp para começar a registrar seus gastos.")
        st.markdown("""
        ### Como usar:
        1. Envie mensagens descrevendo seus gastos
        2. A IA interpretará e categorizará automaticamente
        3. Peça relatórios digitando "relatorio"
        
        **Exemplos de mensagens:**
        - "Gastei 50 reais no almoço hoje"
        - "Paguei a conta de luz de 150 reais"
        - "Comprei um livro por 45,90"
        """)

if __name__ == "__main__":
    main()
