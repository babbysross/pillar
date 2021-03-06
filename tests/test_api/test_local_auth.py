import json
import datetime

from bson import tz_util

from pillar.tests import AbstractPillarTest


class LocalAuthTest(AbstractPillarTest):
    def create_test_user(self):
        from pillar.api import local_auth
        with self.app.test_request_context():
            user_id = local_auth.create_local_user('koro@example.com', 'oti')
        return user_id

    def test_create_local_user(self):
        user_id = self.create_test_user()

        with self.app.test_request_context():
            users = self.app.data.driver.db['users']
            db_user = users.find_one(user_id)
            self.assertIsNotNone(db_user)

    def test_login_existing_user(self):
        user_id = self.create_test_user()

        resp = self.client.post('/api/auth/make-token',
                                data={'username': 'koro',
                                      'password': 'oti'})
        self.assertEqual(200, resp.status_code, resp.data)

        token_info = json.loads(resp.data)
        token = token_info['token']

        headers = {'Authorization': self.make_header(token)}
        resp = self.client.get('/api/users/%s' % user_id,
                               headers=headers)
        self.assertEqual(200, resp.status_code, resp.data)

    def test_login_expired_token(self):
        from pillar.api.utils.authentication import hash_auth_token

        user_id = self.create_test_user()

        resp = self.client.post('/api/auth/make-token',
                                data={'username': 'koro',
                                      'password': 'oti'})
        self.assertEqual(200, resp.status_code, resp.data)

        token_info = json.loads(resp.data)
        token = token_info['token']

        with self.app.test_request_context():
            tokens = self.app.data.driver.db['tokens']

            exp = datetime.datetime.now(tz=tz_util.utc) - datetime.timedelta(1)
            result = tokens.update_one({'token_hashed': hash_auth_token(token)},
                                       {'$set': {'expire_time': exp}})
            self.assertEqual(1, result.modified_count)

        # Do something restricted.
        headers = {'Authorization': self.make_header(token)}
        resp = self.client.put('/api/users/%s' % user_id,
                               headers=headers)
        self.assertEqual(403, resp.status_code, resp.data)

    def test_login_nonexistant_user(self):
        resp = self.client.post('/api/auth/make-token',
                                data={'username': 'proog',
                                      'password': 'oti'})

        self.assertEqual(403, resp.status_code, resp.data)

    def test_login_bad_pwd(self):
        resp = self.client.post('/api/auth/make-token',
                                data={'username': 'koro',
                                      'password': 'koro'})

        self.assertEqual(403, resp.status_code, resp.data)

    def test_hash_password(self):
        from pillar.api.local_auth import hash_password

        salt = b'$2b$12$cHdK4M8/yJ7SWp2Q.PYW0O'
        self.assertEqual(hash_password('© 2017 je moeder™', salt),
                         '$2b$12$cHdK4M8/yJ7SWp2Q.PYW0OAU1gE3DIVdeehq0XIzOMM0Vp3ldPMb6')
        self.assertIsInstance(hash_password('Резиновая уточка', salt), str)

        # The password should be encodable as ASCII.
        hash_password('Резиновая уточка', salt).encode('ascii')
