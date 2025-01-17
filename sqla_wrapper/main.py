import sqlalchemy as sa
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from sqlalchemy.util import get_cls_kwargs

from .routing import get_routing_class
from .default_model import get_default_model_class
from .default_meta import DefaultMeta
from .session_proxy import SessionProxy


class SQLAlchemy(SessionProxy):
    """This class is used to easily instantiate a SQLAlchemy connection to
    a database, to provide a base class for your models, and to get a session
    to interact with them.

    ```python
    db = SQLAlchemy({"default": <uri to database>}})

    class User(db.Model):
        login = Column(String(80), unique=True)
        passw_hash = Column(String(80))
    ```

    **IMPORTANT**

    In a web application or a multithreaded environment you need to call
    ``session.remove()`` when a request/thread ends. Use your framework's
    ``after_request`` hook, to do that. For example, in `Flask`:

    ```python
    app = Flask(…)
    db = SQLAlchemy(…)

    @app.teardown_appcontext
    def shutdown(response=None):
        db.remove()
        return response
    ```

    Use the ``db`` to interact with the data:

    ```python
    user = User('tiger')
    db.add(user)
    db.commit()
    # etc
    ```

    To query, you can use ``db.query``

    ```python
    db.query(User.id, User.email).all()
    db.query(User).filter_by(login == 'tiger').first()
    # etc.
    ```

    **Scoping**

    By default, sessions are scoped to the current thread, but he SQLAlchemy
    documentation recommends scoping the session to something more
    application-specific if you can, like a web request in a web app.

    To do that, you can use the ``scopefunc`` argument, passing a function that
    returns something unique (and hashable) like a request.
    """

    def __init__(
        self,
        databases=None,
        *,
        metadata=None,
        metaclass=None,
        model_class=None,
        scopefunc=None,
        **options
    ):
        self.databases = databases
        self.Model = self._make_declarative_base(model_class, metadata, metaclass)

        self._set_session_options(options)
        self.engines = {k: sa.create_engine(v, self.engine_options) for k, v in self.databases.items()}
        self.RoutingSession = get_routing_class(self.engines)
        self.Session = sessionmaker(class_=self.RoutingSession, **self.session_options)
        self._session = scoped_session(self.Session, scopefunc)

        _include_sqlalchemy(self)

    def _set_session_options(self, options):
        session_options = {}

        for arg in get_cls_kwargs(Session):
            if arg in options:
                session_options[arg] = options.pop(arg)

        options.setdefault("echo", False)
        self.engine_options = options

        session_options.setdefault("autoflush", True)
        session_options.setdefault("autocommit", False)
        self.session_options = session_options

    def _make_declarative_base(self, model_class, metaclass=None, metadata=None):
        """Creates the declarative base."""
        return declarative_base(
            name="Model",
            cls=model_class or get_default_model_class(self),
            metaclass=metaclass or DefaultMeta,
            metadata=metadata,
        )

    @property
    def metadata(self):
        """Proxy for ``Model.metadata``."""
        return self.Model.metadata

    def create_all(self, engine='default', *args, **kwargs):
        """Creates all tables."""
        _engine = self.engines[engine]
        kwargs.setdefault("bind", _engine)
        self.Model.metadata.create_all(*args, **kwargs)

    def drop_all(self, engine='default', *args, **kwargs):
        """Drops all tables."""
        _engine = self.engines[engine]
        kwargs.setdefault("bind", _engine)
        self.Model.metadata.drop_all(*args, **kwargs)

    def reconfigure(self, **kwargs):
        """Updates the session options."""
        self._session.remove()
        self.session_options.update(**kwargs)
        self._session.configure(**self.session_options)

    def __repr__(self):
        return "<SQLAlchemy('{}')>".format(str(self.databases))


def _include_sqlalchemy(obj):
    for module in sa, sa.orm:
        for key in module.__all__:
            if not hasattr(obj, key):
                setattr(obj, key, getattr(module, key))
    obj.event = sa.event
