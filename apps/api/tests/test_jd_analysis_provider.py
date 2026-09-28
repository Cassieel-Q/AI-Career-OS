from app.jd_analysis_provider import OpenAIJDAnalysisProvider


class FakeCompletions:
    def create(self, **kwargs):
        assert kwargs["response_format"] == {"type": "json_object"}
        return type("Response", (), {"choices": [type("Choice", (), {"message": type("Message", (), {"content": '{"items":[{"jd_id":"00000000-0000-0000-0000-000000000001","items":[]}]}'})()})()]})()


class FakeClient:
    chat = type("Chat", (), {"completions": FakeCompletions()})()


def test_provider_accepts_strict_json_object_contract(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = OpenAIJDAnalysisProvider(client=FakeClient())
    result = provider.analyze(target_role="AI_PRODUCT_MANAGER", job_descriptions=[{"id": "jd", "raw_text": "x", "source_url": None}])
    assert len(result.items) == 1
