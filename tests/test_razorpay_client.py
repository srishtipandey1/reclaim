from src.razorpay_client import RazorpayClient


class FakeInvoice:
    def notify_by(self, invoice_id: str, medium: str) -> dict[str, str]:
        return {'invoice_id': invoice_id, 'medium': medium}


class FakeClient:
    invoice = FakeInvoice()


def test_notify_invoice_uses_sdk_medium_argument() -> None:
    client = RazorpayClient(client=FakeClient())

    result = client.notify_invoice('inv_1', 'sms')

    assert result == {'invoice_id': 'inv_1', 'medium': 'sms'}