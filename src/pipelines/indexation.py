# -*- coding: utf-8 -*-
from typing import List, Literal, Tuple, Union

import faiss
import numpy as np
import torch
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer
from sklearn.preprocessing import normalize

from src.utils.common import get_device

# Set the number of threads for PyTorch to 1 to avoid issues in MX Apple chip
# https://www.reddit.com/r/comfyui/comments/1c0n5de/there_appear_to_be_1_leaked_semaphore_objects_to/
torch.set_num_threads(1)


class Embeddings:
    """
    Embeddings class using Sentence Transformers.
    """

    def __init__(self, model_name: str):
        """
        Initialize the sentence transformer model.

        Args:
            model_name: Pre-trained model name or path.
            See: https://huggingface.co/sentence-transformers
        """

        self.model_name = model_name
        self._model = None  # Defer loading until first use
        self._device = None  # Defer loading until first use

        @property
        def device(self):
            return get_device()

        @property
        def model(self):
            if self._model is None:
                self._model = SentenceTransformer(model_name, device=self.device)
            return self._model

    def encode(self, text: Union[str, List[str]]) -> np.ndarray:
        """
        Encode text into embeddings.

        Args:
            text: Input text or list of texts to encode
        """
        return self.model.encode(text)


class ReRanker:
    """
    Cross-encoder re-ranker for improved relevance
    """

    def __init__(self, model_name: str):
        """
        Args:
            model_name: Cross-encoder model for re-ranking
            See: https://huggingface.co/cross-encoder
        """
        self.model_name = model_name
        self._model = None  # Defer loading until first use
        self._device = None  # Defer loading until first use

        @property
        def device(self):
            return get_device()

        @property
        def model(self):
            if self._model is None:
                self._model = CrossEncoder(
                    model_name,
                    device=self.device,
                    compute_type="float16",
                )
            return self._model

    def rerank(
        self,
        query: str,
        documents: List[str],
        k: int = 3,
    ) -> List[Tuple[str, float]]:
        """
        Re-rank documents based on relevance to query

        Args:
            query: Search query
            documents: Candidate documents to re-rank
            k: Number of documents to return
        """
        # Create query-document pairs
        pairs = [[query, doc] for doc in documents]

        # Get scores from cross-encoder
        scores = self.model.predict(pairs)

        # Combine documents with scores and sort
        scored_docs = list(zip(documents, scores))
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        return scored_docs[:k]


class VectorStore:
    """
    Vector store to index and search documents
    """

    def __init__(self, embeddings: Embeddings, reranker: Union[ReRanker, None] = None):
        """
        Args:
            embeddings: Embeddings model for vector search
            reranker: Optional re-ranker for improved results
        """
        self.embeddings = embeddings
        self.reranker = reranker
        self.index = None
        self.documents = []
        self.bm25 = None

    def add_documents(self, documents: List[str]):
        """
        Index documents for searching to the vector and BM25 index

        Args:
            documents: List of documents to index
        """
        self.documents = documents
        embeddings = self.embeddings.encode(documents)
        embeddings = normalize(embeddings, axis=1, norm="l2")

        # FAISS index
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(embeddings.astype(np.float32))

        # BM25 index
        tokenized_docs = [doc.split() for doc in documents]
        self.bm25 = BM25Okapi(tokenized_docs)

    def semantic_search(self, query: str, k: int = 5) -> List[Tuple[str, float]]:
        """
        Pure vector similarity search

        Args:
            query: Query string
            k: Number of results to return
        """
        query_embedding = self.embeddings.encode(query)
        query_embedding = normalize(query_embedding.reshape(1, -1), axis=1, norm="l2")

        scores, indices = self.index.search(query_embedding.astype(np.float32), k)

        results = []
        for i, score in zip(indices[0], scores[0]):
            if i >= 0:
                results.append((self.documents[i], float(score)))
        return results

    def keyword_search(self, query: str, k: int) -> List[Tuple[str, float]]:
        """
        Pure BM25 search using the rank_bm25 library

        Args:
            query: Query string
            k: Number of results to return
        """
        tokenized_query = query.split()
        scores = self.bm25.get_scores(tokenized_query)
        scored_docs = [
            (self.documents[i], float(scores[i])) for i in scores.argsort()[-k:][::-1]
        ]
        return scored_docs

    def hybrid_search(
        self,
        query: str,
        k: int = 5,
        alpha: float = 0.5,
    ) -> List[Tuple[str, float]]:
        """
        Combine BM25 and vector search scores

        Args:
            query: Query string
            k: Number of results to return
            alpha: alpha: Weight for hybrid search (0=BM25, 1=vector)
        """
        # Vector search
        vector_results = self.semantic_search(query, k)
        vector_scores = {doc: score for doc, score in vector_results}

        # BM25 search
        tokenized_query = query.split()
        bm25_scores = self.bm25.get_scores(tokenized_query)
        bm25_results = {
            self.documents[i]: float(bm25_scores[i])
            for i in bm25_scores.argsort()[-k:][::-1]
        }

        # Combine scores
        all_docs = set(vector_scores.keys()).union(set(bm25_results.keys()))
        combined_scores = []

        for doc in all_docs:
            vec_score = vector_scores.get(doc, 0.0)
            bm25_score = bm25_results.get(doc, 0.0)
            norm_bm25 = (bm25_score - min(bm25_results.values())) / (
                max(bm25_results.values()) - min(bm25_results.values()) + 1e-9
            )
            combined = alpha * vec_score + (1 - alpha) * norm_bm25
            combined_scores.append((doc, combined))

        combined_scores.sort(key=lambda x: x[1], reverse=True)
        return combined_scores[:k]

    def search(
        self,
        query: str,
        k: int = 5,
        search_type: Literal["hybrid", "keyword", "semantic"] = "hybrid",
        alpha: float = 0.5,
    ) -> List[Tuple[str, float]]:
        """
        Unified search interface with optional re-ranking

        Args:
            query: Search query
            k: Number of results to return
            search_type: Type of search to perform ("hybrid", "keyword", "semantic")
            alpha: Weight for hybrid search (0=BM25, 1=vector)
        """

        # First-stage retrieval
        # We get a big retrieval if reranker is available to have more candidates to re-rank
        if search_type == "hybrid":
            results = self.hybrid_search(
                query,
                k=k * 100 if self.reranker else k,
                alpha=alpha,
            )
        if search_type == "semantic":
            results = self.semantic_search(query, k=k * 100 if self.reranker else k)
        elif search_type == "keyword":
            results = self.keyword_search(query, k=k * 100 if self.reranker else k)

        # Re-ranking if available
        if self.reranker:
            docs = [doc for doc, _ in results]
            results = self.reranker.rerank(query, docs, k=k)

        return results[:k]


vector_store = VectorStore(
    embeddings=Embeddings("sentence-transformers/all-MiniLM-L6-v2"),
    reranker=ReRanker("cross-encoder/ms-marco-MiniLM-L-6-v2"),
)
