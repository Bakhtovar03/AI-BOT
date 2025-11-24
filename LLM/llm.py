import os
from docx import Document
from environs import Env
from gigachat import GigaChat

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableParallel, RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_classic.text_splitter import RecursiveCharacterTextSplitter

from lexicon.lexicon import PROMPT_LEXICON



#  ENV + GigaChat

env = Env()
env.read_env()
GIGA_KEY = env.str("GIGACHAT_KEY")

giga = GigaChat(
    credentials=GIGA_KEY,
    verify_ssl_certs=False
)



#  Embeddings + FAISS

hf_embeddings = HuggingFaceEmbeddings(
    model_name="sberbank-ai/sbert_large_nlu_ru",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

index_path = "LLM/faiss_db"

if os.path.exists(index_path):
    print("Загружаю существующий FAISS индекс...")
    db = FAISS.load_local(
        index_path,
        hf_embeddings,
        allow_dangerous_deserialization=True
    )
else:
    print("Создаю новый FAISS индекс...")
    doc_path = os.path.abspath("LLM/rag.docx")
    if not os.path.exists(doc_path):
        raise FileNotFoundError(f"Документ не найден: {doc_path}")

    doc = Document(doc_path)
    full_text = "\n".join([p.text for p in doc.paragraphs])

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    docs = splitter.create_documents([full_text])

    db = FAISS.from_documents(docs, hf_embeddings)
    db.save_local(index_path)

retriever = db.as_retriever()


#  Prompt

template = PROMPT_LEXICON["assistent_template"]
prompt = ChatPromptTemplate.from_template(template)


#  LangChain Runnable: сборка цепочки


def giga_invoke(prompt_text: str) -> str:
    """Обёртка для GigaChat под LangChain Runnable."""
    response = giga.chat(prompt_text)
    return response.choices[0].message.content


# Функция для форматирования доков для контекста
def format_docs(docs):
    return "\n\n".join([d.page_content for d in docs]) if docs else ""


# Основная RAG-цепочка
rag_chain = (
    RunnableParallel({
        "context": retriever | format_docs,
        "question": RunnablePassthrough()
    })
    | prompt
    | (lambda msg: msg.to_string())     # превращаем ChatPromptTemplate в обычный текст
    | giga_invoke                       # вызываем GigaChat
    | StrOutputParser()                 # получаем строку
)



#  Внешняя функция, вызываемая из кода

def ask_giga_chat(user_question: str) -> str:
    return rag_chain.invoke(user_question)




