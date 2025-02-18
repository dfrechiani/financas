import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path

class DataManager:
    def __init__(self):
        # Inicializar DataFrame na sessão do Streamlit
        if 'df' not in st.session_state:
            st.session_state.df = pd.DataFrame(
                columns=['data', 'categoria', 'valor', 'descricao']
            )
    
    def adicionar_gasto(self, gasto: dict) -> bool:
        """Adiciona um novo gasto ao DataFrame"""
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
            
            # Salvar em CSV para persistência
            self.salvar_dados()
            return True
            
        except Exception as e:
            st.error(f"Erro ao adicionar gasto: {str(e)}")
            return False
    
    def get_dataframe(self) -> pd.DataFrame:
        """Retorna o DataFrame atual"""
        return st.session_state.df
    
    def has_data(self) -> bool:
        """Verifica se existem dados registrados"""
        return not st.session_state.df.empty
    
    def salvar_dados(self):
        """Salva os dados em CSV"""
        try:
            # Criar diretório se não existir
            Path("data").mkdir(exist_ok=True)
            st.session_state.df.to_csv("data/gastos.csv", index=False)
        except Exception as e:
            st.error(f"Erro ao salvar dados: {str(e)}")
    
    def carregar_dados(self):
        """Carrega dados do CSV se existir"""
        try:
            if Path("data/gastos.csv").exists():
                df = pd.read_csv("data/gastos.csv")
                df['data'] = pd.to_datetime(df['data'])
                st.session_state.df = df
        except Exception as e:
            st.error(f"Erro ao carregar dados: {str(e)}")
