import pandas as pd
from langchain_community.vectorstores import FAISS
import os

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

from rag import document
from environs import Env
from lexicon.lexicon import PROMPT_LEXICON
from langchain_classic.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_gigachat.chat_models import GigaChat

# Чтение переменных окружения и создание экземпляра модели GigaChat
env = Env()
env.read_env()
llm_giga = GigaChat(credentials=env.str('GIGACHAT_KEY'), model="GigaChat", verify_ssl_certs=False)

# Установка embedding-модели Hugging Face
hf_embeddings_model = HuggingFaceEmbeddings(model_name="sberbank-ai/sbert_large_nlu_ru", model_kwargs={"device": "cpu"}, encode_kwargs={"normalize_embeddings": True})

# Загрузка или создание векторного индекса FAISS
index_path = 'faiss_db'
if os.path.exists(index_path):
    print("Загружаю существующий индекс...")
    db = FAISS.load_local(index_path, hf_embeddings_model, allow_dangerous_deserialization=True)
else:
    print("Создаю новый индекс...")
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100, length_function=len)
    split_documents = splitter.create_documents([document[i]['answer'] for i in range(len(document))])
    embeddings = hf_embeddings_model.embed_documents([doc.page_content for doc in split_documents])
    db = FAISS.from_documents(split_documents, embeddings)
    db.save_local(index_path)

# Получение retriever'а для поиска похожих документов
retriever = db.as_retriever()

# Подготовка шаблона подсказки и форматирование документов
template = PROMPT_LEXICON['assistent_template']
prompt = ChatPromptTemplate.from_template(template)

def format_docs(docs):
    """Объединяет содержимое найденных документов."""
    return "\n\n".join([d.page_content for d in docs])

# Создаем цепочку обработки запросов
chain = (
    {'context':retriever|format_docs,'question':RunnablePassthrough()}  # Извлекаем релевантные документы и объединяем их
    |prompt  # Формируем финальный запрос для LLM
    |llm_giga  # Обрабатываем запрос моделью
    |StrOutputParser()  # Парсим вывод в строку
)

# Выполняем запрос и выводим результат
result = chain.invoke('как записаться на курсы к кому обратиться?')
print(result)