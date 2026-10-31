"""Register the complete experiment design and implementation before new inference."""
from validation_common import ROOT, WORKSPACE, sha, freeze, verify_lock, load


if __name__ == '__main__':
    verify_lock()
    protocol = load(ROOT/'protocol.json')
    freeze(ROOT/'PROTOCOL_LOCK.json', {
        'id':protocol['id'], 'protocol_sha256':sha(ROOT/'protocol.json'),
        'registration_scope':'Local reproducible preregistration; not a third-party timestamped public registry.',
        'implementation_sha256':{p.relative_to(WORKSPACE).as_posix():sha(p) for p in sorted(ROOT.glob('*.py'))},
    })
    print('Protocol and implementation sealed; no model calls')
