# -*- coding: utf-8 -*-

import os
import json
import urlparse
import unittest
import tempfile
import threading

from BaseHTTPServer import HTTPServer
from BaseHTTPServer import BaseHTTPRequestHandler

from smartfile import BasicClient
from smartfile import OAuthClient
from smartfile.errors import APIError
from smartfile.errors import RequestError


API_KEY = '8g1aq1UF2QfZTG47yEVhVLAFqyfDdp'
API_PASSWORD = '3II3UFD3pBAwy3Rbz8mVWBhJTA2Gvd'
CLIENT_TOKEN = '8oWot4KrppJDzfokDsHNJrND0Ay13s'
CLIENT_SECRET = '0I7BV6Bm3Rgfk73LL68vBp0u23KcKr'
ACCESS_TOKEN = 'hIlkipZNmwIJ28HQtQRcbGuXBePQp5'
ACCESS_SECRET = 'Scen1dwmVtWhjLpJfnilrfdc5OZWCJ'


class TestHTTPRequestHandler(BaseHTTPRequestHandler):
    """
    A simple handler that logs requests for examination.
    """
    class TestRequest(object):
        def __init__(self, method, path, query=None, data=None):
            self.method = method
            self.path = path
            self.query = query
            self.data = data

    def __init__(self, *args, **kwargs):
        self.verbose = kwargs.pop('verbose', False)
        BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

    def record(self, method, path, query=None, data=None):
        self.server.requests.append(TestHTTPRequestHandler.TestRequest(method,
                                    path, query=query, data=data))

    def respond(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write("Hello World!")

    def parse_and_record(self, method):
        urlp = urlparse.urlparse(self.path)
        query, data = urlparse.parse_qs(urlp.query), None
        if method == 'POST':
            l = int(self.headers['Content-Length'])
            data = urlparse.parse_qs(self.rfile.read(l))
        self.record(method, urlp.path, query=query, data=data)
        self.respond()

    def log_message(self, *args, **kwargs):
        if self.verbose:
            BaseHTTPRequestHandler.log_message(self, *args, **kwargs)

    def do_GET(self):
        self.parse_and_record('GET')

    def do_PUT(self):
        self.parse_and_record('PUT')

    def do_POST(self):
        self.parse_and_record('POST')

    def do_DELETE(self):
        self.parse_and_record('DELETE')


class TestHTTPServer(threading.Thread, HTTPServer):
    """
    A simple server that logs requests for examination. Provides some basic
    assertions that should aid in test development.
    """
    allow_reuse_address = True

    def __init__(self, address='127.0.0.1', port=0, handler=TestHTTPRequestHandler):
        HTTPServer.__init__(self, (address, port), handler)
        threading.Thread.__init__(self)
        self.requests = []
        self.setDaemon(True)
        self.start()

    def run(self):
        self.serve_forever()


class TestServerTestCase(unittest.TestCase):
    """
    Test case that starts our test HTTP server.
    """
    def setUp(self):
        self.server = TestHTTPServer()

    def tearDown(self):
        self.server.shutdown()

    def assertRequestCount(self, num=1):
        requests = len(self.server.requests)
        if requests > num:
            raise AssertionError('More than %s request performed: %s' % (num,
                                 requests))
        elif requests < num:
            raise AssertionError('Less than %s request performed' % num)

    def assertMethod(self, method):
        try:
            request = self.server.requests[0]
        except IndexError:
            raise AssertionError('Cannot assert method without request')
        if request.method != method:
            raise AssertionError('%s is not %s method' % (method,
                                 request.method))

    def assertPath(self, path):
        try:
            request = self.server.requests[0]
        except IndexError:
            raise AssertionError('Cannot assert path without request')
        if request.path != path:
            raise AssertionError('"%s" is not equal to "%s"' % (path,
                                 request.path))


class BasicTestCase(TestServerTestCase):
    def getClient(self, **kwargs):
        kwargs.setdefault('key', API_KEY)
        kwargs.setdefault('password', API_PASSWORD)
        kwargs.setdefault('url', 'http://127.0.0.1:%s/' %
                          self.server.server_port)
        return BasicClient(**kwargs)


class OAuthTestCase(TestServerTestCase):
    def getClient(self, **kwargs):
        kwargs.setdefault('client_token', CLIENT_TOKEN)
        kwargs.setdefault('client_secret', CLIENT_SECRET)
        kwargs.setdefault('access_token', ACCESS_TOKEN)
        kwargs.setdefault('access_secret', ACCESS_SECRET)
        kwargs.setdefault('url', 'http://127.0.0.1:%s/' %
                          self.server.server_port)
        return OAuthClient(**kwargs)


class UrlGenerationTestCase(object):
    "Tests that validate 'auto-generated' URLs."
    def test_with_path_id(self):
        client = self.getClient()
        client.get('/path/data', '/the/file/path')
        self.assertMethod('GET')
        self.assertPath('/api/{0}/path/data/the/file/path/'.format(
            client.version))

    def test_with_int_id(self):
        client = self.getClient()
        client.get('/access/user', 42)
        self.assertMethod('GET')
        self.assertPath('/api/{0}/access/user/42/'.format(client.version))

    def test_with_version(self):
        client = self.getClient(version='3.1')
        client.get('/ping')
        self.assertMethod('GET')
        self.assertPath('/api/{0}/ping/'.format(client.version))


class MethodTestCase(object):
    "Tests the HTTP methods used by CRUD methods."
    def test_call_is_GET(self):
        client = self.getClient()
        client('/user', 'bobafett')
        self.assertMethod('GET')

    def test_post_is_POST(self):
        client = self.getClient()
        client.post('/user', username='bobafett', email='bobafett@example.com')
        self.assertMethod('POST')

    def test_get_is_GET(self):
        client = self.getClient()
        client.get('/user', 'bobafett')
        self.assertMethod('GET')

    def test_put_is_PUT(self):
        client = self.getClient()
        client.put('/user', 'bobafett', full_name='Boba Fett')
        self.assertMethod('PUT')

    def test_delete_is_DELETE(self):
        client = self.getClient()
        client.delete('/user', 'bobafett')
        self.assertMethod('DELETE')


class DownloadTestCase(object):
    def test_file_response(self):
        client = self.getClient()
        r = client.get('/user')
        self.assertTrue(hasattr(r, 'read'), 'File-like object not returned.')
        self.assertEqual(r.read(), 'Hello World!')


class UploadTestCase(object):
    def test_file_upload(self):
        client = self.getClient()
        fd, t = tempfile.mkstemp()
        os.close(fd)
        try:
            client.post('/path/data', 'foobar.png', file=file(t))
        except Exception, e:
            self.fail('POSTing a file failed. %s' % e)
        finally:
            try:
                os.unlink(t)
            except:
                pass


class BasicEnvironTestCase(BasicTestCase):
    "Tests that the API client reads settings from ENV."
    def setUp(self):
        super(BasicEnvironTestCase, self).setUp()
        os.environ['SMARTFILE_API_KEY'] = API_KEY
        os.environ['SMARTFILE_API_PASSWORD'] = API_KEY

    def tearDown(self):
        super(BasicEnvironTestCase, self).tearDown()
        del os.environ['SMARTFILE_API_KEY']
        del os.environ['SMARTFILE_API_PASSWORD']

    def test_read_from_env(self):
        # Blank out the credentials, the client should read them from the
        # environment variables.
        client = self.getClient(key=None, password=None)
        client.get('/ping')
        self.assertMethod('GET')
        self.assertPath('/api/{0}/ping/'.format(client.version))


class OAuthEnvironTestCase(OAuthTestCase):
    "Tests that the API client reads settings from ENV."
    def setUp(self):
        super(OAuthEnvironTestCase, self).setUp()
        os.environ['SMARTFILE_CLIENT_TOKEN'] = CLIENT_TOKEN
        os.environ['SMARTFILE_CLIENT_SECRET'] = CLIENT_SECRET
        os.environ['SMARTFILE_ACCESS_TOKEN'] = ACCESS_TOKEN
        os.environ['SMARTFILE_ACCESS_SECRET'] = ACCESS_SECRET

    def tearDown(self):
        super(OAuthEnvironTestCase, self).tearDown()
        del os.environ['SMARTFILE_CLIENT_TOKEN']
        del os.environ['SMARTFILE_CLIENT_SECRET']
        del os.environ['SMARTFILE_ACCESS_TOKEN']
        del os.environ['SMARTFILE_ACCESS_SECRET']

    def test_read_from_env(self):
        # Blank out the credentials, the client should read them from the
        # environment variables.
        client = self.getClient(client_token=None, client_secret=None)
        client.get('/ping')
        self.assertMethod('GET')
        self.assertPath('/api/{0}/ping/'.format(client.version))


class BasicClientTestCase(DownloadTestCase, UploadTestCase, MethodTestCase,
                          UrlGenerationTestCase, BasicTestCase):
    def test_blank_credentials(self):
        self.assertRaises(APIError, self.getClient, key='', password='')

    def test_netrc(self):
        fd, t = tempfile.mkstemp()
        try:
            try:
                address = self.server.server_address
                if isinstance(address, tuple):
                    address, port = address
                else:
                    port = self.server.server_port
                netrc = "machine 127.0.0.1:%s\n  login %s\n  password %s" % (
                        port, API_KEY, API_PASSWORD)
                os.write(fd, netrc)
            finally:
                os.close(fd)
            client = self.getClient(key=None, password=None, netrcfile=t)
            client.get('/ping')
            self.assertMethod('GET')
            self.assertPath('/api/{0}/ping/'.format(client.version))
        finally:
            try:
                os.unlink(t)
            except:
                pass


class OAuthClientTestCase(DownloadTestCase, UploadTestCase, MethodTestCase,
                          UrlGenerationTestCase, OAuthTestCase):
    def test_blank_client_token(self):
        self.assertRaises(APIError, self.getClient, client_token='', client_secret='')

    def test_blank_access_token(self):
        client = self.getClient(access_token='', access_secret='')
        self.assertRaises(APIError, client.get, '/ping')


class HTTPThrottleRequestHandler(TestHTTPRequestHandler):
    def respond(self):
        self.send_response(503)
        self.send_header("X-Throttle", "throttled; next=0.01 sec")
        self.end_headers()
        self.wfile.write("Request Throttled!")


class ThrottleTestCase(object):
    def setUp(self):
        self.server = TestHTTPServer(handler=HTTPThrottleRequestHandler)

    def test_throttle_GET(self):
        client = self.getClient()
        self.assertRaises(RequestError, client.get, '/ping')
        self.assertRequestCount(3)


class BasicThrottleTestCase(ThrottleTestCase, BasicTestCase):
    pass


class OAuthThrottleTestCase(ThrottleTestCase, OAuthTestCase):
    pass


class HTTPJSONRequestHandler(TestHTTPRequestHandler):
    def respond(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({ 'foo': 'bar' }))


class JSONTestCase(object):
    def setUp(self):
        self.server = TestHTTPServer(handler=HTTPJSONRequestHandler)

    def test_throttle_GET(self):
        client = self.getClient()
        r = client.get('/user')
        self.assertMethod('GET')
        self.assertEqual(r, { 'foo': 'bar' })


class BasicJSONTestCase(JSONTestCase, BasicTestCase):
    pass


class OAuthJSONTestCase(JSONTestCase, OAuthTestCase):
    pass


# TODO: Test with missing oauthlib...
# Must invoke an ImportError when smartfile tries to import it. Then the test
# case should verify that the correct exception (NotImplementedError) is raised
# when OAuth is used...
#
# http://stackoverflow.com/questions/2481511/mocking-importerror-in-python


if __name__ == '__main__':
    unittest.main()
