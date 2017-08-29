import logging

from eve.methods.get import get
from flask import Blueprint

from pillar.api.utils import jsonify
from pillar.api.utils.authorization import require_login
from pillar.auth import current_user

log = logging.getLogger(__name__)
blueprint_api = Blueprint('users_api', __name__)


@blueprint_api.route('/me')
@require_login()
def my_info():
    eve_resp, _, _, status, _ = get('users', {'_id': current_user.user_id})
    resp = jsonify(eve_resp['_items'][0], status=status)
    return resp


