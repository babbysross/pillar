import abc
import attr
import json
import logging

from rauth import OAuth2Service
from flask import current_app, url_for, request, redirect, session, Response


@attr.s
class OAuthUserResponse:
    """Represents user information requested to an OAuth provider after
    authenticating.
    """

    id = attr.ib(validator=attr.validators.instance_of(str))
    email = attr.ib(validator=attr.validators.instance_of(str))


class OAuthError(Exception):
    """Superclass of all exceptions raised by this module."""


class ProviderConfigurationMissing(OAuthError):
    """Raised when an OAuth provider is used but not configured."""


class ProviderNotImplemented(OAuthError):
    """Raised when a provider is requested that does not exist."""


class OAuthCodeNotProvided(OAuthError):
    """Raised when the 'code' arg is not provided in the OAuth callback."""


class ProviderNotConfigured:
    """Dummy class that indicates a provider isn't configured."""


class OAuthSignIn(metaclass=abc.ABCMeta):
    provider_name: str = None  # set in each subclass.

    _providers = None  # initialized in get_provider()
    _log = logging.getLogger(f'{__name__}.OAuthSignIn')

    def __init__(self):
        credentials = current_app.config['OAUTH_CREDENTIALS'].get(self.provider_name)
        if not credentials:
            raise ProviderConfigurationMissing(
                f'Missing OAuth credentials for {self.provider_name}')

        self.consumer_id = credentials['id']
        self.consumer_secret = credentials['secret']

        # Set in a subclass
        self.service: OAuth2Service = None

    @abc.abstractmethod
    def authorize(self) -> Response:
        """Redirect to the correct authorization endpoint for the current provider.

        Depending on the provider, we sometimes have to specify a different
        'scope'.
        """
        pass

    @abc.abstractmethod
    def callback(self) -> OAuthUserResponse:
        """Callback performed after authorizing the user.

        This is usually a request to a protected /me endpoint to query for
        user information, such as user id and email address.
        """
        pass

    def get_callback_url(self):
        return url_for('users.oauth_callback', provider=self.provider_name,
                       _external=True, _scheme=current_app.config['SCHEME'])

    @staticmethod
    def auth_code_from_request() -> str:
        try:
            return request.args['code']
        except KeyError:
            raise OAuthCodeNotProvided('A code argument was not provided in the request')

    @staticmethod
    def decode_json(payload):
        return json.loads(payload.decode('utf-8'))

    def make_oauth_session(self):
        return self.service.get_auth_session(
            data={'code': self.auth_code_from_request(),
                  'grant_type': 'authorization_code',
                  'redirect_uri': self.get_callback_url()},
            decoder=self.decode_json
        )

    @classmethod
    def get_provider(cls, provider_name) -> 'OAuthSignIn':
        if cls._providers is None:
            cls._init_providers()

        try:
            provider = cls._providers[provider_name]
        except KeyError:
            raise ProviderNotImplemented(f'No such OAuth provider {provider_name}')

        if provider is ProviderNotConfigured:
            raise ProviderConfigurationMissing(f'OAuth provider {provider_name} not configured')

        return provider

    @classmethod
    def _init_providers(cls):
        cls._providers = {}

        for provider_class in cls.__subclasses__():
            try:
                provider = provider_class()
            except ProviderConfigurationMissing:
                cls._log.info('OAuth provider %s not configured',
                              provider_class.provider_name)
                provider = ProviderNotConfigured
            cls._providers[provider_class.provider_name] = provider


class BlenderIdSignIn(OAuthSignIn):
    provider_name = 'blender-id'

    def __init__(self):
        super().__init__()

        base_url = current_app.config['BLENDER_ID_ENDPOINT']

        self.service = OAuth2Service(
            name='blender-id',
            client_id=self.consumer_id,
            client_secret=self.consumer_secret,
            authorize_url='%s/oauth/authorize' % base_url,
            access_token_url='%s/oauth/token' % base_url,
            base_url='%s/api/' % base_url
        )

    def authorize(self):
        return redirect(self.service.get_authorize_url(
            scope='email',
            response_type='code',
            redirect_uri=self.get_callback_url())
        )

    def callback(self):
        oauth_session = self.make_oauth_session()

        # TODO handle exception for failed oauth or not authorized
        access_token = oauth_session.access_token
        assert isinstance(access_token, str), f'oauth token must be str, not {type(access_token)}'

        session['blender_id_oauth_token'] = access_token
        me = oauth_session.get('user').json()
        return OAuthUserResponse(str(me['id']), me['email'])


class FacebookSignIn(OAuthSignIn):
    provider_name = 'facebook'

    def __init__(self):
        super().__init__()
        self.service = OAuth2Service(
            name='facebook',
            client_id=self.consumer_id,
            client_secret=self.consumer_secret,
            authorize_url='https://graph.facebook.com/oauth/authorize',
            access_token_url='https://graph.facebook.com/oauth/access_token',
            base_url='https://graph.facebook.com/'
        )

    def authorize(self):
        return redirect(self.service.get_authorize_url(
            scope='email',
            response_type='code',
            redirect_uri=self.get_callback_url())
        )

    def callback(self):
        oauth_session = self.make_oauth_session()

        me = oauth_session.get('me?fields=id,email').json()
        # TODO handle case when user chooses not to disclose en email
        # see https://developers.facebook.com/docs/graph-api/reference/user/
        return OAuthUserResponse(me['id'], me.get('email'))


class GoogleSignIn(OAuthSignIn):
    provider_name = 'google'

    def __init__(self):
        super().__init__()
        self.service = OAuth2Service(
            name='google',
            client_id=self.consumer_id,
            client_secret=self.consumer_secret,
            authorize_url='https://accounts.google.com/o/oauth2/auth',
            access_token_url='https://accounts.google.com/o/oauth2/token',
            base_url='https://www.googleapis.com/oauth2/v1/'
        )

    def authorize(self):
        return redirect(self.service.get_authorize_url(
            scope='https://www.googleapis.com/auth/userinfo.email',
            response_type='code',
            redirect_uri=self.get_callback_url())
        )

    def callback(self):
        oauth_session = self.make_oauth_session()

        me = oauth_session.get('userinfo').json()
        return OAuthUserResponse(str(me['id']), me['email'])
