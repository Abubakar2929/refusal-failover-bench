from contracts.schemas import RouterResult


class Defence:
    name = "base"

    def call(self, adapter, prompt, request_id, requester_token=None) -> RouterResult:
        raise NotImplementedError


class D0None(Defence):
    name = "d0"

    def call(self, adapter, prompt, request_id, requester_token=None) -> RouterResult:
        return adapter.send(prompt, request_id)
