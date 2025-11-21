import os
from docx import Document
from environs import Env

from gigachat import GigaChat
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_classic.text_splitter import RecursiveCharacterTextSplitter

from lexicon.lexicon import PROMPT_LEXICON

# Чтение .env
env = Env()
env.read_env()
GIGA_KEY = env.str("GIGACHAT_KEY")

# Инициализация GigaChat клиента
giga = GigaChat(
    credentials=GIGA_KEY,
    verify_ssl_certs=False
)

# Embeddings
hf_embeddings_model = HuggingFaceEmbeddings(
    model_name="sberbank-ai/sbert_large_nlu_ru",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

# FAISS индекс
index_path = "LLM/faiss_db"
if os.path.exists(index_path):
    print("Загружаю существующий FAISS индекс...")
    db = FAISS.load_local(index_path, hf_embeddings_model, allow_dangerous_deserialization=True)
else:
    print("Создаю новый FAISS индекс...")
    doc_path = os.path.abspath("LLM/rag.docx")
    if not os.path.exists(doc_path):
        raise FileNotFoundError(f"Документ не найден: {doc_path}")

    doc = Document(doc_path)
    full_text = "\n".join([p.text for p in doc.paragraphs])

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    docs = splitter.create_documents([full_text])

    db = FAISS.from_documents(docs, hf_embeddings_model)
    db.save_local(index_path)

retriever = db.as_retriever()

# Prompt шаблон
template = PROMPT_LEXICON["assistent_template"]
prompt = ChatPromptTemplate.from_template(template)

def format_docs(docs):
    return "\n\n".join([d.page_content for d in docs]) if docs else ""

# Функция для обращения к GigaChat + RAG
def ask_giga_chat_sync(user_question: str) -> str:
    # Получаем релевантные документы через retriever
    docs = retriever._get_relevant_documents(user_question,run_manager=None)  # используем публичный метод
    context = format_docs(docs)

    # Формируем финальный prompt
    final_prompt = prompt.format(context=context, question=user_question)

    # Отправляем в GigaChat
    response = giga.chat(final_prompt)
    return response.choices[0].message.content

print(ask_giga_chat_sync('hello'))




