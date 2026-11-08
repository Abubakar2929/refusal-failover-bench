"""Router names accepted by the runner."""
from routers.langchain_adapter import LangChainAdapter
from routers.litellm_adapter import LiteLLMAdapter
from routers.litellm_proxy_adapter import LiteLLMProxyAdapter
from routers.portkey_adapter import PortkeyAdapter

ADAPTERS = {"litellm": LiteLLMAdapter, "langchain": LangChainAdapter, "portkey": PortkeyAdapter, "litellm_proxy": LiteLLMProxyAdapter}
