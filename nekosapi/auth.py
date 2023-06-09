import json
import typing

from requests_oauthlib import OAuth2Session


class Client:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, scope: typing.Optional[typing.List[str]] = None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scope = scope or [""]

        self._session = OAuth2Session(client_id=self.client_id, redirect_uri=self.redirect_uri, scope=self.scope)
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None

    def authorization_url(self) -> typing.Tuple[str, str]:
        """
        Returns the authorization URL for the API.

        :return: A tuple containing the authorization URL and a string.
        :rtype: Tuple[str, str]
        """
        return self._session.authorization_url(
            authorization_url="https://api.nekosapi.com/v2/auth/authorize",
        )

    def login(self, code: str) -> typing.Tuple[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = json.dumps({
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        })

        self._session.fetch_token(
            token_url="https://api.nekosapi.com/v2/auth/token",
            body=body,
            headers=headers
        )
        self.access_token = self._session.token["access_token"]
        self.refresh_token = self._session.token["refresh_token"]
        self.expires_at = self._session.token["expires_at"]

    def __repr__(self) -> str:
        return f"Client(client_id={self.client_id!r}, client_secret={self.client_secret!r})"
