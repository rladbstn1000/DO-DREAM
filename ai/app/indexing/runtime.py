"""Pure selection gates; importing this module never constructs a paid client."""
from app.config import AI_MODE
from app.indexing.source import LOCAL_INDEX_SPECS, LIVE_SPEC


def scope_for(pointer, purpose):
    from app.providers import CallScope
    if pointer.get('resource_kind') != 'MATERIAL':
        raise ValueError('Live evaluation supports approved materials only')
    return CallScope(material_id=pointer['resource_id'], user_id=pointer['user_id'],
        spec=pointer['spec'], source_revision=pointer['source_revision'],
        source_hash=pointer['source_hash'], purpose=purpose)


def authorize_pointer(pointer, purpose, role='api'):
    if AI_MODE == 'LOCAL_FAKE':
        if pointer['spec'] not in LOCAL_INDEX_SPECS:
            raise ValueError('Provider and embedding specification do not match')
        return
    if pointer['spec'] != LIVE_SPEC:
        raise ValueError('Provider and embedding specification do not match')
    from app.providers import authorize_scope
    authorize_scope(scope_for(pointer, purpose), role)


def provider(role):
    if AI_MODE != 'LIVE_OPENAI':
        raise RuntimeError('Paid providers are unavailable in LOCAL_FAKE')
    from app.providers import LiveOpenAI
    return LiveOpenAI.from_environment(role=role)
