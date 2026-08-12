from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class AnalyticsProviderInterface(ABC):
    """Core interface for Analytics and RAG providers."""
    
    @abstractmethod
    def query_playbook(self, query: str, channel: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
        """
        Query the analytics/RAG backend for historical playbooks or retrospectives.
        
        Args:
            query (str): The question or query string.
            channel (Optional[str]): A channel or namespace to filter the RAG results.
            timeout (int): Request timeout in seconds.
            
        Returns:
            Dict[str, Any]: The response dictionary containing the synthesized answer or errors.
        """
        pass
