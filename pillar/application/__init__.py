import os
import json
import requests

from eve import Eve
from pymongo import MongoClient

# import random
# import string

from eve.auth import TokenAuth
from eve.auth import BasicAuth
from eve.io.mongo import Validator
from eve.methods.post import post_internal
from bson import ObjectId

from flask import g
from flask import request
from flask import url_for
from flask import abort

from pre_hooks import pre_GET
from pre_hooks import pre_PUT
from pre_hooks import pre_PATCH
from pre_hooks import pre_POST
from pre_hooks import pre_DELETE
# from pre_hooks import check_permissions
# from pre_hooks import compute_permissions

from datetime import datetime
from datetime import timedelta


RFC1123_DATE_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'


class SystemUtility():
    def __new__(cls, *args, **kwargs):
        raise TypeError("Base class may not be instantiated")

    @staticmethod
    def blender_id_endpoint():
        """Gets the endpoint for the authentication API. If the env variable
        is defined, it's possible to override the (default) production address.
        """
        return os.environ.get(
            'BLENDER_ID_ENDPOINT', "https://www.blender.org/id")


def validate(token):
    """Validate a token against the Blender ID server. This simple lookup
    returns a dictionary with the following keys:

    - message: a success message
    - valid: a boolean, stating if the token is valid
    - user: a dictionary with information regarding the user
    """
    payload = dict(
        token=token)
    try:
        r = requests.post("{0}/u/validate_token".format(
            SystemUtility.blender_id_endpoint()), data=payload)
    except requests.exceptions.ConnectionError as e:
        raise e

    if r.status_code == 200:
        response = r.json()
        validation_result = dict(
            message=response['message'],
            valid=response['valid'],
            user=response['user'])
    else:
        validation_result = dict(valid=False)
    return validation_result


def validate_token():
    """Validate the token provided in the request and populate the current_user
    flask.g object, so that permissions and access to a resource can be defined
    from it.
    """
    if not request.authorization:
        # If no authorization headers are provided, we are getting a request
        # from a non logged in user. Proceed accordingly.
        return None

    current_user = {}

    token = request.authorization.username
    tokens = app.data.driver.db['tokens']

    lookup = {'token': token, 'expire_time': {"$gt": datetime.now()}}
    db_token = tokens.find_one(lookup)
    if not db_token:
        # If no valid token is found, we issue a new request to the Blender ID
        # to verify the validity of the token. We will get basic user info if
        # the user is authorized and we will make a new token.
        validation = validate(token)
        if validation['valid']:
            users = app.data.driver.db['users']
            email = validation['user']['email']
            db_user = users.find_one({'email': email})
            tmpname = email.split('@')[0]
            if not db_user:
                user_data = {
                    'first_name': tmpname,
                    'last_name': tmpname,
                    'email': email,
                }
                r = post_internal('users', user_data)
                user_id = r[0]['_id']
                groups = None
            else:
                user_id = db_user['_id']
                groups = db_user['groups']

            token_data = {
                'user': user_id,
                'token': token,
                'expire_time': datetime.now() + timedelta(hours=1)
            }
            post_internal('tokens', token_data)
            current_user = dict(
                user_id=user_id,
                token=token,
                groups=groups,
                token_expire_time=datetime.now() + timedelta(hours=1))
            #return token_data
        else:
            return None
    else:
        users = app.data.driver.db['users']
        db_user = users.find_one(db_token['user'])
        current_user = dict(
            user_id=db_token['user'],
            token=db_token['token'],
            groups=db_user['groups'],
            token_expire_time=db_token['expire_time'])

    setattr(g, 'current_user', current_user)


class TokensAuth(TokenAuth):
    def check_auth(self, token, allowed_roles, resource, method):
        if not token:
            return False

        validate_token()

        # if dbtoken:
        #     check_permissions(dbtoken['user'])
        #     return True

        # return validation['valid']
        return True


class BasicsAuth(BasicAuth):
    def check_auth(self, username, password, allowed_roles, resource, method):
        # return username == 'admin' and password == 'secret'
        print username
        print password
        return True


class CustomTokenAuth(BasicsAuth):
    """Switch between Basic and Token auth"""
    def __init__(self):
        self.token_auth = TokensAuth()
        self.authorized_protected = BasicsAuth.authorized

    def authorized(self, allowed_roles, resource, method):
        # if resource == 'tokens':
        if False:
            return self.authorized_protected(
                self, allowed_roles, resource, method)
        else:
            print 'is auth'
            return self.token_auth.authorized(allowed_roles, resource, method)

    def authorized_protected(self):
        pass


class NewAuth(TokenAuth):
    def check_auth(self, token, allowed_roles, resource, method):
        if not token:
            return False
        else:
            print '---'
            print 'validating'
            print token
            print resource
            print method
            print '---'
            validate_token()

        return True


class ValidateCustomFields(Validator):
    def convert_properties(self, properties, node_schema):
        for prop in node_schema:
            if not prop in properties:
                continue
            schema_prop = node_schema[prop]
            prop_type = schema_prop['type']
            if prop_type == 'dict':
                properties[prop] = self.convert_properties(
                    properties[prop], schema_prop['schema'])
            if prop_type == 'list':
                if properties[prop] in ['', '[]']:
                    properties[prop] = []
                for k, val in enumerate(properties[prop]):
                    if not 'schema' in schema_prop:
                        continue
                    item_schema = {'item': schema_prop['schema']}
                    item_prop = {'item': properties[prop][k]}
                    properties[prop][k] = self.convert_properties(
                        item_prop, item_schema)['item']
            # Convert datetime string to RFC1123 datetime
            elif prop_type == 'datetime':
                prop_val = properties[prop]
                properties[prop] = datetime.strptime(prop_val, RFC1123_DATE_FORMAT)
            elif prop_type == 'objectid':
                prop_val = properties[prop]
                if prop_val:
                    properties[prop] = ObjectId(prop_val)
                else:
                    properties[prop] = None

        return properties

    def _validate_valid_properties(self, valid_properties, field, value):
        node_types = app.data.driver.db['node_types']
        lookup = {}
        lookup['_id'] = ObjectId(self.document['node_type'])
        node_type = node_types.find_one(lookup)

        try:
            value = self.convert_properties(value, node_type['dyn_schema'])
        except Exception, e:
            print ("Error converting: {0}".format(e))
        #print (value)

        v = Validator(node_type['dyn_schema'])
        val = v.validate(value)

        if val:
            return True
        else:
            try:
                print (val.errors)
            except:
                pass
            self._error(
                field, "Error validating properties")


def post_item(entry, data):
    return post_internal(entry, data)

# We specify a settings.py file because when running on wsgi we can't detect it
# automatically. The default path (which work in Docker) can be overriden with
# an env variable.
settings_path = os.environ.get('EVE_SETTINGS', '/data/dev/pillar/pillar/settings.py')
app = Eve(settings=settings_path, validator=ValidateCustomFields, auth=NewAuth)

import config
app.config.from_object(config.Deployment)

client = MongoClient(app.config['MONGO_HOST'], 27017)
db = client.eve


def global_validation():
    token_data = validate_token()
    if token_data:
        setattr(g, 'token_data', token_data)
        #setattr(g, 'validate', validate(token_data['token']))
        check_permissions(token_data['user'], app.data.driver)
    else:
        print 'NO TOKEN'


def pre_GET_nodes(request, lookup):
    # Only get allowed documents
    global_validation()
    # print ("Get")
    # print ("Owner: {0}".format(g.get('owner_permissions')))
    # print ("World: {0}".format(g.get('world_permissions')))
    return pre_GET(request, lookup, app.data.driver)


def pre_PUT_nodes(request, lookup):
    # Only Update allowed documents
    global_validation()
    # print ("Put")
    # print ("Owner: {0}".format(g.get('owner_permissions')))
    # print ("World: {0}".format(g.get('world_permissions')))
    return pre_PUT(request, lookup, app.data.driver)


def pre_PATCH_nodes(request):
    return pre_PATCH(request, app.data.driver)


def pre_POST_nodes(request):
    # global_validation()
    # print ("Post")
    # print ("World: {0}".format(g.get('world_permissions')))
    # print ("Group: {0}".format(g.get('groups_permissions')))
    # return pre_POST(request, app.data.driver)
    print 'pre posting'
    print request


def pre_DELETE_nodes(request, lookup):
    # Only Delete allowed documents
    global_validation()
    # print ("Delete")
    # print ("Owner: {0}".format(type_owner_permissions))
    # print ("World: {0}".format(type_world_permissions))
    # print ("Groups: {0}".format(type_groups_permissions))
    return pre_DELETE(request, lookup, app.data.driver)


#app.on_pre_GET_nodes += pre_GET_nodes
app.on_pre_POST_nodes += pre_POST_nodes
# app.on_pre_PATCH_nodes += pre_PATCH_nodes
#app.on_pre_PUT_nodes += pre_PUT_nodes
app.on_pre_DELETE_nodes += pre_DELETE_nodes


def check_permissions(resource, method):
    """Check user permissions to access a node. We look up node permissions from
    world to groups to users and match them with the computed user permissions.
    If there is not match, we return 403.
    """
    current_user = g.get('current_user', None)

    if 'permissions' in resource:
        # If permissions are embedde in the node (this overrides any other
        # permission previously set)
        resource_permissions = resource['permissions']
    elif type(resource['node_type']) is dict:
        # If the node_type is embedded in the document, extract permissions
        # from there
        resource_permissions = resource['node_type']['permissions']
    else:
        # If the node_type is referenced with an ObjectID (was not embedded on
        # request) query for if from the database and get the permissions
        node_types_collection = app.data.driver.db['node_types']
        node_type = node_types_collection.find_one(resource['node_type'])
        resource_permissions = node_type['permissions']

    if current_user:
        # If the user is authenticated, proceed to compare the group permissions
        for permission in resource_permissions['groups']:
            if permission['group'] in current_user['groups']:
                if method in permission['methods']:
                    return

        for permission in resource_permissions['users']:
            if current_user['user_id'] == permission['user']:
                if method in permission['methods']:
                    return

    # Check if the node is public or private. This must be set for non logged
    # in users to see the content. For most BI projects this is on by default,
    # while for private project this will not be set at all.
    if 'world' in permissions and method in permissions['world']:
        return

    abort(403)

def before_returning_node(response):
    # Run validation process, since GET on nodes entry point is public
    validate_token()
    check_permissions(response, 'GET')

def before_replacing_node(item, original):
    check_permissions(original, 'PUT')

def before_inserting_nodes(items):
    for item in items:
        check_permissions(item, 'POST')

app.on_fetched_item_nodes += before_returning_node
app.on_replace_nodes += before_replacing_node
app.on_insert_nodes += before_inserting_nodes


def post_GET_user(request, payload):
    print 'computing permissions'
    json_data = json.loads(payload.data)
    # Check if we are querying the users endpoint (instead of the single user)
    if json_data.get('_id') is None:
        return
    # json_data['computed_permissions'] = \
    #     compute_permissions(json_data['_id'], app.data.driver)
    payload.data = json.dumps(json_data)

app.on_post_GET_users += post_GET_user

from modules.file_storage import process_file

def post_POST_files(request, payload):
    """After an file object has been created, we do the necessary processing
    and further update it.
    """
    process_file(request.get_json())


#app.on_pre_POST_files += pre_POST_files
app.on_post_POST_files += post_POST_files

from utils.cdn import hash_file_path
# Hook to check the backend of a file resource, to build an appropriate link
# that can be used by the client to retrieve the actual file.
def generate_link(backend, path):
    if backend == 'pillar':
        link = url_for('file_storage.index', file_name=path, _external=True)
    elif backend == 'cdnsun':
        link = hash_file_path(path, None)
    else:
        link = None
    return link

def before_returning_file(response):
    response['link'] = generate_link(response['backend'], response['path'])

def before_returning_files(response):
    for item in response['_items']:
        item['link'] = generate_link(item['backend'], item['path'])


app.on_fetched_item_files += before_returning_file
app.on_fetched_resource_files += before_returning_files

# The file_storage module needs app to be defined
from modules.file_storage import file_storage
#from modules.file_storage.serve import *
app.register_blueprint(file_storage, url_prefix='/storage')
