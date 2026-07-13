import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_local = threading.local()

# Some mirrors reject unfamiliar clients, so every backend (requests, curl, aria2) presents
# the same User-Agent.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            # requests defaults to "gzip, deflate", and nginx ignores Range whenever a
            # content-coding is negotiated: it answers 200 with the whole file instead of
            # 206/416. That silently turns every resume into a fresh download. ISOs are
            # already compressed, so identity costs nothing and keeps Range working.
            "Accept-Encoding": "identity",
        }
    )
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def get_session() -> requests.Session:
    """A session private to the calling thread; requests.Session is not thread-safe."""
    session = getattr(_local, "session", None)
    if session is None:
        session = build_session()
        _local.session = session
    return session
