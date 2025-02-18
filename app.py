import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import json
from pathlib import Path
from flask import Flask, request
from threading import Thread
from whatsapp_api_client_python import API
from openai import OpenAI
import requests

# Configuração inicial do Streamlit
st.set_page_config(
    page_title="Assistente Financeiro IA",
    page_icon="💰",
    layout="wide"
)

# Debug: Mostrar todos os secrets disponíveis
st.write("Secrets disponíveis:", st.secrets)

# Tentativa de inicialização com try/except
try:
    whatsapp_token = st.secrets["WHATSAPP_TOKEN"]
    st.write("Token WhatsApp encontrado:", whatsapp_token[:10] + "...")  # Mostra apenas início do token
    whatsapp_api = API(whatsapp_token)
except Exception as e:
    st.error(f"Erro ao inicializar WhatsApp API: {str(e)}")
    whatsapp_api = None

try:
    openai_key = st.secrets["OPENAI_API_KEY"]
    st.write("OpenAI key encontrada:", openai_key[:10] + "...")
    openai_client = OpenAI(api_key=openai_key)
except Exception as e:
    st.error(f"Erro ao inicializar OpenAI: {str(e)}")
    openai_client = None

# Aplicativo Flask para webhook
flask_app = Flask(__name__)

class DataManager:
    def __init__(self):
        if 'df' not in st.session_state:
            st.session_state.df = pd.DataFrame(
                columns=['data', 'categoria', 'valor', 'descricao']
            )
    
    def adicionar_gasto(self, gasto: dict) -> bool:
        try:
            novo_gasto = {
                'data': datetime.now(),
                'categoria': gasto['categoria'].lower(),
                'valor': float(gasto['valor']),
                'descricao': gasto['descricao']
            }
            
            st.session_state.df = pd.concat(
                [st.session_state.df, pd.DataFrame([novo_gasto])],
                ignore_index=True
            )
            
            self.salvar_dados()
            return True
            
        except Exception as e:
            st.error(f"Erro ao adicionar gasto: {str(e)}")
            return False
    
    def get_dataframe(self) -> pd.DataFrame:
        return st.session_state.df
    
    def has_data(self) -> bool:
        return not st.session_state.df.empty
    
    def salvar_dados(self):
        try:
            Path("data").mkdir(exist_ok=True)
            st.session_state.df.to_csv("data/gastos.csv", index=False)
        except Exception as e:
            st.error(f"Erro ao salvar dados: {str(e)}")
    
    def carregar_dados(self):
        try:
            if Path("data/gastos.csv").exists():
                df = pd.read_csv("data/gastos.csv")
                df['data'] = pd.to_datetime(df['data'])
                st.session_state.df = df
        except Exception as e:
            st.error(f"Erro ao carregar dados: {str(e)}")

class AIFinanceAssistant:
    def __init__(self):
        self.client = openai_client
    
    def processar_mensagem(self, mensagem: str) -> dict:
        system_prompt = """Você é um assistente financeiro especializado em:
        1. Extrair informações de gastos de mensagens em linguagem natural
        2. Categorizar gastos apropriadamente
        3. Identificar valores e descrições
        
        Categorias possíveis:
        - alimentacao
        - transporte
        - moradia
        - saude
        - educacao
        - lazer
        - outros
        
        Retorne apenas um JSON com os campos:
        {
            "categoria": string,
            "valor": float,
            "descricao": string,
            "sucesso": boolean,
            "mensagem": string
        }"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": mensagem}
                ],
                response_format={"type": "json_object"}
            )
            
            resultado = json.loads(response.choices[0].message.content)
            return resultado
            
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro ao processar mensagem: {str(e)}"
            }
    
    def analisar_padroes(self, df: pd.DataFrame) -> str:
        if df.empty:
            return "Ainda não há dados suficientes para análise."

        resumo_categorias = df.groupby('categoria')['valor'].agg(['sum', 'count', 'mean'])
        tendencia_mensal = df.groupby(df['data'].dt.strftime('%Y-%m'))['valor'].sum()
        
        contexto = f"""
        Analise os seguintes dados financeiros e forneça insights detalhados:

        Resumo por categoria:
        {resumo_categorias.to_string()}
        
        Tendência mensal:
        {tendencia_mensal.to_string()}
        
        Forneça:
        1. Principais insights sobre os padrões de gastos
        2. Sugestões específicas de economia baseadas nos dados
        3. Identificação de possíveis gastos anormais ou excessivos
        4. Previsões e tendências futuras
        5. Recomendações práticas para melhor gestão financeira
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": "Você é um analista financeiro especializado em finanças pessoais."},
                    {"role": "user", "content": contexto}
                ]
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"Erro na análise: {str(e)}"
    
    def gerar_relatorio_mensal(self, df: pd.DataFrame):
        if df.empty:
            return "Nenhum gasto registrado ainda.", None
        
        mes_atual = datetime.now().month
        df['data'] = pd.to_datetime(df['data'])
        df_mes = df[df['data'].dt.month == mes_atual]
        
        if df_mes.empty:
            return "Nenhum gasto registrado este mês.", None
        
        gastos_categoria = df_mes.groupby('categoria')['valor'].sum()
        total_gasto = df_mes['valor'].sum()
        media_diaria = total_gasto / df_mes['data'].dt.day.nunique()
        
        fig = px.pie(
            values=gastos_categoria.values,
            names=gastos_categoria.index,
            title='Distribuição de Gastos por Categoria'
        )
        fig.update_traces(textposition='inside', textinfo='percent+label')
        
        relatorio = f"""### 📊 Resumo Financeiro do Mês

💰 **Total Gasto:** R$ {total_gasto:.2f}
📅 **Média Diária:** R$ {media_diaria:.2f}

#### Gastos por Categoria:
"""
        
        for categoria, valor in gastos_categoria.items():
            percentual = (valor / total_gasto) * 100
            relatorio += f"- {categoria.title()}: R$ {valor:.2f} ({percentual:.1f}%)\n"
        
        return relatorio, fig

class WebhookTester:
    def __init__(self):
        self.base_url = st.secrets.get('STREAMLIT_URL', 'seu-app-name.streamlit.app')
    
    def render_test_interface(self):
        st.subheader("🔧 Teste do Webhook")
        
        test_message = st.text_input(
            "Mensagem de teste",
            value="Gastei 50 reais no almoço"
        )
        
        if st.button("🔄 Testar Webhook"):
            self.test_webhook(test_message)
    
    def test_webhook(self, message: str):
        try:
            webhook_url = f"https://{self.base_url}/webhook"
            
            test_data = {
                "object": "whatsapp_business_account",
                "entry": [{
                    "id": "TEST_ID",
                    "changes": [{
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "TEST_NUMBER",
                                "phone_number_id": "TEST_ID"
                            },
                            "messages": [{
                                "from": "TEST_NUMBER",
                                "id": "TEST_MESSAGE_ID",
                                "timestamp": str(int(datetime.now().timestamp())),
                                "text": {
                                    "body": message
                                },
                                "type": "text"
                            }]
                        },
                        "field": "messages"
                    }]
                }]
            }
            
            with st.spinner("Testando webhook..."):
                response = requests.post(
                    webhook_url,
                    json=test_data,
                    headers={"Content-Type": "application/json"}
                )
            
            if response.status_code == 200:
                st.success("✅ Webhook respondeu corretamente!")
                try:
                    st.json(response.json())
                except:
                    st.text(response.text)
            else:
                st.error(f"❌ Erro no webhook: {response.status_code}")
                st.text(response.text)
            
        except Exception as e:
            st.error(f"❌ Erro ao testar webhook: {str(e)}")

# Inicialização dos componentes
@st.cache_resource
def initialize_components():
    data_manager = DataManager()
    ai_assistant = AIFinanceAssistant()
    webhook_tester = WebhookTester()
    return data_manager, ai_assistant, webhook_tester

# Rotas do Flask para webhook
@flask_app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    
    try:
        if 'messages' in data and data['messages']:
            mensagem = data['messages'][0]
            numero = mensagem['from']
            texto = mensagem['text']['body']
            
            data_manager, ai_assistant, _ = initialize_components()
            
            if texto.lower() == 'relatorio':
                relatorio, _ = ai_assistant.gerar_relatorio_mensal(
                    data_manager.get_dataframe()
                )
                whatsapp_api.send_message(numero, relatorio)
            else:
                resultado = ai_assistant.processar_mensagem(texto)
                if resultado['sucesso']:
                    if data_manager.adicionar_gasto(resultado):
                        mensagem = f"""✅ Gasto registrado com sucesso!
                        
Categoria: {resultado['categoria']}
Valor: R$ {resultado['valor']:.2f}
Descrição: {resultado['descricao']}"""
                    else:
                        mensagem = "❌ Erro ao salvar o gasto."
                else:
                    mensagem = resultado['mensagem']
                
                whatsapp_api.send_message(numero, mensagem)
        
        return 'OK', 200
    except Exception as e:
        st.error(f"Erro no webhook: {str(e)}")
        return 'Erro', 500

@flask_app.route('/webhook', methods=['GET'])
def verificar():
    if request.args.get('hub.verify_token') == st.secrets["VERIFY_TOKEN"]:
        return request.args.get('hub.challenge')
    return 'Token inválido', 403

def main():
    data_manager, ai_assistant, webhook_tester = initialize_components()
    
    st.title("💰 Assistente Financeiro Inteligente")
    
    with st.sidebar:
        st.title("⚙️ Configurações")
        
        st.subheader("Status das APIs")
        openai_status = "✅ Conectado" if st.secrets.get("OPENAI_API_KEY") else "❌ Não configurado"
        whatsapp_status = "✅ Conectado" if st.secrets.get("WHATSAPP_TOKEN") else "❌ Não configurado"
        
        st.write(f"OpenAI API: {openai_status}")
        st.write(f"WhatsApp API: {whatsapp_status}")
        
        webhook_tester.render_test_interface()
    
    if data_manager.has_data():
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
    # Iniciar o servidor webhook em uma thread separada
    Thread(target=flask_app.run, kwargs={'port': 5000}).start()
