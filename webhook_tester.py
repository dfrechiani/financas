import streamlit as st
import requests
import json
from datetime import datetime

class WebhookTester:
    def __init__(self):
        self.base_url = self._get_base_url()
    
    def _get_base_url(self) -> str:
        """Obtém a URL base do aplicativo Streamlit"""
        return st.secrets.get('STREAMLIT_URL', 'seu-app-name.streamlit.app')
    
    def render_test_interface(self):
        """Renderiza a interface de teste do webhook"""
        st.subheader("🔧 Teste do Webhook")
        
        # Campos de teste
        test_message = st.text_input(
            "Mensagem de teste",
            value="Gastei 50 reais no almoço"
        )
        
        if st.button("🔄 Testar Webhook"):
            self.test_webhook(test_message)
    
    def test_webhook(self, message: str):
        """Executa o teste do webhook"""
        try:
            # URL do webhook
            webhook_url = f"https://{self.base_url}/webhook"
            
            # Dados de teste simulando mensagem do WhatsApp
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
            
            # Fazer requisição
            with st.spinner("Testando webhook..."):
                response = requests.post(
                    webhook_url,
                    json=test_data,
                    headers={"Content-Type": "application/json"}
                )
            
            # Mostrar resultado
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
    
    def verify_webhook_configuration(self) -> bool:
        """Verifica se o webhook está configurado corretamente"""
        required_secrets = ["WHATSAPP_TOKEN", "VERIFY_TOKEN", "STREAMLIT_URL"]
        
        missing_secrets = [
            secret for secret in required_secrets 
            if secret not in st.secrets
        ]
        
        if missing_secrets:
            st.warning(f"⚠️ Configurações ausentes: {', '.join(missing_secrets)}")
            return False
        
        return True
