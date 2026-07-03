import requests


def generar_refresh_token(client_id, client_secret, grant_token, accounts_url="https://accounts.zoho.com"):
    url = f"{accounts_url}/oauth/v2/token"

    params = {
        "code": grant_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
    }

    response = requests.post(url, params=params)
    data = response.json()

    return data
