import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import yaml
from environs import Env

from gigachat import GigaChat

from langchain_community.embeddings import GigaChatEmbeddings
from langchain_community.vectorstores import FAISS

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import (
    RunnableLambda,
    RunnableParallel,
    RunnableWithMessageHistory
)

from langchain_redis import RedisChatMessageHistory
from langchain_classic.text_splitter import RecursiveCharacterTextSplitter
from redis import Redis

from lexicon.lexicon import PROMPT_LEXICON



# 1. ИНИЦИАЛИЗАЦИЯ GIGACHAT


env = Env()                 # Загружаем переменные окружения
env.read_env()

GIGA_KEY = env.str("GIGACHAT_KEY")  # Ключ для GigaChat API

giga = GigaChat(
    credentials=GIGA_KEY,          # Передаем ключ
    verify_ssl_certs=False,        # Не проверяем SSL (можно True)
    model='GigaChat-2-Pro',        # Указываем модель GigaChat-2-Max
)

executor = ThreadPoolExecutor(max_workers=10)  # Поток для асинхронного вызова синхронного API

async def giga_invoke_async(prompt_text: str) -> str:
    """Асинхронный вызов GigaChat через ThreadPoolExecutor"""
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(executor, giga.chat, prompt_text)
    return response.choices[0].message.content  # Возвращаем текст ответа



# 2. ВЕКТОРНОЕ ХРАНИЛИЩЕ / ЭМБЕДДИНГИ


embeddings = GigaChatEmbeddings(
    credentials=GIGA_KEY,
    verify_ssl_certs=False
)

index_path = "LLM/faiss_db"   # Путь к FAISS индексу
yaml_path = "LLM/rag.yaml"    # Путь к YAML базе знаний

# =========================
# Загрузка или создание FAISS
# =========================
if os.path.exists(index_path):
    print("Загружаю существующий FAISS индекс...")  # Если индекс есть, просто загружаем
    db = FAISS.load_local(
        index_path,
        embeddings,
        allow_dangerous_deserialization=True
    )
else:
    print("Создаю новый FAISS индекс...")  # Если нет — создаем новый

    with open(yaml_path, "r", encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f)  # Загружаем YAML как Python словарь

    texts = []
    for course in yaml_data["COURSES"]:
        text = "\n".join([
            f"id: {course.get('id')}",                              # ID курса
            f"title: {course.get('title')}",                        # Название
            f"age_min: {course.get('age_min')}",                    # Минимальный возраст
            f"age_max: {course.get('age_max')}",                    # Максимальный возраст
            f"skills: {', '.join(course.get('skills', []))}",      # Навыки, которые получит ребенок
            f"child_outcomes: {', '.join(course.get('child_outcomes', []))}",  # Что ребенок сможет делать
            f"parent_value: {', '.join(course.get('parent_value', []))}",      # Польза для родителей
            f"when_to_offer: {course.get('when_to_offer')}",        # Когда курс актуален
            f'description: {course.get("description")}'
            f"tags: {', '.join(course.get('tags', []))}",          # Теги для поиска

        ])
        texts.append(text)  # Сохраняем курс как текст

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)  # Разбивка на чанки
    chunks = []
    for t in texts:
        chunks.extend(splitter.split_text(t))  # Каждый чанк — просто строка

    db = FAISS.from_texts(chunks, embeddings)  # Создаем FAISS индекс из строк
    db.save_local(index_path)                  # Сохраняем на диск

retriever = db.as_retriever()  # Получаем retriever для RAG



# 3. АСИНХРОННЫЙ REDIS (история диалогов)


redis_host = os.getenv("REDIS_HOST", "redis")  # Хост Redis
redis_port = int(os.getenv("REDIS_PORT", 6379))  # Порт Redis

redis_client = Redis(host=redis_host, port=redis_port)

def get_redis_history(session_id: str):
    """
    Возвращает объект для хранения истории сообщений в Redis.
    TTL = 3600 секунд (1 час)
    """
    return RedisChatMessageHistory(
        redis_client=redis_client,
        session_id=session_id,
        ttl=3600,
    )



# 4. ПРОМПТЫ ДЛЯ RAG


prompt = ChatPromptTemplate.from_messages([
    ("system", PROMPT_LEXICON["system_policy"]),       # Логика принятия решений
    ("system", PROMPT_LEXICON["rag_guard"]),          # Принудительное использование RAG
    ("system", PROMPT_LEXICON["assistant_template"]), # Стиль живого консультанта
    MessagesPlaceholder(variable_name="history"),     # История диалога
    ("user", "{question}")                             # Вопрос пользователя
])



# 5. СОЗДАНИЕ RAG-ЦЕПОЧКИ


def format_docs(docs):
    """Объединяет найденные документы в один текст для LLM"""
    return "\n\n".join(d.page_content for d in docs)


def build_search_query(data):
    """
    Собирает текст запроса для RAG с учётом истории диалога
    """
    question = data["question"]
    history = data.get("history", [])
    history_text = " ".join([m.content for m in history[-6:]])  # последние 6 сообщений

    return f"""
Профиль диалога:
{history_text}

Последний вопрос:
{question}

Найди информацию о подходящих курсах для ребёнка.
"""


async def call_giga(text: str) -> str:
    return await giga_invoke_async(text)


rag_chain = (
    RunnableParallel({
        "question": RunnableLambda(lambda x: x["question"]),  # Берем вопрос пользователя
        "context": (
            RunnableLambda(build_search_query)               # Формируем поисковый запрос с учетом истории
            | RunnableLambda(lambda q: retriever.invoke(q))  # Ищем релевантные документы в FAISS
            | RunnableLambda(format_docs)                     # Превращаем документы в текст для LLM
        ),
        "history": RunnableLambda(lambda x: x.get("history", [])[-6:])  # Берем последние 6 сообщений
    })
    | prompt                                                   # Подставляем промпт с правилами и стилем
    | RunnableLambda(lambda msg: msg.to_string())             # Превращаем объект ответа в строку
    | RunnableLambda(call_giga)  # Отправляем в GigaChat и получаем текст
    | StrOutputParser()                                        # Финальный парсинг текста
)

# Обёртка для цепочки с хранением истории в Redis
chain_with_history = RunnableWithMessageHistory(
    rag_chain,
    get_session_history=get_redis_history,
    input_messages_key="question",
    history_messages_key="history"
)



# 6. ASYNC API ДЛЯ ТЕЛЕГРАМ-БОТА


async def ask_giga_chat_async(user_question: str, session_id: str) -> str:
    """
    Асинхронная функция для общения с AI через RAG цепочку с историей.
    Возвращает ответ AI на заданный вопрос.
    """
    return await chain_with_history.ainvoke(
        {"question": user_question},
        config={"configurable": {"session_id": session_id}}
    )
