import json
import logging
import typing

from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search, Q
from elasticsearch_dsl.query import Query

from pillar import current_app

log = logging.getLogger(__name__)

NODE_AGG_TERMS = ['node_type', 'media', 'tags', 'is_free']
USER_AGG_TERMS = ['roles', ]
ITEMS_PER_PAGE = 10

# Will be set in setup_app()
client: Elasticsearch = None


def add_aggs_to_search(search, agg_terms):
    """
    Add facets / aggregations to the search result
    """

    for term in agg_terms:
        search.aggs.bucket(term, 'terms', field=term)


def make_must(must: list, terms: dict) -> list:
    """ Given term parameters append must queries to the must list """

    for field, value in terms.items():
        if value:
            must.append({'match': {field: value}})

    return must


def nested_bool(must: list, should: list, terms: dict, *, index_alias: str) -> Search:
    """
    Create a nested bool, where the aggregation selection is a must.

    :param index_alias: 'USER' or 'NODE', see ELASTIC_INDICES config.
    """
    must = make_must(must, terms)
    bool_query = Q('bool', should=should)
    must.append(bool_query)
    bool_query = Q('bool', must=must)

    index = current_app.config['ELASTIC_INDICES'][index_alias]
    search = Search(using=client, index=index)
    search.query = bool_query

    return search


def do_node_search(query: str, terms: dict, page: int, project_id: str='') -> dict:
    """
    Given user query input and term refinements
    search for public published nodes
    """

    should = [
        Q('match', name=query),

        {"match": {"project.name": query}},
        {"match": {"user.name": query}},

        Q('match', description=query),
        Q('term', media=query),
        Q('term', tags=query),
    ]

    must = []
    if project_id:
        must.append({'term': {'project.id': project_id}})

    if not query:
        should = []

    search = nested_bool(must, should, terms, index_alias='NODE')
    if not query:
        search = search.sort('-created_at')
    add_aggs_to_search(search, NODE_AGG_TERMS)
    search = paginate(search, page)

    if log.isEnabledFor(logging.DEBUG):
        log.debug(json.dumps(search.to_dict(), indent=4))

    response = search.execute()

    if log.isEnabledFor(logging.DEBUG):
        log.debug(json.dumps(response.to_dict(), indent=4))

    return response.to_dict()


def do_user_search(query: str, terms: dict, page: int) -> dict:
    """ return user objects represented in elasicsearch result dict"""

    must, should = _common_user_search(query)
    search = nested_bool(must, should, terms, index_alias='USER')
    add_aggs_to_search(search, USER_AGG_TERMS)
    search = paginate(search, page)

    if log.isEnabledFor(logging.DEBUG):
        log.debug(json.dumps(search.to_dict(), indent=4))

    response = search.execute()

    if log.isEnabledFor(logging.DEBUG):
        log.debug(json.dumps(response.to_dict(), indent=4))

    return response.to_dict()


def _common_user_search(query: str) -> (typing.List[Query], typing.List[Query]):
    """Construct (must,shoud) for regular + admin user search."""
    if not query:
        return [], []

    should = []

    if '@' in query:
        should.append({'term': {'email_exact': {'value': query, 'boost': 50}}})
        email_boost = 25
    else:
        email_boost = 1

    should.extend([
        Q('match', username=query),
        Q('match', full_name=query),
        {'match': {'email': {'query': query, 'boost': email_boost}}},
        {'term': {'username_exact': {'value': query, 'boost': 50}}},
    ])

    return [], should


def do_user_search_admin(query: str, terms: dict, page: int) -> dict:
    """
    return users seach result dict object
    search all user fields and provide aggregation information
    """

    must, should = _common_user_search(query)

    if query:
        # We most likely got and id field. we should find it.
        if len(query) == len('563aca02c379cf0005e8e17d'):
            should.append({'term': {
                'objectID': {
                    'value': query,  # the thing we're looking for
                    'boost': 100,  # how much more it counts for the score
                }
            }})

    search = nested_bool(must, should, terms, index_alias='USER')
    add_aggs_to_search(search, USER_AGG_TERMS)
    search = paginate(search, page)

    if log.isEnabledFor(logging.DEBUG):
        log.debug(json.dumps(search.to_dict(), indent=4))

    response = search.execute()

    if log.isEnabledFor(logging.DEBUG):
        log.debug(json.dumps(response.to_dict(), indent=4))

    return response.to_dict()


def paginate(search: Search, page_idx: int) -> Search:
    return search[page_idx * ITEMS_PER_PAGE:(page_idx + 1) * ITEMS_PER_PAGE]


def setup_app(app):
    global client

    hosts = app.config['ELASTIC_SEARCH_HOSTS']
    log.getChild('setup_app').info('Creating ElasticSearch client for %s', hosts)
    client = Elasticsearch(hosts)
