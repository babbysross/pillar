import logging
import typing
import bson

from flask_script import Manager

from pillar import current_app
from pillar.api.search import index

log = logging.getLogger(__name__)

manager_elastic = Manager(
    current_app, usage="Elastic utilities")

name_to_task = {
    'nodes': index.ResetNodeIndex,
    'users': index.ResetUserIndex,
}


@manager_elastic.option('indices', nargs='*')
def reset_index(indices):
    """
    Destroy and recreate elastic indices

    nodes, users
    """

    with current_app.app_context():
        if not indices:
            indices = name_to_task.keys()

        for elk_index in indices:
            try:
                task = name_to_task[elk_index]()
            except KeyError:
                raise SystemError('Unknown elk_index, choose from %s' %
                                  (', '.join(name_to_task.keys())))
            task.execute()


def _reindex_users():
    db = current_app.db()
    users_coll = db['users']
    user_count = users_coll.count()

    log.debug('Reindexing users %d in Elastic', user_count)

    from pillar.celery.search_index_tasks import prepare_user_data
    from pillar.api.search import elastic_indexing

    for user in users_coll.find():
        to_index = prepare_user_data('', user=user)
        if not to_index:
            log.debug('missing user..')
            continue

        try:
            elastic_indexing.push_updated_user(to_index)
        except(KeyError, AttributeError):
            log.exception('Field is missing for %s', user)
            continue


def _public_project_ids() -> typing.List[bson.ObjectId]:
    """Returns a list of ObjectIDs of public projects.

    Memoized in setup_app().
    """

    proj_coll = current_app.db('projects')
    result = proj_coll.find({'is_private': False}, {'_id': 1})
    return [p['_id'] for p in result]


def _reindex_nodes():
    db = current_app.db()
    nodes_coll = db['nodes']
    nodes_coll = nodes_coll.find({'project': {'$in': _public_project_ids()}})
    node_count = nodes_coll.count()

    log.debug('Reindexing nodes %d in Elastic', node_count)

    from pillar.celery.search_index_tasks import prepare_node_data
    from pillar.api.search import elastic_indexing

    for node in nodes_coll:
        try:
            to_index = prepare_node_data('', node=node)
            elastic_indexing.index_node_save(to_index)
        except (KeyError, AttributeError):
            log.exception('Field is missing for %s', node)
            continue


@manager_elastic.option('indexname', nargs='?')
def reindex(indexname=''):
    if not indexname:
        log.info('reindex everything..')
        _reindex_nodes()
        _reindex_users()
    elif indexname == 'users':
        log.info('Indexing %s', indexname)
        _reindex_users()
    elif indexname == 'nodes':
        log.info('Indexing %s', indexname)
        _reindex_nodes()
