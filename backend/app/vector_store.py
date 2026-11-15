import chromadb

from app.config import settings

COLLECTION_NAME = f"coursemate-{settings.embedding_model}-{settings.embedding_dimensions}"


def init_chroma() -> chromadb.ClientAPI:
    path = settings.data_path / "chroma"
    path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(path))
    client.get_or_create_collection(
        name=COLLECTION_NAME,
        configuration={"hnsw": {"space": "cosine"}},
        embedding_function=None,
    )
    return client


def collection() -> chromadb.Collection:
    client = init_chroma()
    return client.get_collection(name=COLLECTION_NAME, embedding_function=None)


def add_chunks(ids: list[str], texts: list[str], embeddings: list[list[float]], metadatas: list[dict]) -> None:
    collection().add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)


def query_chunks(embedding: list[float], document_ids: list[str], limit: int = 5) -> list[dict]:
    if not document_ids:
        return []
    where: dict = (
        {"document_id": document_ids[0]}
        if len(document_ids) == 1
        else {"document_id": {"$in": document_ids}}
    )
    found = collection().query(
        query_embeddings=[embedding],
        n_results=limit,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    documents = (found.get("documents") or [[]])[0] or []
    metadatas = (found.get("metadatas") or [[]])[0] or []
    distances = (found.get("distances") or [[]])[0] or []
    rows = []
    for text, metadata, distance in zip(documents, metadatas, distances):
        rows.append(
            {
                "text": text,
                "document_id": metadata["document_id"],
                "filename": metadata["filename"],
                "page": metadata["page"],
                "chunk_index": metadata["chunk_index"],
                "distance": distance,
            }
        )
    return rows


def chunks_for_pages(pages: list[tuple[str, int]]) -> list[dict]:
    if not pages:
        return []
    document_ids = list(dict.fromkeys(document_id for document_id, _page in pages))
    page_numbers = list(dict.fromkeys(page for _document_id, page in pages))
    found = collection().get(
        where={
            "$and": [
                {"document_id": {"$in": document_ids}},
                {"page": {"$in": page_numbers}},
            ]
        },
        include=["documents", "metadatas"],
    )
    wanted = set(pages)
    documents = found.get("documents") or []
    metadatas = found.get("metadatas") or []
    rows = []
    for text, metadata in zip(documents, metadatas):
        pair = (metadata["document_id"], int(metadata["page"]))
        if pair not in wanted:
            continue
        rows.append(
            {
                "text": text,
                "document_id": metadata["document_id"],
                "filename": metadata["filename"],
                "page": int(metadata["page"]),
                "chunk_index": int(metadata["chunk_index"]),
            }
        )
    return rows


def delete_document_vectors(document_id: str) -> None:
    collection().delete(where={"document_id": document_id})
