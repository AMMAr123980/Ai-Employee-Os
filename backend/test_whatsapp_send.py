import requests
import getpass

BASE_URL = "http://127.0.0.1:8001"

token = getpass.getpass("JWT token: ")
phone = input("Recipient phone: ").strip()
message = input("Message: ").strip()

response = requests.post(
    f"{BASE_URL}/api/whatsapp/send",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    },
    json={
        "recipient_phone": phone,
        "message_text": message,
        "customer_id": None,
    },
)

print("\nStatus:", response.status_code)
print("Response:", response.text)