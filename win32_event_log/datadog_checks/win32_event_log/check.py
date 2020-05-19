# (C) Datadog, Inc. 2020-present
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)
from itertools import chain

import win32con
import win32event
import win32evtlog

from datadog_checks.base import AgentCheck, ConfigurationError, is_affirmative

from .filters import construct_query
from .legacy import Win32EventLogWMI
from .utils import EventNamespace, parse_event_xml


class Win32EventLogCheck(AgentCheck):
    # https://docs.microsoft.com/en-us/windows/win32/api/winevt/ne-winevt-evt_rpc_login_flags
    LOGIN_FLAGS = {
        'default': win32evtlog.EvtRpcLoginAuthDefault,
        'negotiate': win32evtlog.EvtRpcLoginAuthNegotiate,
        'kerberos': win32evtlog.EvtRpcLoginAuthKerberos,
        'ntlm': win32evtlog.EvtRpcLoginAuthNTLM,
    }

    def __new__(cls, name, init_config, instances):
        instance = instances[0]

        if is_affirmative(instance.get('legacy_mode', True)):
            return Win32EventLogWMI(name, init_config, instances)
        else:
            return super(Win32EventLogCheck, cls).__new__(cls)

    def __init__(self, name, init_config, instances):
        super(Win32EventLogCheck, self).__init__(name, init_config, instances)

        # Channel or log file to subscribe to
        self._path = self.instance.get('path', '')

        # Raw user-defined query or one we construct based on filters
        self._query = None

        # Create a pull subscription and its signaler on the first check run
        self._event_handle = None
        self._subscription = None

        # Session used for remote connections, or None if local connection
        self._session = None

        # Connection options
        self._timeout = int(self.instance.get('timeout', 5)) * 1000
        self._payload_size = int(self.instance.get('payload_size', 10))

        self.check_initializations.append(self.parse_config)
        self.check_initializations.append(self.create_session)
        self.check_initializations.append(self.create_subscription)

    def check(self, _):
        events, ns = self.get_events_and_namespace()
        if events is None:
            return

        for event in events:
            return event

    def poll_events(self):
        while True:

            # IMPORTANT: the subscription starts immediately so you must consume before waiting for the signal
            while True:
                # https://docs.microsoft.com/en-us/windows/win32/api/winevt/nf-winevt-evtnext
                # http://timgolden.me.uk/pywin32-docs/win32evtlog__EvtNext_meth.html
                events = win32evtlog.EvtNext(self._subscription, self._payload_size)
                if not events:
                    break

                for event in events:
                    yield event

            # https://docs.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobjectex
            # http://timgolden.me.uk/pywin32-docs/win32event__WaitForSingleObjectEx_meth.html
            wait_signal = win32event.WaitForSingleObjectEx(self._event_handle, self._timeout, True)

            # No more events, end check run
            if wait_signal != win32con.WAIT_OBJECT_0:
                break

    def parse_config(self):
        if not self._path:
            raise ConfigurationError('You must select a `path`.')

        query = self.instance.get('query')
        if query:
            self._query = query
            return

        filters = self.instance.get('filters', {})
        if not isinstance(filters, dict):
            raise ConfigurationError('The `filters` option must be a mapping.')

        for key, value in filters.items():
            if not isinstance(value, list) or not (isinstance(value, dict) and not value):
                raise ConfigurationError('Value for event filter `{}` must be an array or empty mapping.'.format(key))

        self._query = construct_query(filters)

        password = self.instance.get('password')
        if password:
            self.register_secret(password)

    def create_session(self):
        session_struct = self.get_session_struct()

        # No need for a remote connection
        if session_struct is None:
            return

        # https://docs.microsoft.com/en-us/windows/win32/api/winevt/nf-winevt-evtopensession
        # http://timgolden.me.uk/pywin32-docs/win32evtlog__EvtOpenSession_meth.html
        self._session = win32evtlog.EvtOpenSession(session_struct, win32evtlog.EvtRpcLogin, 0, 0)

    def create_subscription(self):
        # https://docs.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createeventa
        # http://timgolden.me.uk/pywin32-docs/win32event__CreateEvent_meth.html
        self._event_handle = win32event.CreateEvent(None, 0, 0, self.check_id)

        # https://docs.microsoft.com/en-us/windows/win32/api/winevt/nf-winevt-evtsubscribe
        # http://timgolden.me.uk/pywin32-docs/win32evtlog__EvtSubscribe_meth.html
        self._subscription = win32evtlog.EvtSubscribe(
            self._path,
            win32evtlog.EvtSubscribeStartAtOldestRecord,
            SignalEvent=self._event_handle,
            Query=self._query,
            Session=self._session,
        )

    def get_session_struct(self):
        server = self.instance.get('server', 'localhost')
        if server == 'localhost':
            return

        auth_type = self.instance.get('auth_type', 'default')
        if auth_type not in self.LOGIN_FLAGS:
            raise ConfigurationError('Invalid `auth_type`, must be one of: {}'.format(' | '.join(self.LOGIN_FLAGS)))

        user = self.instance.get('user')
        domain = self.instance.get('domain')
        password = self.instance.get('password')

        # https://docs.microsoft.com/en-us/windows/win32/api/winevt/ns-winevt-evt_rpc_login
        # http://timgolden.me.uk/pywin32-docs/PyEVT_RPC_LOGIN.html
        return server, user, domain, password, self.LOGIN_FLAGS[auth_type]

    def get_events_and_namespace(self):
        events = self.poll_events()

        try:
            first_event = next(events)
        except StopIteration:
            return None, None

        root = parse_event_xml(first_event)

        # It's unlikely that the schema manifest will change but we do this to be future-proof. See:
        # https://docs.microsoft.com/en-us/windows/win32/wes/writing-an-instrumentation-manifest
        namespace = root.nsmap.get(None, '')
        if namespace:
            namespace = '{{{}}}'.format(namespace)

        return chain((first_event,), events), EventNamespace(namespace)
