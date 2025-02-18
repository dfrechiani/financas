import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import json
from openai import OpenAI

class AIFinanceAssistant:
    def __init__(self):
        self.client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        
    def processar_mensagem(self, mensagem: str) -> dict:
        """Processa mensagem do usuário usando GPT-4"""
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
        """Análise avançada dos padrões de gastos"""
        if df.empty:
            return "Ainda não há dados suficientes para análise."

        # Preparar dados para análise
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
        """Gera relatório mensal com visualizações"""
        if df.empty:
            return "Nenhum gasto registrado ainda.", None
        
        # Filtrar para o mês atual
        mes_atual = datetime.now().month
        df['data'] = pd.to_datetime(df['data'])
        df_mes = df[df['data'].dt.month == mes_atual]
        
        if df_mes.empty:
            return "Nenhum gasto registrado este mês.", None
        
        # Análises
        gastos_categoria = df_mes.groupby('categoria')['valor'].sum()
        total_gasto = df_mes['valor'].sum()
        media_diaria = total_gasto / df_mes['data'].dt.day.nunique()
        
        # Gráfico
        fig = px.pie(
            values=gastos_categoria.values,
            names=gastos_categoria.index,
            title='Distribuição de Gastos por Categoria'
        )
        fig.update_traces(textposition='inside', textinfo='percent+label')
        
        # Relatório textual
        relatorio = f"""### 📊 Resumo Financeiro do Mês

💰 **Total Gasto:** R$ {total_gasto:.2f}
📅 **Média Diária:** R$ {media_diaria:.2f}

#### Gastos por Categoria:
"""
        
        # Adicionar cada categoria ao relatório
        for categoria, valor in gastos_categoria.items():
            percentual = (valor / total_gasto) * 100
            relatorio += f"- {categoria.title()}: R$ {valor:.2f} ({percentual:.1f}%)\n"
        
        return relatorio, fig
