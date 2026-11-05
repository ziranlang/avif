import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parent/'fixtures'
manifest = json.loads((root/'manifest.json').read_text())
for name, digest in manifest['sha256'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == digest, name
print(f"AVIF fixture digests: {len(manifest['sha256'])} verified")
