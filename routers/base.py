from contracts.schemas import RouterResult


class RouterAdapter:
    name = "base"
    version = "unknown"

    def start(self, config_name, mock_url="http://localhost:8900"):
        raise NotImplementedError

    def send(self, prompt, request_id, api_style="openai") -> RouterResult:
        """Send one request through the router. The prompt must contain f"REQ:{request_id}"."""
        raise NotImplementedError

    def stop(self):
        pass

    def supports(self, config_name) -> bool:
        return False
