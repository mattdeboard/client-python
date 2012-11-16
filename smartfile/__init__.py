import os
import requests
import time

from os.path import basename
from os.path import dirname

from smartfile.decorators import response_processor


class _BaseAPI(object):
    """ Base class for specific API endpoints (i.e., user, path). """
    _baseurl = 'http://localhost:8000/api/2/'

    def __init__(self, api_key=None, api_pass=None, session=None, **kwargs):
        # Re-use existing session if provided.
        self._session = session or requests.session(
            auth=self._get_auth(api_key, api_pass))

    def _get_auth(self, api_key, api_pass):
        """ Get API key and password. """
        if api_key is None and api_pass is None:
            # Pull the API key and password from the environment.
            try:
                api_key = os.environ['SMARTFILE_API_KEY']
                api_pass = os.environ['SMARTFILE_API_PASS']
            except KeyError:
                raise Exception(
                    'Set key/password (SMARTFILE_API_KEY, SMARTFILE_API_PASS) in environment')

        return api_key, api_pass

    def _gen_url(self, uri_args=(), baseurl=None):
        """ Join segments onto URL to call API. """
        # Generate list of path components from URI template and provided
        # arguments.  'None' in the template is replaced with a path if there
        # is one provided by the caller.
        #
        # NOTE:  uri_iter raises StopIteration if it runs out of elements.
        # This is caught by the generator which stops before all the elements
        # in self._api_url are used.
        uri_iter = iter(uri_args)
        paths = (next(uri_iter) if x is None else x for x in self._api_uri)

        # Concatenate the path components without '//'.
        url = baseurl or self._baseurl
        for arg in paths:
            if isinstance(arg, basestring) and arg.startswith('/'):
                arg = arg[1:]
            if arg != '/':
                sep = '' if url.endswith('/') else '/'
                url = '{0}{1}{2}'.format(url, sep, arg)

        return url

    @response_processor
    def _create(self, data=None, *args, **kwargs):
        """ The C in CRUD. """
        url = self._gen_url(args, baseurl=kwargs.pop('baseurl', None))
        return self._session.post(url, data=data, **kwargs)

    @response_processor
    def _read(self, *args, **kwargs):
        """ The R in CRUD. """
        url = self._gen_url(args, baseurl=kwargs.pop('baseurl', None))
        return self._session.get(url, **kwargs)

    @response_processor
    def _update(self, data=None, *args, **kwargs):
        """ The U in CRUD. """
        url = self._gen_url(args, baseurl=kwargs.pop('baseurl', None))
        if data is not None:
            kwargs['data'] = data
        return self._session.post(url, **kwargs)

    @response_processor
    def _delete(self, *args, **kwargs):
        """ The D in CRUD. """
        url = self._gen_url(args, baseurl=kwargs.pop('baseurl', None))
        return self._session.delete(url, **kwargs)


class UserAPI(_BaseAPI):
    """ User API. """
    _api_uri = ('user/', None, '/')

    @property
    def create(self):
        return self._create

    @property
    def read(self):
        return self._read

    @property
    def update(self):
        return self._update

    @property
    def delete(self):
        return self._delete


class PathOperAPI(_BaseAPI):
    """ Path Oper API. """
    _api_uri = ('path/oper/', None, None, None, '/')

    def remove(self, path):
        """ Create task to remove file system object(s). """
        return super(PathOperAPI, self)._create({'path': path}, 'remove/')

    def poll(self, url, checks=5, check_timeout=2):
        """
        Poll a URL until a non-200 response or the result of operation is
        SUCCESS.  Check a few times with a sleep between each check.
        """
        while checks > 0:
            response = self._session.get(url)
            if (response.status_code != 200 or
                response.json['result']['status'] == 'SUCCESS'):
                break
            checks -= 1
            time.sleep(check_timeout)

        return response


class PathTreeAPI(_BaseAPI):
    """ Path Tree API. """
    _api_uri = ('path/tree/', None)

    def read(self, path='/', children=False, *args, **kwargs):
        if children:
            kwargs['params'] = {'children': True}
        return super(PathTreeAPI, self)._read(path, *args, **kwargs)


class PathDataAPI(_BaseAPI):
    """ Path Data API. """
    _api_uri = ('path/', None, 'data/')

    @property
    def create(self):
        return self._create

    @property
    def read(self):
        return self._read


class PathAPI(_BaseAPI):
    """ Path API. """
    _api_uri = ('path/', None, '/')

    def __init__(self, *args, **kwargs):
        super(PathAPI, self).__init__(*args, **kwargs)
        kwargs['session'] = self._session
        self._path_data_api = PathDataAPI(*args, **kwargs)
        self._path_oper_api = PathOperAPI(*args, **kwargs)
        self._path_tree_api = PathTreeAPI(*args, **kwargs)

    @property
    def read(self):
        """ Shortcut to Path Tree API read(). """
        return self._path_tree_api.read

    def remove(self, path):
        """ Remove the file and poll awhile for it to finish. """
        response = self._path_oper_api.remove(path)
        if response.status_code == 200:
            response = self._path_oper_api.poll(response.json['url'])
        return response

    def download(self, dst, src):
        # Get file ID and download and save file in chunks.
        tree = self.read(src)
        response = self._path_data_api.read(tree.json['id'])
        if response.status_code == 200:
            with open(dst, 'wb') as dst_file:
                for chunk in response.iter_content(16 * 1024):
                    dst_file.write(chunk)

        return response

    def upload(self, dst, src):
        # Get directory ID.
        dst_dir = dirname(dst)
        tree = self._path_tree_api.read(dst_dir)

        # Upload file.
        files = {'file': (basename(dst), open(src, 'rb'))}
        return self._path_data_api.create(None, tree.json['id'], files=files)

        return super(PathAPI, self)._create(
            None, self._api_uri_ext, baseurl=tree.json['url'], files=files)


class RoleAPI(_BaseAPI):
    """ Role API. """
    _api_uri = ('role/', None, '/')

    @property
    def create(self):
        return self._create

    @property
    def read(self):
        return self._read

    @property
    def update(self):
        return self._update

    @property
    def delete(self):
        return self._delete


class API(object):
    """
    This class provides a single interface to the various segments of the
    SmartFile API.
    """
    def __init__(self, api_key=None, api_pass=None):
        # Create a session to be shared by all endpoints.
        base = _BaseAPI(api_key, api_pass)
        self._session = base._session

    def _get_api(self, attr, cls):
        """ Return the API endpoint.  Instantiate it if needed. """
        api = getattr(self, attr, None)
        if api is None:
            api = cls(None, None, session=self._session)
            setattr(self, attr, api)
        return api

    @property
    def path(self):
        return self._get_api('_api_path_obj', PathAPI)

    @property
    def path_oper(self):
        return self._get_api('_api_path_oper_obj', PathOperAPI)

    @property
    def path_tree(self):
        return self._get_api('_api_path_tree_obj', PathTreeAPI)

    @property
    def role(self):
        return self._get_api('_api_role_obj', RoleAPI)

    @property
    def user(self):
        return self._get_api('_api_user_obj', UserAPI)