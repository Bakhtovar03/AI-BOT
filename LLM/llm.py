import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

from docx import Document
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


# ============================================================
# 1. ИНИЦИАЛИЗАЦИЯ GIGACHAT
# ============================================================

env = Env()
env.read_env()

GIGA_KEY = env.str("GIGACHAT_KEY")

# клиент GigaChat (он синхронный)
giga = GigaChat(
    credentials=GIGA_KEY,
    verify_ssl_certs=False
)


# --- async wrapper ---
executor = ThreadPoolExecutor(max_workers=10)
async def giga_invoke_async(prompt_text: str) -> str:
    """Асинхронный вызов GigaChat через executor."""
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(executor, giga.chat, prompt_text)
    return response.choices[0].message.content


# ============================================================
# 2. ВЕКТОРНОЕ ХРАНИЛИЩЕ / ЭМБЕДДИНГИ
# ============================================================

embeddings = GigaChatEmbeddings(
    credentials=GIGA_KEY,
    verify_ssl_certs=False
)

index_path = "LLM/faiss_db"

if os.path.exists(index_path):
    print("Загружаю существующий FAISS индекс...")
    db = FAISS.load_local(
        index_path,
        embeddings,
        allow_dangerous_deserialization=True
    )
else:
    print("Создаю новый FAISS индекс...")

    doc = Document("LLM/rag.docx")
    full_text = "\n".join([p.text for p in doc.paragraphs])

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    docs = splitter.create_documents([full_text])

    db = FAISS.from_documents(docs, embeddings)
    db.save_local(index_path)

retriever = db.as_retriever()


# ============================================================
# 3. АСИНХРОННЫЙ REDIS
# ============================================================

redis_host = os.getenv("REDIS_HOST", "redis")
redis_port = int(os.getenv("REDIS_PORT", 6379))

#redis_client = Redis(host=redis_host, port=redis_port)
redis_client = Redis(host=redis_host, port=redis_port)

def get_redis_history(session_id: str):
    return RedisChatMessageHistory(
        redis_client=redis_client,
        session_id=session_id,
        ttl=3600,
    )



# 4. ПРОМПТ


prompt = ChatPromptTemplate.from_messages([
    ("system", PROMPT_LEXICON["assistent_template"]),
    MessagesPlaceholder(variable_name="history"),
])



# 5. RAG-ЦЕПОЧКА


def format_docs(docs):
    return "\n\n".join(d.page_content for d in docs)


rag_chain = (
    RunnableParallel({
        "question": RunnableLambda(lambda x: x["question"]),
        "context": RunnableLambda(lambda x: retriever.invoke(x["question"]))
                   | RunnableLambda(format_docs),
        "history": RunnableLambda(lambda x: x.get("history", [])[-8:])
    })
    | prompt
    | RunnableLambda(lambda msg: msg.to_string())
    | RunnableLambda(lambda text: asyncio.run(giga_invoke_async(text)))
    | StrOutputParser()
)


# Обёртка с историей
chain_with_history = RunnableWithMessageHistory(
    rag_chain,
    get_session_history=get_redis_history,
    input_messages_key="question",
    history_messages_key="history"
)



# 6. ASYNC API ДЛЯ ТЕЛЕГРАМ-БОТА

async def ask_giga_chat_async(user_question: str, session_id: str) -> str:
    """
    Асинхронная функция общения с AI.
    """
    return await chain_with_history.ainvoke(
        {"question": user_question},
        config={"configurable": {"session_id": session_id}}
    )


