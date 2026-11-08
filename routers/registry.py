"""Router names accepted by the runner."""
from routers.langchain_adapter import LangChainAdapter
from routers.litellm_adapter import LiteLLMAdapter
from routers.portkey_adapter import PortkeyAdapter

ADAPTERS = {"litellm": LiteLLMAdapter, "langchain": LangChainAdapter, "portkey": PortkeyAdapter}
