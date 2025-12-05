import os
from docx import Document  # Библиотека для чтения файлов .docx
from environs import Env  # Библиотека для безопасной работы с переменными окружения
from gigachat import GigaChat  # API клиент для общения с моделью GigaChat
import redis  # Клиент для работы с Redis (хранилище истории)
from langchain_community.embeddings import GigaChatEmbeddings

# LangChain модули для построения цепочки обработки
from langchain_community.vectorstores import FAISS  # Векторное хранилище для семантического поиска

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder  # Конструкторы промптов
from langchain_core.output_parsers import StrOutputParser  # Парсер для преобразования вывода в строку
from langchain_core.runnables import (
    RunnableLambda,  # Обработчик для выполнения функций в цепи
    RunnableParallel,  # Запуск нескольких операций одновременно
    RunnableWithMessageHistory,  # Интеграция истории сообщений
    RunnablePassthrough  # Пропуск данных без изменений
)
from langchain_redis import RedisChatMessageHistory  # История сообщений в Redis
from langchain_classic.text_splitter import RecursiveCharacterTextSplitter  # Разбиение текста на куски

from lexicon.lexicon import PROMPT_LEXICON  # Словарь с шаблонами промптов

# =============================================================================
# 1️⃣ ИНИЦИАЛИЗАЦИЯ GIGACHAT API
# =============================================================================

env = Env()
env.read_env()  # Читаем переменные окружения из .env файла
GIGA_KEY = env.str("GIGACHAT_KEY")  # Получаем API ключ для GigaChat

# Создаем клиент GigaChat с конфигурацией
giga = GigaChat(
    credentials=GIGA_KEY,
    verify_ssl_certs=False  # Отключаем проверку SSL (для локальной разработки)
)


def giga_invoke(prompt_text: str) -> str:
    """
    Отправляет промпт в GigaChat и возвращает ответ.

    Args:
        prompt_text: Текст промпта для отправки модели

    Returns:
        Текстовый ответ от модели GigaChat
    """
    response = giga.chat(prompt_text)
    return response.choices[0].message.content  # Извлекаем только текст ответа


# =============================================================================
# 2️⃣ НАСТРОЙКА ВЕКТОРНОГО ХРАНИЛИЩА (FAISS) И ЭМБЕДДИНГОВ
# =============================================================================

# Создаем эмбеддинги (преобразование текста в векторы) с помощью русской модели SBERT
hf_embeddings = GigaChatEmbeddings(
credentials=GIGA_KEY, verify_ssl_certs=False
)

index_path = "LLM/faiss_db"  # Путь, где хранится индекс FAISS

# Проверяем, существует ли уже индекс
if os.path.exists(index_path):
    # Загружаем существующий индекс (быстрее, чем создавать новый)
    print("Загружаю существующий FAISS индекс...")
    db = FAISS.load_local(
        index_path,
        hf_embeddings,
        allow_dangerous_deserialization=True
    )
else:
    # Создаем новый индекс, если его еще нет
    print("Создаю новый FAISS индекс...")

    # Читаем документ .docx
    doc = Document("LLM/rag.docx")
    # Объединяем все абзацы документа в один текст
    full_text = "\n".join([p.text for p in doc.paragraphs])

    # Разбиваем большой текст на куски для лучшей обработки
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,  # Размер одного куска (символов)
        chunk_overlap=50  # Перекрытие между кусками для контекста
    )
    docs = splitter.create_documents([full_text])

    # Создаем FAISS индекс из кусков текста с их эмбеддингами
    db = FAISS.from_documents(docs, hf_embeddings)
    # Сохраняем индекс на диск для будущих использований
    db.save_local(index_path)

# Создаем retriever - инструмент для поиска релевантных документов по запросу
retriever = db.as_retriever()

# =============================================================================
# 3️⃣ НАСТРОЙКА REDIS ДЛЯ ХРАНЕНИЯ ИСТОРИИ ЧАТА
# =============================================================================

# Подключаемся к локальному Redis серверу
redis_host = os.getenv("REDIS_HOST", "redis")
redis_port = int(os.getenv("REDIS_PORT", 6379))

redis_client = redis.Redis(host=redis_host, port=redis_port)


def get_redis_history(session_id):
    """
    Получает историю сообщений для конкретной пользовательской сессии.

    Args:
        session_id: Уникальный идентификатор сессии пользователя

    Returns:
        Объект истории сообщений из Redis
    """
    history = RedisChatMessageHistory(
        redis_client=redis_client,
        session_id=session_id,
        ttl=3600,  # Time To Live - история хранится 1 час
    )
    return history


# =============================================================================
# 4️ СОЗДАНИЕ ПРОМПТА С ПОДДЕРЖКОЙ ИСТОРИИ
# =============================================================================

# Строим структурированный промпт для модели
prompt = ChatPromptTemplate.from_messages([
    # Системное сообщение - инструкции для модели
    ("system", f'{PROMPT_LEXICON["assistent_template"]}'),

    # MessagesPlaceholder - заполнитель для истории сообщений
    # LangChain автоматически подставит сюда историю разговора
    MessagesPlaceholder(variable_name="history"),
])


# =============================================================================
# 5️⃣ СОЗДАНИЕ RAG ЦЕПОЧКИ (Retrieval-Augmented Generation)
# =============================================================================

def format_docs(docs):
    """
    Форматирует найденные документы в читаемый текст.

    Args:
        docs: Список найденных документов

    Returns:
        Объединенный текст всех документов
    """
    return "\n\n".join(d.page_content for d in docs)


# Главная цепочка обработки:
rag_chain = (
    # Шаг 1️: Параллельная подготовка трех компонентов
        RunnableParallel({
            # Компонент 1: Вопрос пользователя - просто передаем как есть
            "question": RunnableLambda(lambda x: x["question"]),

            # Компонент 2: Поиск контекста в документах
            # 2.1: Берем вопрос и ищем релевантные документы в FAISS
            "context": RunnableLambda(lambda x: retriever.invoke(x["question"]))
                       # 2.2: Форматируем найденные документы в текст
                       | RunnableLambda(format_docs),

            #Компонент 3: История разговора
            # последние 2 сообщения для контекста
            "history": RunnableLambda(lambda x: x.get("history", [])[-4:]),
        })
        # Шаг 2️: Подставляем все компоненты в промпт
        | prompt
        # Шаг 3️: Преобразуем сообщения в строку
        | (lambda msg: msg.to_string())
        # Шаг 4️: Отправляем в GigaChat API
        | RunnableLambda(giga_invoke)
        # Шаг 5️: Парсим ответ (преобразуем в строку)
        | StrOutputParser()
)

# Оборачиваем цепочку для работы с историей сообщений
chain_with_history = RunnableWithMessageHistory(
    rag_chain,
    get_session_history=get_redis_history,  # Функция для получения истории
    input_messages_key="question",  # Ключ для текущего вопроса
    history_messages_key="history"  # Ключ для истории
)


# =============================================================================
# ОСНОВНАЯ ФУНКЦИЯ ДЛЯ ВЫЗОВА
# =============================================================================

def ask_giga_chat(user_question: str, session_id: str) -> str:
    """
    Главная функция для общения с ботом.

    Args:
        user_question: Вопрос пользователя
        session_id: ID сессии (разные пользователи = разные session_id)

    Returns:
        Ответ от GigaChat с учетом истории и контекста
    """
    return chain_with_history.invoke(
        {"question": user_question},  # Входные данные
        config={"configurable": {"session_id": session_id}}  # Конфигурация сессии
    )


