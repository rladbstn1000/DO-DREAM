"""String-only canonical learning snapshots shared with Spring's indexing ledger."""
import hashlib
import json
import re
import html

MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
MAX_CHUNKS = 500
BATCH_SIZE = 32
INDEX_SPEC = 'local-hash8-content-v1'
INDEX_SPECS = frozenset((INDEX_SPEC, 'local-hash8-content-v2'))
DIMENSION = 8


def text(value, default=''):
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError('Index source text must be a string')
    if any((ord(char) < 32 and char not in '\t\n\r') or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError('Index source contains invalid characters')
    return value


def array(value):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError('Invalid index source structure')
    return value


def normalize_source(source, kind):
    if not isinstance(source, dict) or kind not in ('MATERIAL', 'PDF'):
        raise ValueError('Invalid index source')
    blocks = []
    if 'chapters' in source:
        for chapter in array(source.get('chapters')):
            if chapter.get('type') != 'content':
                continue
            content = text(chapter.get('content'))
            if content.strip() and '새 챕터의 내용을 입력하세요' not in content:
                blocks.append({'text': content, 'type': 'content'})
    elif kind == 'PDF':
        wrapped = source.get('parsedData', source)
        if not isinstance(wrapped, dict):
            raise ValueError('Invalid initial index source')
        for item in array(wrapped.get('data')):
            for title_item in array(item.get('titles')):
                title = text(title_item.get('title'))
                if '개념' in title and 'check' in title.lower():
                    continue
                for section in array(title_item.get('s_titles')):
                    subtitle = text(section.get('s_title'))
                    if '개념' in subtitle and 'check' in subtitle.lower():
                        continue
                    content = text(section.get('contents'))
                    if content.strip():
                        blocks.append({'text': title+'\n'+subtitle+'\n'+content, 'type': 'content'})
                    for child in array(section.get('ss_titles')):
                        child_title = text(child.get('ss_title'))
                        if '개념' in child_title and 'check' in child_title.lower():
                            continue
                        content = text(child.get('contents'))
                        if content.strip():
                            blocks.append({'text': title+'\n'+subtitle+'\n'+child_title+'\n'+content, 'type': 'content'})
    else:
        raise ValueError('Expected material chapters')
    if not blocks:
        raise ValueError('Empty learning source')
    return snapshot({'blocks': blocks})


def snapshot(value):
    if type(value) is not dict or set(value) != {'blocks'}:
        raise ValueError('Invalid snapshot structure')
    blocks = array(value['blocks'])
    if len(blocks) > MAX_CHUNKS:
        raise ValueError('Too many source blocks')
    for block in blocks:
        if set(block) != {'text', 'type'} or block['type'] != 'content':
            raise ValueError('Only learning content may be indexed')
        text(block['text'])
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    encoded = raw.encode('utf-8')
    if len(encoded) > MAX_SNAPSHOT_BYTES:
        raise ValueError('Index snapshot exceeds size limit')
    return raw, hashlib.sha256(encoded).hexdigest(), len(encoded)


def parse_snapshot(raw, digest, byte_count):
    encoded = raw.encode('utf-8')
    if len(encoded) != byte_count or len(encoded) > MAX_SNAPSHOT_BYTES or hashlib.sha256(encoded).hexdigest() != digest:
        raise ValueError('Index source hash mismatch')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate snapshot field')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    canonical, _, _ = snapshot(value)
    if canonical != raw:
        raise ValueError('Noncanonical index snapshot')
    return value


def make_chunks(source, resource_kind, resource_id, revision, source_hash, spec):
    if spec not in INDEX_SPECS:
        raise ValueError('Unsupported index specification')
    chunks = []
    for block in source['blocks']:
        # Keep the original canonical HTML/text in the source ledger; rendering is
        # part of the versioned index specification and never includes quiz blocks.
        content = re.sub(r'<br\s*/?>', '\n', block['text'], flags=re.IGNORECASE)
        content = ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', content)).split())
        if not content:
            continue
        for offset in range(0, len(content), 900):
            chunk = content[offset:offset + 1000]
            position = len(chunks)
            digest = hashlib.sha256(chunk.encode()).hexdigest()
            identity = f'{resource_kind}:{resource_id}:{revision}:{spec}:{position}:content:{digest}'
            chunks.append({'id': hashlib.sha256(identity.encode()).hexdigest(), 'document': chunk,
                'metadata': {'resource_kind': resource_kind, 'resource_id': str(resource_id),
                    'source_revision': str(revision), 'source_hash': source_hash, 'index_spec': spec,
                    'position': position, 'type': 'content', 'content_hash': digest}})
            if len(chunks) > MAX_CHUNKS:
                raise ValueError('Index chunk limit exceeded')
            if offset + 1000 >= len(content):
                break
    if not chunks:
        raise ValueError('EMPTY_SOURCE')
    return chunks
