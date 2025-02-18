import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import json
from pathlib import Path
from flask import Flask, request, jsonify
from threading import Thread
import requests
import io
import openai

# Configuração inicial do Streamlit
st.set_page_config(
    page_title="Assistente Financeiro IA",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicialização do Flask
flask_app = Flask(__name__)

class ConfigManager:
    """Gerencia as configurações e secrets do aplicativo"""
    
    @staticmethod
    def get_secret(key: str, default: str = None) -> str:
        """Recupera um secret de forma segura"""
        try:
            return st.secrets[key] if key in st.secrets else default
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
            if not token or not phone_number_id:
                st.error("Token ou ID do número de telefone não configurados.")
                return False
            
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
        """Inicializa a API da OpenAI e retorna o módulo openai configurado"""
        openai_key = ConfigManager.get_secret("OPENAI_API_KEY")
        if openai_key:
            openai.api_key = openai_key
            return openai
        else:
            st.error("Chave da OpenAI não configurada.")
            return None

class DataManager:
    def __init__(self):
        if "df" not in st.session_state:
            st.session_state["df"] = pd.DataFrame(
                columns=["data", "categoria", "valor", "descricao"]
            )
    
    def adicionar_gasto(self, gasto: dict) -> bool:
        try:
            novo_gasto = {
                "data": datetime.now(),
                "categoria": gasto.get("categoria", "").lower(),
                "valor": float(gasto.get("valor", 0)),
                "descricao": gasto.get("descricao", "")
            }
            # Usa o st.session_state como dicionário
            st.session_state["df"] = pd.concat(
                [st.session_state["df"], pd.DataFrame([novo_gasto])],
                ignore_index=True
            )
            self.salvar_dados()
            return True
            
        except Exception as e:
            st.error(f"Erro ao adicionar gasto: {str(e)}")
            return False
    
    def get_dataframe(self) -> pd.DataFrame:
        if "df" not in st.session_state:
            st.session_state["df"] = pd.DataFrame(
                columns=["data", "categoria", "valor", "descricao"]
            )
        return st.session_state["df"]
    
    def has_data(self) -> bool:
        return not self.get_dataframe().empty
    
    def salvar_dados(self):
        try:
            Path("data").mkdir(exist_ok=True)
            st.session_state["df"].to_csv("data/gastos.csv", index=False)
        except Exception as e:
            st.error(f"Erro ao salvar dados: {str(e)}")
    
    def carregar_dados(self):
        try:
            if Path("data/gastos.csv").exists():
                df = pd.read_csv("data/gastos.csv")
                df["data"] = pd.to_datetime(df["data"])
                st.session_state["df"] = df
        except Exception as e:
            st.error(f"Erro ao carregar dados: {str(e)}")

class WhatsAppMessageHandler:
    def __init__(self, ai_assistant, data_manager):
        self.ai_assistant = ai_assistant
        self.data_manager = data_manager

    def download_file(self, file_id):
        """Faz download de arquivo via Media API do WhatsApp"""
        try:
            token = ConfigManager.get_secret("WHATSAPP_TOKEN")
            if not token:
                st.error("Token do WhatsApp não configurado.")
                return None
            url = f"https://graph.facebook.com/v17.0/{file_id}"
            
            headers = {
                "Authorization": f"Bearer {token}",
            }
            
            # Obter URL do arquivo
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                file_data = response.json()
                # Download do arquivo
                file_response = requests.get(file_data.get("url", ""), headers=headers)
                return file_response.content
            return None
        except Exception as e:
            st.error(f"Erro ao baixar arquivo: {str(e)}")
            return None

    def process_image(self, image_id, number):
        """Processa imagem usando OCR e GPT-4 Vision"""
        try:
            image_content = self.download_file(image_id)
            if not image_content:
                return "Erro ao baixar imagem"

            # Usar GPT-4 Vision para analisar a imagem (simulado)
            response = self.ai_assistant.analyze_image(image_content)
            
            # Processar os gastos identificados
            gastos = response.get("gastos", [])
            for gasto in gastos:
                self.data_manager.adicionar_gasto(gasto)
            
            mensagem = f"✅ Identifiquei {len(gastos)} gastos na imagem:\n\n"
            for gasto in gastos:
                mensagem += f"- {gasto['descricao']}: R$ {float(gasto['valor']):.2f} ({gasto['categoria']})\n"
            
            ConfigManager.send_whatsapp_message(number, mensagem)
            return "Imagem processada com sucesso"

        except Exception as e:
            return f"Erro ao processar imagem: {str(e)}"

    def process_document(self, doc_id, number):
        """Processa documentos (CSV, PDF) enviados pelo banco"""
        try:
            doc_content = self.download_file(doc_id)
            if not doc_content:
                return "Erro ao baixar documento"

            # Identificar tipo do arquivo (assumindo que doc_id contenha extensão)
            extension = self.get_file_extension(doc_id)
            
            if extension == "csv":
                # Processar CSV
                df = pd.read_csv(io.StringIO(doc_content.decode("utf-8")))
                gastos = self.ai_assistant.analyze_bank_csv(df)
            elif extension == "pdf":
                # Processar PDF
                gastos = self.ai_assistant.analyze_bank_pdf(doc_content)
            else:
                return "Formato de arquivo não suportado"

            # Adicionar gastos identificados
            for gasto in gastos:
                self.data_manager.adicionar_gasto(gasto)
            
            mensagem = f"✅ Processado {len(gastos)} transações do arquivo:\n\n"
            total = sum(float(gasto['valor']) for gasto in gastos)
            mensagem += f"Total: R$ {total:.2f}\n\n"
            mensagem += "Digite 'relatorio' para ver o resumo completo."
            
            ConfigManager.send_whatsapp_message(number, mensagem)
            return "Documento processado com sucesso"

        except Exception as e:
            return f"Erro ao processar documento: {str(e)}"

    def get_file_extension(self, filename):
        """Obtém a extensão do arquivo"""
        return filename.split(".")[-1].lower()

class AIFinanceAssistant:
    def __init__(self, openai_client):
        self.client = openai_client
    
    def processar_mensagem(self, mensagem: str) -> dict:
        if not self.client:
            return {
                "sucesso": False,
                "mensagem": "Cliente OpenAI não inicializado. Verifique as configurações."
            }

        system_prompt = (
            "Você é um assistente financeiro especializado em:\n"
            "1. Extrair informações de gastos de mensagens em linguagem natural\n"
            "2. Categorizar gastos apropriadamente\n"
            "3. Identificar valores e descrições\n\n"
            "Categorias possíveis:\n"
            "- alimentacao\n"
            "- transporte\n"
            "- moradia\n"
            "- saude\n"
            "- educacao\n"
            "- lazer\n"
            "- outros\n\n"
            "Retorne apenas um JSON com os campos:\n"
            '{ "categoria": string, "valor": float, "descricao": string, "sucesso": boolean, "mensagem": string }'
        )

        try:
            response = self.client.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": mensagem}
                ]
            )
            resultado = json.loads(response.choices[0].message.content)
            return resultado
            
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro ao processar mensagem: {str(e)}"
            }
    
    def analyze_image(self, image_content) -> dict:
        """
        Simula a análise de uma imagem usando GPT-4 Vision.
        Substitua por uma implementação real conforme disponível.
        """
        # Simulação: suponha que a imagem contenha um gasto de R$50 no almoço.
        return {
            "gastos": [
                {"categoria": "alimentacao", "valor": 50.0, "descricao": "Almoço"}
            ]
        }

    def analyze_bank_csv(self, df: pd.DataFrame):
        """
        Simula a análise de um CSV bancário.
        Mapeia colunas comuns para gastos.
        """
        gastos = []
        # Supondo que o CSV tenha colunas 'amount' e 'description'
        for _, row in df.iterrows():
            try:
                gasto = {
                    "categoria": "outros",
                    "valor": float(row.get("amount", 0)),
                    "descricao": row.get("description", "Transação CSV")
                }
                gastos.append(gasto)
            except Exception as e:
                continue
        return gastos

    def analyze_bank_pdf(self, doc_content):
        """
        Simula a análise de um PDF bancário.
        Em produção, utilize uma biblioteca para leitura de PDF (ex.: PyPDF2).
        """
        # Simulação: retorna um gasto fixo
        return [
            {"categoria": "outros", "valor": 100.0, "descricao": "Transação PDF simulada"}
        ]

    def analisar_padroes(self, df: pd.DataFrame) -> str:
        if not self.client:
            return "Cliente OpenAI não inicializado. Verifique as configurações."

        if df.empty:
            return "Ainda não há dados suficientes para análise."

        resumo_categorias = df.groupby("categoria")["valor"].agg(["sum", "count", "mean"])
        tendencia_mensal = df.groupby(df["data"].dt.strftime("%Y-%m"))["valor"].sum()
        
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
            response = self.client.ChatCompletion.create(
                model="gpt-4",
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
        df["data"] = pd.to_datetime(df["data"])
        df_mes = df[df["data"].dt.month == mes_atual]
        
        if df_mes.empty:
            return "Nenhum gasto registrado este mês.", None
        
        gastos_categoria = df_mes.groupby("categoria")["valor"].sum()
        total_gasto = df_mes["valor"].sum()
        media_diaria = total_gasto / df_mes["data"].dt.day.nunique()
        
        fig = px.pie(
            values=gastos_categoria.values,
            names=gastos_categoria.index,
            title="Distribuição de Gastos por Categoria"
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        
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
        self.base_url = ConfigManager.get_secret("STREAMLIT_URL", "seu-app-name.streamlit.app")
    
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
                except Exception:
                    st.text(response.text)
            else:
                st.error(f"❌ Erro no webhook: {response.status_code}")
                st.text(response.text)
            
        except Exception as e:
            st.error(f"❌ Erro ao testar webhook: {str(e)}")

# Rotas do Flask para o Webhook
@flask_app.route("/webhook", methods=["POST"])
def webhook_post():
    data = request.json
    try:
        # Extrair a mensagem do payload do WhatsApp (estrutura aninhada)
        entry = data.get("entry", [])
        if entry:
            changes = entry[0].get("changes", [])
            if changes:
                value = changes[0].get("value", {})
                messages = value.get("messages", [])
                if messages:
                    mensagem_data = messages[0]
                    numero = mensagem_data.get("from")
                    texto = mensagem_data.get("text", {}).get("body", "")
                    
                    data_manager = DataManager()
                    ai_assistant = AIFinanceAssistant(ConfigManager.initialize_openai())
                    
                    if texto.lower() == "relatorio":
                        relatorio, _ = ai_assistant.gerar_relatorio_mensal(
                            data_manager.get_dataframe()
                        )
                        ConfigManager.send_whatsapp_message(numero, relatorio)
                    else:
                        resultado = ai_assistant.processar_mensagem(texto)
                        if resultado.get("sucesso"):
                            if data_manager.adicionar_gasto(resultado):
                                mensagem_envio = (
                                    f"✅ Gasto registrado com sucesso!\n\n"
                                    f"Categoria: {resultado.get('categoria')}\n"
                                    f"Valor: R$ {float(resultado.get('valor')):.2f}\n"
                                    f"Descrição: {resultado.get('descricao')}"
                                )
                            else:
                                mensagem_envio = "❌ Erro ao salvar o gasto."
                        else:
                            mensagem_envio = resultado.get("mensagem", "Erro ao processar a mensagem.")
                        
                        ConfigManager.send_whatsapp_message(numero, mensagem_envio)
        
        return jsonify({"status": "success", "message": "Mensagem processada com sucesso"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@flask_app.route("/webhook", methods=["GET"])
def webhook_verify():
    try:
        verify_token = ConfigManager.get_secret("VERIFY_TOKEN")
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode and token:
            if mode == "subscribe" and token == verify_token:
                return challenge, 200
            else:
                return jsonify({"status": "error", "message": "Token inválido"}), 403
        return jsonify({"status": "error", "message": "Parâmetros inválidos"}), 400
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Inicialização dos componentes com cache
@st.cache_resource
def initialize_components():
    data_manager = DataManager()
    openai_client = ConfigManager.initialize_openai()
    ai_assistant = AIFinanceAssistant(openai_client)
    webhook_tester = WebhookTester()
    return data_manager, ai_assistant, webhook_tester

def render_sidebar(webhook_tester):
    with st.sidebar:
        st.title("⚙️ Configurações")
        st.subheader("Status das APIs")
        
        openai_status = "✅ Conectado" if ConfigManager.get_secret("OPENAI_API_KEY") else "❌ Não configurado"
        whatsapp_status = "✅ Conectado" if ConfigManager.get_secret("WHATSAPP_TOKEN") else "❌ Não configurado"
        
        st.write(f"OpenAI API: {openai_status}")
        st.write(f"WhatsApp API: {whatsapp_status}")
        
        webhook_tester.render_test_interface()

def main():
    data_manager, ai_assistant, webhook_tester = initialize_components()
    
    st.title("💰 Assistente Financeiro Inteligente")
    render_sidebar(webhook_tester)
    
    if data_manager.has_data():
        tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📝 Registros", "🤖 Análise IA"])
        
        with tab1:
            st.subheader("Dashboard Financeiro")
            relatorio, fig = ai_assistant.gerar_relatorio_mensal(data_manager.get_dataframe())
            if fig:
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

def start_flask():
    flask_app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    # Inicia o servidor Flask em uma thread separada
    flask_thread = Thread(target=start_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Inicia a aplicação Streamlit
    main()
