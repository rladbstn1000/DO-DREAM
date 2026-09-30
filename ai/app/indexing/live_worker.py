"""Execute one explicitly approved new job; never consume any broker queue."""
import argparse
import json


def main():
    from app.config import AI_MODE
    if AI_MODE != 'LIVE_OPENAI':
        raise RuntimeError('Manual live worker requires the guarded live configuration')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job_id')
    args = parser.parse_args()
    from app.indexing.store import identity
    from app.indexing.worker import process
    identity(args.job_id)
    # process -> claim_execution checks exact approved material/source/spec/owner
    # before obtaining an execution. LiveOpenAI repeats it before every request.
    try:
        result = process(args.job_id, manual_live=True)
    except Exception:
        result = {'status':'blocked','failure_code':'LIVE_SCOPE_NOT_AUTHORIZED'}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'active' else 1


if __name__ == '__main__':
    raise SystemExit(main())
