import asyncio

from monitor.notifier import Notifier


def test_alert_is_valid_html_in_priority_order(monkeypatch):
    sent = {}

    async def fake_send(self, text, button_url=None, as_html=False):
        sent.update(text=text, button_url=button_url, as_html=as_html)
        return True

    async def no_sound(self):
        return None

    monkeypatch.setattr(Notifier, "send_text", fake_send)
    monkeypatch.setattr(Notifier, "play_sound", no_sound)
    notifier = Notifier("token", "123", 1)

    ok = asyncio.run(notifier.send_availability_alert("https://example.test/partido", ["Popular <Sur>", "Platea & Baja"]))

    assert ok and sent["as_html"] and sent["button_url"] == "https://example.test/partido"
    assert "<b>1°</b> Popular &lt;Sur&gt;" in sent["text"]
    assert sent["text"].index("Popular") < sent["text"].index("Platea &amp; Baja")
