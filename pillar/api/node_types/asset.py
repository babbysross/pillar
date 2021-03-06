from pillar.api.node_types import _file_embedded_schema, attachments_embedded_schema

node_type_asset = {
    'name': 'asset',
    'description': 'Basic Asset Type',
    # This data type does not have parent limitations (can be child
    # of any node). An empty parent declaration is required.
    'parent': ['group', ],
    'dyn_schema': {
        'status': {
            'type': 'string',
            'allowed': [
                'published',
                'pending',
                'processing'
            ],
        },
        # Used for sorting within the context of a group
        'order': {
            'type': 'integer'
        },
        # We expose the type of asset we point to. Usually image, video,
        # zipfile, ect.
        'content_type': {
            'type': 'string'
        },
        # We point to the original file (and use it to extract any relevant
        # variation useful for our scope).
        'file': _file_embedded_schema,
        'attachments': attachments_embedded_schema,
        # Tags for search
        'tags': {
            'type': 'list',
            'schema': {
                'type': 'string'
            }
        },
        # Simple string to represent hierarchical categories. Should follow
        # this schema: "Root > Nested Category > One More Nested Category"
        'categories': {
            'type': 'string'
        },
        'license_type': {
            'default': 'cc-by',
            'type': 'string',
            'allowed': [
                'cc-by',
                'cc-0',
                'cc-by-sa',
                'cc-by-nd',
                'cc-by-nc',
                'copyright'
            ]
        },
        'license_notes': {
            'type': 'string'
        },
    },
    'form_schema': {
        'content_type': {'visible': False},
        'order': {'visible': False},
        'tags': {'visible': False},
        'categories': {'visible': False},
        'license_type': {'visible': False},
        'license_notes': {'visible': False},
    },
}
