import streamlit as st
from flask import Flask, request
import json
from threading import Thread
from whatsapp_api_client_python import API
from modules.data_manager import DataManager
from modules.ai_assistant import AIFinanceAssistant

class WhatsAppHandler:
    def __init__(self, data_manager: DataManager, ai_assistant: AIFinanceAssistant):
        self.app = Flask(__name__)
        self.whatsapp_api = API(st.secrets["WHATSAPP_TOKEN"])
        self.data_manager = data_manager
        self.ai_assistant = ai_assistant
        
        # Configurar rotas do Flask
        self.setup_routes()
    
    def setup_routes(self):
        @self.app.route('/webhook', methods=['POST'])
        def webhook():
            try:
                data = request.json
                
                if 'messages' in data and data['messages']:
                    mensagem = data['messages'][0]
                    numero = mensagem['from']
                    texto = mensagem['text']['body']
                    
                    # Processar comando especial
                    if texto.lower() == 'relatorio':
                        self.enviar_relatorio(numero)
                    else:
                        # Processar gasto com IA
                        self.processar_mensagem(numero, texto)
                
                return 'OK', 200
                
            except Exception as e:
                st.error(f"Erro no webhook: {str(e)}")
                return 'Erro', 500
        
        @self.app.route('/webhook', methods=['GET'])
        def verificar():
            try:
                verify_token = st.secrets["VERIFY_TOKEN"]
                if request.args.get('hub.verify_token') == verify_token:
                    return request.args.get('hub.challenge')
                return 'Token inválido', 403
            except Exception as e:
                st.error(f"Erro na verificação: {str(e)}")
                return 'Erro', 500
    
    def start_webhook(self, port: int = 5000):
        """Inicia o servidor webhook em uma thread separada"""
        Thread(target=self.app.run, kwargs={'port': port}).start()
    
    def enviar_relatorio(self, numero: str):
        """Envia relatório mensal para o usuário"""
        try:
            relatorio, _ = self.ai_assistant.gerar_relatorio_mensal(
                self.data_manager.get_dataframe()
            )
            
            # Enviar mensagem
            self.whatsapp_api.send_message(
                numero,
                relatorio
            )
            
        except Exception as e:
            erro = f"Erro ao enviar relatório: {str(e)}"
            st.error(erro)
            self.whatsapp_api.send_message(numero, erro)
    
    def processar_mensagem(self, numero: str, texto: str):
        """Processa mensagem de gasto e responde ao usuário"""
        try:
            # Processar com IA
            resultado = self.ai_assistant.processar_mensagem(texto)
            
            if resultado['sucesso']:
                # Adicionar aos dados
                if self.data_manager.adicionar_gasto(resultado):
                    mensagem = f"""✅ Gasto registrado com sucesso!
                    
Categoria: {resultado['categoria']}
Valor: R$ {resultado['valor']:.2f}
Descrição: {resultado['descricao']}"""
                else:
                    mensagem = "❌ Erro ao salvar o gasto."
            else:
                mensagem = resultado['mensagem']
            
            # Enviar resposta
            self.whatsapp_api.send_message(numero, mensagem)
            
        except Exception as e:
            erro = f"Erro ao processar mensagem: {str(e)}"
            st.error(erro)
            self.whatsapp_api.send_message(numero, erro)
