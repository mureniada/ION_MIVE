"""Retrieval module: embeddings, chunking, ingestion, and the vector store.

The only *product* vector store is Qdrant (`qdrant_store.QdrantRetrieval`).
`memory_index.InMemoryRetrieval` is a dependency-free TEST DOUBLE used by unit
tests and local dev — it is not a second product store (ADR-005).
"""
