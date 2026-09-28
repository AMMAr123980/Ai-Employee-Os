"""
Elasticsearch Document & Knowledge Base Search Adapter.
Provides full-text and vector/hybrid indexing for enterprise documents.
Falls back to database string matching when Elasticsearch cluster is offline or unconfigured.
"""
import logging
from typing import List, Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)

class ElasticsearchKB:
    def __init__(self):
        self._es_client = None
        self._is_es = False

        if settings.elasticsearch_url:
            try:
                from elasticsearch import Elasticsearch
                self._es_client = Elasticsearch(settings.elasticsearch_url)
                if self._es_client.ping():
                    self._is_es = True
                    logger.info("Connected to Elasticsearch at %s", settings.elasticsearch_url)
                else:
                    logger.warning("Elasticsearch ping failed at %s. Falling back to DB search.", settings.elasticsearch_url)
            except Exception as err:
                logger.warning("Elasticsearch connection error (%s). Falling back to DB search.", err)
                self._es_client = None
                self._is_es = False

    def index_document(self, company_id: int, doc_id: int, title: str, content: str, category: str = "general") -> bool:
        if not self._is_es or not self._es_client:
            return False
        try:
            body = {
                "company_id": company_id,
                "doc_id": doc_id,
                "title": title,
                "content": content,
                "category": category,
            }
            self._es_client.index(index="ai_employee_kb", id=f"{company_id}_{doc_id}", document=body)
            return True
        except Exception as err:
            logger.error("Elasticsearch indexing error for doc %s: %s", doc_id, err)
            return False

    def search_documents(self, company_id: int, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self._is_es or not self._es_client:
            return []
        try:
            body = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"company_id": company_id}},
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["title^2", "content"],
                                    "fuzziness": "AUTO"
                                }
                            }
                        ]
                    }
                },
                "size": limit
            }
            res = self._es_client.search(index="ai_employee_kb", body=body)
            hits = res.get("hits", {}).get("hits", [])
            results = []
            for hit in hits:
                src = hit.get("_source", {})
                src["score"] = hit.get("_score")
                results.append(src)
            return results
        except Exception as err:
            logger.error("Elasticsearch search error for query '%s': %s", query, err)
            return []

    def status(self) -> dict:
        return {
            "type": "elasticsearch" if self._is_es else "database_fallback",
            "active": self._is_es,
            "url": settings.elasticsearch_url if self._is_es else None
        }

elasticsearch_kb = ElasticsearchKB()
