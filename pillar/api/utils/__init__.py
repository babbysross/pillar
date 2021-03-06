import base64
import copy
import datetime
import functools
import hashlib
import json
import logging
import random
import typing
import urllib.request, urllib.parse, urllib.error

import bson.objectid
import bson.tz_util
from eve import RFC1123_DATE_FORMAT
from flask import current_app
from werkzeug import exceptions as wz_exceptions
import pymongo.results

log = logging.getLogger(__name__)


def node_setattr(node, key, value):
    """Sets a node property by dotted key.

    Modifies the node in-place. Deletes None values.

    :type node: dict
    :type key: str
    :param value: the value to set, or None to delete the key.
    """

    set_on = node
    while key and '.' in key:
        head, key = key.split('.', 1)
        set_on = set_on[head]

    if value is None:
        set_on.pop(key, None)
    else:
        set_on[key] = value


def remove_private_keys(document):
    """Removes any key that starts with an underscore, returns result as new
    dictionary.
    """
    doc_copy = copy.deepcopy(document)
    for key in list(doc_copy.keys()):
        if key.startswith('_'):
            del doc_copy[key]

    try:
        del doc_copy['allowed_methods']
    except KeyError:
        pass

    return doc_copy


class PillarJSONEncoder(json.JSONEncoder):
    """JSON encoder with support for Pillar resources."""

    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.strftime(RFC1123_DATE_FORMAT)

        if isinstance(obj, bson.ObjectId):
            return str(obj)

        if isinstance(obj, pymongo.results.UpdateResult):
            return obj.raw_result

        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


def dumps(mongo_doc, **kwargs):
    """json.dumps() for MongoDB documents."""
    return json.dumps(mongo_doc, cls=PillarJSONEncoder, **kwargs)


def jsonify(mongo_doc, status=200, headers=None):
    """JSonifies a Mongo document into a Flask response object."""

    return current_app.response_class(dumps(mongo_doc),
                                      mimetype='application/json',
                                      status=status,
                                      headers=headers)


def bsonify(mongo_doc, status=200, headers=None):
    """BSonifies a Mongo document into a Flask response object."""

    import bson

    data = bson.BSON.encode(mongo_doc)
    return current_app.response_class(data,
                                      mimetype='application/bson',
                                      status=status,
                                      headers=headers)


def skip_when_testing(func):
    """Decorator, skips the decorated function when app.config['TESTING']"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if current_app.config['TESTING']:
            log.debug('Skipping call to %s(...) due to TESTING', func.__name__)
            return None

        return func(*args, **kwargs)

    return wrapper


def project_get_node_type(project_document, node_type_node_name):
    """Return a node_type subdocument for a project. If none is found, return
    None.
    """

    if project_document is None:
        return None

    return next((node_type for node_type in project_document['node_types']
                 if node_type['name'] == node_type_node_name), None)


def str2id(document_id: str) -> bson.ObjectId:
    """Returns the document ID as ObjectID, or raises a BadRequest exception.

    :raises: wz_exceptions.BadRequest
    """

    if not document_id:
        log.debug('str2id(%r): Invalid Object ID', document_id)
        raise wz_exceptions.BadRequest('Invalid object ID %r' % document_id)

    try:
        return bson.ObjectId(document_id)
    except (bson.objectid.InvalidId, TypeError):
        log.debug('str2id(%r): Invalid Object ID', document_id)
        raise wz_exceptions.BadRequest('Invalid object ID %r' % document_id)


def gravatar(email: str, size=64) -> typing.Optional[str]:
    if email is None:
        return None

    parameters = {'s': str(size), 'd': 'mm'}
    return "https://www.gravatar.com/avatar/" + \
           hashlib.md5(email.encode()).hexdigest() + \
           "?" + urllib.parse.urlencode(parameters)


class MetaFalsey(type):
    def __bool__(cls):
        return False


class DoesNotExistMeta(MetaFalsey):
    def __repr__(cls) -> str:
        return 'DoesNotExist'


class DoesNotExist(object, metaclass=DoesNotExistMeta):
    """Returned as value by doc_diff if a value does not exist."""


def doc_diff(doc1, doc2, *, falsey_is_equal=True, superkey: str = None):
    """Generator, yields differences between documents.

    Yields changes as (key, value in doc1, value in doc2) tuples, where
    the value can also be the DoesNotExist class. Does not report changed
    private keys (i.e. the standard Eve keys starting with underscores).

    Sub-documents (i.e. dicts) are recursed, and dot notation is used
    for the keys if changes are found.

    If falsey_is_equal=True, all Falsey values compare as equal, i.e. this
    function won't report differences between DoesNotExist, False, '', and 0.
    """

    private_keys = {'_id', '_etag', '_deleted', '_updated', '_created'}

    def combine_key(some_key):
        """Combine this key with the superkey.

        Keep the key type the same, unless we have to combine with a superkey.
        """
        if not superkey:
            return some_key
        if isinstance(some_key, str) and some_key[0] == '[':
            return f'{superkey}{some_key}'
        return f'{superkey}.{some_key}'

    if doc1 is doc2:
        return

    if falsey_is_equal and not bool(doc1) and not bool(doc2):
        return

    if isinstance(doc1, dict) and isinstance(doc2, dict):
        for key in set(doc1.keys()).union(set(doc2.keys())):
            if key in private_keys:
                continue

            val1 = doc1.get(key, DoesNotExist)
            val2 = doc2.get(key, DoesNotExist)

            yield from doc_diff(val1, val2,
                                falsey_is_equal=falsey_is_equal,
                                superkey=combine_key(key))
        return

    if isinstance(doc1, list) and isinstance(doc2, list):
        for idx in range(max(len(doc1), len(doc2))):
            try:
                item1 = doc1[idx]
            except IndexError:
                item1 = DoesNotExist
            try:
                item2 = doc2[idx]
            except IndexError:
                item2 = DoesNotExist

            subkey = f'[{idx}]'
            if item1 is DoesNotExist or item2 is DoesNotExist:
                yield combine_key(subkey), item1, item2
            else:
                yield from doc_diff(item1, item2,
                                    falsey_is_equal=falsey_is_equal,
                                    superkey=combine_key(subkey))
        return

    if doc1 != doc2:
        yield superkey, doc1, doc2


def random_etag() -> str:
    """Random string usable as etag."""

    randbytes = random.getrandbits(256).to_bytes(32, 'big')
    return base64.b64encode(randbytes)[:-1].decode()


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(tz=bson.tz_util.utc)
