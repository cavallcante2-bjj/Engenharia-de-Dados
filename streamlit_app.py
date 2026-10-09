"""Interface Streamlit para o agente SQL da Livraria Inteligente."""
import importlib.util
import os

import streamlit as st
from dotenv import load_dotenv

CAMINHO_AGENTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "04_sql_agent.py")


def carregar_modulo_agente():
    spec = importlib.util.spec_from_file_location("agente_sql", CAMINHO_AGENTE)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@st.cache_resource
def montar_agente(sem_contexto: bool):
    load_dotenv()
    modulo = carregar_modulo_agente()
    dsn = os.environ["DATABASE_URL"]
    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    model = os.environ["LLM_MODEL"]
    api_key = (
        os.environ["ANTHROPIC_API_KEY"] if provider == "anthropic" else os.environ["OPENAI_API_KEY"]
    )
    agente = modulo.AgenteLLM(provider, model, api_key)
    system_prompt = modulo.montar_prompt_sistema(dsn, sem_contexto)
    return modulo, agente, system_prompt, dsn


st.set_page_config(page_title="Agente SQL · Livraria Inteligente", page_icon="📚")
st.title("📚 Agente SQL da Livraria Inteligente")
st.caption(
    "Pergunte em português. O agente consulta `prata`/`ouro` no Supabase e mostra o SQL gerado "
    "e o resultado antes de responder."
)

sem_contexto = st.sidebar.checkbox("Sem contexto (só schema, para comparar)", value=False)

try:
    modulo, agente, system_prompt, dsn = montar_agente(sem_contexto)
except KeyError as erro:
    st.error(f"Variável de ambiente faltando no .env: {erro}")
    st.stop()

pergunta = st.text_input(
    "Sua pergunta",
    placeholder="Qual categoria tem o maior valor em estoque, em reais?",
)

if st.button("Perguntar", type="primary") and pergunta.strip():
    with st.spinner("Consultando..."):
        resultado = modulo.responder_pergunta(agente, system_prompt, dsn, pergunta.strip())

    for passo in resultado["tentativas"]:
        st.subheader(f"SQL gerado (tentativa {passo['numero']})")
        st.code(passo["sql"], language="sql")
        if "erro" in passo:
            st.error(passo["erro"])
        else:
            linhas_dict = [dict(zip(passo["colunas"], linha)) for linha in passo["linhas"]]
            st.dataframe(linhas_dict if linhas_dict else [], use_container_width=True)

    st.subheader("Resposta")
    st.success(resultado["resposta"])
