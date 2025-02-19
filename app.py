import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import json
import io
import asyncio
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from threading import Thread
import requests
from openai import OpenAI
from google.oauth2.service_account import Credentials
import gspread

# Configuração inicial do Streamlit
st.set_page_config(
    page_title="Assistente Financeiro IA",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicialização do Flask
flask_app = Flask(__name__)
CORS(flask_app)

# Definição das categorias estilo Cerbasi
CATEGORIAS = {
    "moradia": {
        "subcategorias": [
            "aluguel",
            "condomínio",
            "luz",
            "água",
            "gás",
            "internet",
            "iptu",
            "manutenção"
        ]
    },
    "alimentacao": {
        "subcategorias": [
            "supermercado",
            "restaurante",
            "delivery",
            "padaria"
        ]
    },
    "transporte": {
        "subcategorias": [
            "combustível",
            "estacionamento",
            "manutenção",
            "uber/99",
            "transporte público",
            "ipva"
        ]
    },
    "saude": {
        "subcategorias": [
            "plano de saúde",
            "medicamentos",
            "consultas",
            "exames",
            "academia"
        ]
    },
    "educacao": {
        "subcategorias": [
            "mensalidade",
            "material",
            "cursos",
            "livros"
        ]
    },
    "lazer": {
        "subcategorias": [
            "streaming",
            "restaurantes",
            "cinema/teatro",
            "viagens",
            "hobbies"
        ]
    },
    "financeiro": {
        "subcategorias": [
            "investimentos",
            "seguros",
            "empréstimos",
            "cartão de crédito"
        ]
    }
}

class ConfigManager:
    """Gerencia as configurações e secrets do aplicativo"""
    @staticmethod
    def get_secret(key: str, default: str = None) -> str:
        """Recupera um secret de forma segura"""
        try:
            return st.secrets.secrets[key]
        except Exception as e:
            if default:
                return default
            st.error(f"Erro ao acessar {key}: {str(e)}")
            return None

    @staticmethod
    def send_whatsapp_message(phone_number: str, message: str) -> bool:
        """Envia mensagem usando a API do WhatsApp"""
        try:
            token = ConfigManager.get_secret("WHATSAPP_TOKEN")
            phone_number_id = ConfigManager.get_secret("PHONE_NUMBER_ID")
            
            url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            data = {
                "messaging_product": "whatsapp",
                "to": phone_number,
                "type": "text",
                "text": {"body": message}
            }
            
            response = requests.post(url, headers=headers, json=data)
            return response.status_code == 200
            
        except Exception as e:
            st.error(f"Erro ao enviar mensagem WhatsApp: {str(e)}")
            return False

    @staticmethod
    def initialize_openai():
        """Inicializa a API da OpenAI"""
        openai_key = ConfigManager.get_secret("OPENAI_API_KEY")
        return OpenAI(api_key=openai_key) if openai_key else None

class SheetsManager:
    """Gerencia as operações com Google Sheets"""
    def __init__(self):
        self.credentials = Credentials.from_service_account_info(
            st.secrets.secrets["google_credentials"],
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
        )
        self.client = gspread.authorize(self.credentials)

    def create_new_sheet(self, user_name: str) -> str:
        """Cria uma nova planilha para o usuário"""
        try:
            # Criar planilha
            spreadsheet = self.client.create(f"Finanças - {user_name}")
            
            # Configurar primeira aba
            worksheet = spreadsheet.sheet1
            worksheet.update_title("Registros")
            
            # Configurar cabeçalhos
            headers = ["Data", "Categoria", "Subcategoria", "Valor", "Descrição"]
            worksheet.update('A1:E1', [headers])
            
            # Formatar cabeçalhos
            worksheet.format('A1:E1', {
                "backgroundColor": {"red": 0.8, "green": 0.8, "blue": 0.8},
                "textFormat": {"bold": True}
            })
            
            # Compartilhar planilha (opcional)
            spreadsheet.share(None, perm_type='anyone', role='reader')
            
            return spreadsheet.url
            
        except Exception as e:
            st.error(f"Erro ao criar planilha: {str(e)}")
            return None

    def save_transaction(self, sheet_id: str, transaction: dict):
        """Salva uma nova transação na planilha"""
        try:
            sheet = self.client.open_by_key(sheet_id)
            worksheet = sheet.sheet1
            
            # Preparar dados
            row = [
                transaction['data'].strftime("%Y-%m-%d %H:%M:%S"),
                transaction['categoria'],
                transaction.get('subcategoria', ''),
                transaction['valor'],
                transaction['descricao']
            ]
            
            # Adicionar linha
            worksheet.append_row(row)
            
        except Exception as e:
            st.error(f"Erro ao salvar transação: {str(e)}")

    def get_transactions(self, sheet_id: str) -> pd.DataFrame:
        """Recupera todas as transações da planilha"""
        try:
            sheet = self.client.open_by_key(sheet_id)
            worksheet = sheet.sheet1
            
            # Pegar todos os dados
            data = worksheet.get_all_records()
            
            # Converter para DataFrame
            df = pd.DataFrame(data)
            if not df.empty:
                df['Data'] = pd.to_datetime(df['Data'])
            
            return df
            
        except Exception as e:
            st.error(f"Erro ao recuperar transações: {str(e)}")
            return pd.DataFrame()

class UserManager:
    """Gerencia os usuários e seus estados"""
    def __init__(self):
        if 'users' not in st.session_state:
            st.session_state.users = {}

    def get_user_state(self, phone_number: str) -> dict:
        """Retorna o estado atual do usuário"""
        if phone_number not in st.session_state.users:
            st.session_state.users[phone_number] = {
                'status': 'new',  # new, pending_name, pending_email, active
                'name': None,
                'email': None,
                'sheet_id': None
            }
        return st.session_state.users[phone_number]

    def update_user_state(self, phone_number: str, updates: dict):
        """Atualiza o estado do usuário"""
        if phone_number in st.session_state.users:
            st.session_state.users[phone_number].update(updates)

    def handle_user_message(self, phone_number: str, message: str) -> str:
        """Processa mensagem baseado no estado do usuário"""
        user = self.get_user_state(phone_number)
        
        if user['status'] == 'new':
            user['status'] = 'pending_name'
            self.update_user_state(phone_number, user)
            return """👋 Olá! Bem-vindo ao Assistente Financeiro!

Para começar, preciso de algumas informações:

Por favor, me diga seu nome completo:"""

        elif user['status'] == 'pending_name':
            user['name'] = message
            user['status'] = 'pending_email'
            self.update_user_state(phone_number, user)
            return f"""Obrigado, {user['name']}! 

Agora, por favor, me informe seu e-mail:"""

        elif user['status'] == 'pending_email':
            if '@' in message and '.' in message:  # Validação básica de email
                user['email'] = message
                user['status'] = 'active'
                
                # Criar planilha para o usuário
                try:
                    sheets_manager = SheetsManager()
                    sheet_url = sheets_manager.create_new_sheet(user['name'])
                    user['sheet_id'] = sheet_url
                    self.update_user_state(phone_number, user)
                    
                    return f"""✨ Tudo pronto, {user['name']}!

Sua planilha foi criada com sucesso! 
Acesse aqui: {sheet_url}

Para registrar gastos, você pode:
1. Enviar mensagens como "Gastei 50 no almoço"
2. Enviar fotos de comprovantes/notas
3. Enviar extratos em CSV/PDF

Para ver relatórios, digite "relatorio" a qualquer momento.

Posso ajudar com mais alguma coisa?"""
                except Exception as e:
                    return "Desculpe, houve um erro ao criar sua planilha. Por favor, tente novamente mais tarde."
            else:
                return "Por favor, forneça um e-mail válido."

        return "Como posso ajudar?"

class DataManager:
    """Gerencia o armazenamento e manipulação dos dados"""
    def __init__(self, sheet_id: str = None):
        self.sheet_id = sheet_id
        self.sheets_manager = SheetsManager() if sheet_id else None

    def adicionar_gasto(self, gasto: dict) -> bool:
        """Adiciona um novo gasto"""
        try:
            if self.sheets_manager and self.sheet_id:
                self.sheets_manager.save_transaction(self.sheet_id, gasto)
            return True
        except Exception as e:
            st.error(f"Erro ao adicionar gasto: {str(e)}")
            return False

    def get_dataframe(self) -> pd.DataFrame:
        """Retorna o DataFrame com todos os gastos"""
        try:
            if self.sheets_manager and self.sheet_id:
                return self.sheets_manager.get_transactions(self.sheet_id)
            return pd.DataFrame()
        except Exception as e:
            st.error(f"Erro ao recuperar dados: {str(e)}")
            return pd.DataFrame()

    def has_data(self) -> bool:
        """Verifica se existem dados registrados"""
        return not self.get_dataframe().empty

class AIFinanceAssistant:
    """Assistente de IA para processamento de mensagens e análise financeira"""
    def __init__(self, openai_client):
        self.client = openai_client

    def processar_mensagem(self, mensagem: str) -> dict:
        """Processa mensagem do usuário usando GPT-4"""
        if not self.client:
            return {
                "sucesso": False,
                "mensagem": "Cliente OpenAI não inicializado. Verifique as configurações."
            }

        system_prompt = f"""Você é um assistente financeiro especializado em:
        1. Extrair informações de gastos de mensagens em linguagem natural
        2. Categorizar gastos apropriadamente usando as categorias definidas
        3. Identificar valores e descrições

        Categorias e subcategorias disponíveis:
        {json.dumps(CATEGORIAS, indent=2)}

        Retorne apenas um JSON com os campos:
        {{
            "categoria": string,
            "subcategoria": string,
            "valor": float,
            "descricao": string,
            "sucesso": boolean,
            "mensagem": string
        }}"""

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

    def analyze_image(self, image_content: bytes) -> dict:
        """Analisa imagem usando GPT-4 Vision"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um especialista em análise de extratos bancários e comprovantes. Identifique os gastos na imagem."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Identifique os gastos nesta imagem e retorne um JSON com uma lista de gastos encontrados, incluindo valor, descrição e categoria."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_content.decode('utf-8')}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro ao analisar imagem: {str(e)}"
            }

    def analyze_bank_csv(self, df: pd.DataFrame) -> list:
        """Analisa CSV do banco e identifica transações"""
        try:
            # Converter DataFrame para texto para enviar ao GPT-4
            csv_text = df.to_string()
            
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {
                        "role": "system",
                        "content": f"""Você é um especialista em análise de extratos bancários.
                        Use estas categorias para classificar as transações:
                        {json.dumps(CATEGORIAS, indent=2)}
                        """
                    },
                    {
                        "role": "user",
                        "content": f"Analise este extrato bancário e identifique os gastos:\n\n{csv_text}"
                    }
                ],
                response_format={"type": "json_object"}
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            return []

    def analisar_padroes(self, df: pd.DataFrame) -> str:
        """Análise avançada dos padrões de gastos"""
        if not self.client:
            return "Cliente OpenAI não inicializado. Verifique as configurações."

        if df.empty:
            return "Ainda não há dados suficientes para análise."

        resumo_categorias = df.groupby(['categoria', 'subcategoria'])['valor'].agg(['sum', 'count', 'mean'])
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
        """Gera relatório mensal com visualizações"""
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
    """Testa a funcionalidade do webhook"""
    def __init__(self):
        self.base_url = ConfigManager.get_secret('STREAMLIT_URL', 'seu-app-name.streamlit.app')
    
    def render_test_interface(self):
        """Renderiza a interface de teste do webhook"""
        st.subheader("🔧 Teste do Webhook")
        
        test_message = st.text_input(
            "Mensagem de teste",
            value="Gastei 50 reais no almoço"
        )
        
        if st.button("🔄 Testar Webhook"):
            self.test_webhook(test_message)
    
    def test_webhook(self, message: str):
        """Executa o teste do webhook"""
        try:
            webhook_url = f"https://{self.base_url}/webhook"
            
            test_data = {
                "object": "whatsapp_business_account",
                "entry": [{
                    "id": ConfigManager.get_secret("WHATSAPP_BUSINESS_ACCOUNT_ID", "TEST_ID"),
                    "changes": [{
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": ConfigManager.get_secret("PHONE_NUMBER_ID", "TEST_NUMBER"),
                                "phone_number_id": ConfigManager.get_secret("PHONE_NUMBER_ID", "TEST_ID")
                            },
                            "messages": [{
                                "from": ConfigManager.get_secret("PHONE_NUMBER_ID", "TEST_NUMBER"),
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

# Rota única para o webhook
@flask_app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        try:
            verify_token = ConfigManager.get_secret("VERIFY_TOKEN")
            mode = request.args.get('hub.mode')
            token = request.args.get('hub.verify_token')
            challenge = request.args.get('hub.challenge')

            if mode == 'subscribe' and token == verify_token:
                if challenge:
                    return str(challenge), 200
                return "OK", 200
            return "Unauthorized", 403
        except Exception as e:
            st.error(f"Erro na verificação: {str(e)}")
            return str(e), 500
            
    elif request.method == 'POST':
        data = request.json
        try:
            if 'messages' in data and data['messages']:
                message = data['messages'][0]
                numero = message['from']
                texto = message['text']['body']
                
                # Inicializar gerenciadores
                user_manager = UserManager()
                
                # Verificar estado do usuário e processar mensagem
                if user_manager.get_user_state(numero)['status'] != 'active':
                    # Usuário ainda não completou o onboarding
                    resposta = user_manager.handle_user_message(numero, texto)
                    ConfigManager.send_whatsapp_message(numero, resposta)
                else:
                    # Usuário já ativo, processar normalmente
                    user_data = user_manager.get_user_state(numero)
                    data_manager = DataManager(user_data['sheet_id'])
                    ai_assistant = AIFinanceAssistant(ConfigManager.initialize_openai())
                    
                    if texto.lower() == 'relatorio':
                        relatorio, _ = ai_assistant.gerar_relatorio_mensal(
                            data_manager.get_dataframe()
                        )
                        ConfigManager.send_whatsapp_message(numero, relatorio)
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
                        
                        ConfigManager.send_whatsapp_message(numero, mensagem)
            
            return jsonify({"status": "success"}), 200
        except Exception as e:
            st.error(f"Erro no webhook: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500

def render_dashboard(data_manager, ai_assistant):
    """Renderiza o dashboard principal"""
    if data_manager.has_data():
        tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📝 Registros", "🤖 Análise IA"])
        
        with tab1:
            st.subheader("Dashboard Financeiro")
            relatorio, fig = ai_assistant.gerar_relatorio_mensal(data_manager.get_dataframe())
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            st.markdown(relatorio)
            
            # Gráficos extras
            df = data_manager.get_dataframe()
            
            # Gráfico de gastos por subcategoria
            gastos_subcategoria = df.groupby('subcategoria')['valor'].sum().sort_values(ascending=True)
            fig_sub = px.bar(
                gastos_subcategoria,
                orientation='h',
                title='Gastos por Subcategoria'
            )
            st.plotly_chart(fig_sub, use_container_width=True)
            
            # Gráfico de tendência temporal
            df_temporal = df.set_index('data')
            fig_temporal = px.line(
                df_temporal,
                y='valor',
                title='Tendência de Gastos ao Longo do Tempo'
            )
            st.plotly_chart(fig_temporal, use_container_width=True)
            
        with tab2:
            st.subheader("Registros de Gastos")
            st.dataframe(
                data_manager.get_dataframe(),
                column_config={
                    "data": st.column_config.DatetimeColumn("Data", format="DD/MM/YYYY HH:mm"),
                    "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                },
                hide_index=True
            )
            
            # Exportar dados
            if st.button("📥 Exportar Dados"):
                df = data_manager.get_dataframe()
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name="gastos.csv",
                    mime="text/csv"
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
        
        **Você também pode enviar:**
        - 📸 Fotos de comprovantes/extratos
        - 📄 Arquivos CSV do banco
        - 📑 PDFs de faturas
        """)

def main():
    """Função principal do aplicativo"""
    # Inicialização dos componentes
    data_manager = DataManager()
    openai_client = ConfigManager.initialize_openai()
    ai_assistant = AIFinanceAssistant(openai_client)
    webhook_tester = WebhookTester()
    
    # Título principal
    st.title("💰 Assistente Financeiro Inteligente")
    
    # Renderizar sidebar
    with st.sidebar:
        st.title("⚙️ Configurações")
        
        # Status das APIs
        st.subheader("Status das APIs")
        openai_status = "✅ Conectado" if ConfigManager.get_secret("OPENAI_API_KEY") else "❌ Não configurado"
        whatsapp_status = "✅ Conectado" if ConfigManager.get_secret("WHATSAPP_TOKEN") else "❌ Não configurado"
        sheets_status = "✅ Conectado" if "google_credentials" in st.secrets.secrets else "❌ Não configurado"
        
        st.write(f"OpenAI API: {openai_status}")
        st.write(f"WhatsApp API: {whatsapp_status}")
        st.write(f"Google Sheets: {sheets_status}")
        
        # Teste do Webhook
        webhook_tester.render_test_interface()
    
    # Renderizar dashboard
    render_dashboard(data_manager, ai_assistant)

if __name__ == "__main__":
    # Iniciar o servidor webhook em uma thread separada
    flask_thread = Thread(target=lambda: flask_app.run(host='0.0.0.0', port=5000))
    flask_thread.daemon = True
    flask_thread.start()
    
    # Iniciar a aplicação Streamlit
    main()
