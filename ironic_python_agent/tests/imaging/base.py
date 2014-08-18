# Copyright 2013-2014 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import md5

import mock
from oslotest import base as test_base
import six

from ironic_python_agent import errors
from ironic_python_agent import imaging
from ironic_python_agent.imaging import base
from ironic_python_agent.imaging import qemu_img
from ironic_python_agent.openstack.common import processutils


if six.PY2:
    OPEN_FUNCTION_NAME = '__builtin__.open'
else:
    OPEN_FUNCTION_NAME = 'builtins.open'


class TestingException(Exception):
    pass


class TestImagingInitModule(test_base.BaseTestCase):
    def test_get_image_manager(self):
        disk_formats = [None, 'qcow2', 'unknown']
        for disk_format in disk_formats:
            res = imaging.get_image_manager(disk_format, None)
            self.assertTrue(isinstance(res, qemu_img.QemuImgImageManager))


class TestBaseImageManager(test_base.BaseTestCase):
    def setUp(self):
        super(TestBaseImageManager, self).setUp()
        self.base_img_mgr = base.BaseImageManager()

    def _build_fake_image_info(self):
        return {'id': 'fake_id',
                'urls': ['url1', 'url2']}

    def test_tmpdir_on_init(self):
        self.assertEqual('/tmp', self.base_img_mgr.tmpdir)
        new_base = base.BaseImageManager(tmpdir='/foo')
        self.assertEqual('/foo', new_base.tmpdir)

    def test__image_location(self):
        image_info = self._build_fake_image_info()
        location = self.base_img_mgr._image_location(image_info)
        self.assertEqual('/tmp/fake_id', location)

    def test__image_location_alt_tmpdir(self):
        self.base_img_mgr.tmpdir = '/foo'
        image_info = self._build_fake_image_info()
        location = self.base_img_mgr._image_location(image_info)
        self.assertEqual('/foo/fake_id', location)

    def test__configdrive_location(self):
        location = self.base_img_mgr._configdrive_location()
        self.assertEqual('/tmp/configdrive', location)

    def test__configdrive_location_alt_tmpdir(self):
        self.base_img_mgr.tmpdir = '/foo'
        location = self.base_img_mgr._configdrive_location()
        self.assertEqual('/foo/configdrive', location)

    def test__path_to_script(self):
        path = self.base_img_mgr._path_to_script('../myscript.sh')
        self.assertTrue(path.endswith(
            'ironic_python_agent/imaging/../../myscript.sh'))

    @mock.patch('requests.get')
    def test__request_url(self, get_mock):
        image_info = self._build_fake_image_info()
        url = 'fake_url'
        get_mock.return_value.status_code = 200

        res = self.base_img_mgr._request_url(image_info, url)
        self.assertEqual(get_mock.return_value, res)
        get_mock.assert_called_once_with(url, stream=True)

    @mock.patch('requests.get')
    def test__request_url_non_200(self, get_mock):
        image_info = self._build_fake_image_info()
        url = 'fake_url'
        get_mock.return_value.status_code = 404

        self.assertRaises(errors.ImageDownloadError,
                          self.base_img_mgr._request_url,
                          image_info,
                          url)

    @mock.patch.object(base.BaseImageManager, '_request_url')
    def test__fetch_image(self, req_mock):
        image_info = self._build_fake_image_info()
        resp_mock = req_mock.return_value
        resp_mock.iter_content.return_value = ['some', 'content']
        image_info['checksum'] = md5.new('somecontent').hexdigest()
        read_cb = mock.Mock()

        self.base_img_mgr._fetch_image(image_info, read_cb)

        req_mock.assert_called_once_with(image_info, 'url1')
        self.assertEqual([mock.call('some'), mock.call('content')],
                         read_cb.call_args_list)

    @mock.patch.object(base.BaseImageManager, '_request_url')
    def test__fetch_image_bad_checksum(self, req_mock):
        image_info = self._build_fake_image_info()
        resp_mock = req_mock.return_value
        resp_mock.iter_content.return_value = ['some', 'content']
        image_info['checksum'] = None
        read_cb = mock.Mock()

        self.assertRaises(errors.ImageChecksumError,
                          self.base_img_mgr._fetch_image,
                          image_info,
                          read_cb)
        req_mock.assert_called_once_with(image_info, 'url1')

    @mock.patch.object(base.BaseImageManager, '_request_url')
    def test__fetch_image_first_url_fail(self, req_mock):
        image_info = self._build_fake_image_info()

        resp_mock = mock.Mock()
        resp_mock.iter_content.return_value = ['some', 'content']
        image_info['checksum'] = md5.new('somecontent').hexdigest()

        def _request_url_side_effect(_image_info, url):
            if url == 'url1':
                raise errors.ImageDownloadError('id', 'whatever')
            return resp_mock

        req_mock.side_effect = _request_url_side_effect
        read_cb = mock.Mock()

        self.base_img_mgr._fetch_image(image_info, read_cb)

        self.assertEqual([mock.call(image_info, 'url1'),
                          mock.call(image_info, 'url2')],
                         req_mock.call_args_list)
        self.assertEqual([mock.call('some'), mock.call('content')],
                         read_cb.call_args_list)

    @mock.patch.object(base.BaseImageManager, '_request_url')
    def test__fetch_image_all_urls_fail(self, req_mock):
        image_info = self._build_fake_image_info()
        req_mock.side_effect = errors.ImageDownloadError('id', 'whatever')
        read_cb = mock.Mock()

        self.assertRaises(errors.ImageDownloadError,
                          self.base_img_mgr._fetch_image,
                          image_info,
                          read_cb)
        self.assertEqual([mock.call(image_info, 'url1'),
                          mock.call(image_info, 'url2')],
                         req_mock.call_args_list)

    @mock.patch('shutil.rmtree')
    def test__safe_remove_path(self, rmtree_mock):
        self.base_img_mgr._safe_remove_path('fake_path')
        rmtree_mock.assert_called_once_with('fake_path', ignore_errors=True)

    @mock.patch.object(base.BaseImageManager, '_safe_remove_path')
    @mock.patch.object(base.BaseImageManager, '_fetch_image')
    @mock.patch.object(base.BaseImageManager, '_image_location')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test__download_image(self, open_mock, loc_mock, fetch_mock,
                             remove_mock):
        file_mock = mock.Mock()

        @contextlib.contextmanager
        def _open_side_effect(_fn, _mode):
            yield file_mock

        open_mock.side_effect = _open_side_effect

        with self.base_img_mgr._download_image('image_info') as loc:
            self.assertEqual(loc_mock.return_value, loc)
            open_mock.assert_called_once_with(loc, 'w')
            fetch_mock.assert_called_once_with('image_info',
                                               file_mock.write)
            self.assertFalse(remove_mock.called)

        remove_mock.assert_called_once_with(loc)

    @mock.patch.object(base.BaseImageManager, '_safe_remove_path')
    @mock.patch.object(base.BaseImageManager, '_fetch_image')
    @mock.patch.object(base.BaseImageManager, '_image_location')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test__download_image_fetch_fail(self, open_mock, loc_mock,
                                        fetch_mock, remove_mock):
        file_mock = mock.Mock()

        @contextlib.contextmanager
        def _open_side_effect(_fn, _mode):
            yield file_mock

        open_mock.side_effect = _open_side_effect
        fetch_mock.side_effect = TestingException()

        def _test_it():
            with self.base_img_mgr._download_image('image_info'):
                pass

        self.assertRaises(TestingException, _test_it)

        loc = loc_mock.return_value
        open_mock.assert_called_once_with(loc, 'w')
        fetch_mock.assert_called_once_with('image_info',
                                           file_mock.write)
        remove_mock.assert_called_once_with(loc)

    @mock.patch.object(base.BaseImageManager, '_safe_remove_path')
    @mock.patch.object(base.BaseImageManager, '_fetch_image')
    @mock.patch.object(base.BaseImageManager, '_image_location')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test__download_image_error_while_yielded(self, open_mock, loc_mock,
                                                 fetch_mock, remove_mock):
        file_mock = mock.Mock()

        @contextlib.contextmanager
        def _open_side_effect(_fn, _mode):
            yield file_mock

        open_mock.side_effect = _open_side_effect
        fetch_mock.side_effect = TestingException()

        def _test_it():
            with self.base_img_mgr._download_image('image_info') as loc:
                self.assertEqual(loc_mock.return_value, loc)
                open_mock.assert_called_once_with(loc, 'w')
                fetch_mock.assert_called_once_with('image_info',
                                                   file_mock.write)
                self.assertFalse(remove_mock.called)
                raise TestingException()

        self.assertRaises(TestingException, _test_it)
        remove_mock.assert_called_once_with(loc_mock.return_value)

    @mock.patch.object(base.BaseImageManager, '_safe_remove_path')
    @mock.patch('os.stat')
    @mock.patch('base64.b64decode')
    @mock.patch('gzip.GzipFile')
    @mock.patch('StringIO.StringIO')
    @mock.patch.object(base.BaseImageManager, '_configdrive_location')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test__unpack_configdrive(self, open_mock, loc_mock, stringio_mock,
                                 gzip_mock, b64_mock, stat_mock, remove_mock):
        cd_data = 'fake base64 encoded data'
        file_mock = mock.Mock()
        stat_mock.return_value.st_size = 64 * 1024 * 1024
        gzread_mock = gzip_mock.return_value.read
        gzclose_mock = gzip_mock.return_value.close

        @contextlib.contextmanager
        def _open_side_effect(_fn, _mode):
            yield file_mock

        open_mock.side_effect = _open_side_effect

        with self.base_img_mgr._unpack_configdrive(cd_data) as loc:
            self.assertEqual(loc_mock.return_value, loc)
            b64_mock.assert_called_once_with(cd_data)
            stringio_mock.assert_called_once_with(b64_mock.return_value)
            gzip_mock.assert_called_once_with('configdrive', 'rb', 9,
                                              stringio_mock.return_value)
            open_mock.assert_called_once_with(loc, 'wb')
            file_mock.write.assert_called_once_with(gzread_mock.return_value)
            gzclose_mock.assert_called_once_with()
            stat_mock.assert_called_once_with(loc)
            self.assertFalse(remove_mock.called)

        remove_mock.assert_called_once_with(loc_mock.return_value)
        # Make sure still only called once
        gzclose_mock.assert_called_once_with()

    @mock.patch.object(base.BaseImageManager, '_safe_remove_path')
    @mock.patch('os.stat')
    @mock.patch('base64.b64decode')
    @mock.patch('gzip.GzipFile')
    @mock.patch('StringIO.StringIO')
    @mock.patch.object(base.BaseImageManager, '_configdrive_location')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test__unpack_configdrive_gzip_read_fail(self, open_mock, loc_mock,
                                                stringio_mock, gzip_mock,
                                                b64_mock, stat_mock,
                                                remove_mock):
        cd_data = 'fake base64 encoded data'
        file_mock = mock.Mock()
        gzread_mock = gzip_mock.return_value.read
        gzread_mock.side_effect = TestingException()

        @contextlib.contextmanager
        def _open_side_effect(_fn, _mode):
            yield file_mock

        open_mock.side_effect = _open_side_effect

        def _test_it():
            with self.base_img_mgr._unpack_configdrive(cd_data):
                pass

        self.assertRaises(TestingException, _test_it)
        remove_mock.assert_called_once_with(loc_mock.return_value)
        gzclose_mock = gzip_mock.return_value.close
        gzclose_mock.assert_called_once_with()
        self.assertFalse(stat_mock.called)

    @mock.patch.object(base.BaseImageManager, '_safe_remove_path')
    @mock.patch('os.stat')
    @mock.patch('base64.b64decode')
    @mock.patch('gzip.GzipFile')
    @mock.patch('StringIO.StringIO')
    @mock.patch.object(base.BaseImageManager, '_configdrive_location')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test__unpack_configdrive_too_large(self, open_mock, loc_mock,
                                           stringio_mock, gzip_mock,
                                           b64_mock, stat_mock, remove_mock):
        cd_data = 'fake base64 encoded data'
        file_mock = mock.Mock()
        stat_mock.return_value.st_size = 64 * 1024 * 1024 + 1

        @contextlib.contextmanager
        def _open_side_effect(_fn, _mode):
            yield file_mock

        open_mock.side_effect = _open_side_effect

        def _test_it():
            with self.base_img_mgr._unpack_configdrive(cd_data):
                pass

        self.assertRaises(errors.ConfigDriveTooLargeError, _test_it)
        remove_mock.assert_called_once_with(loc_mock.return_value)

    @mock.patch.object(base.BaseImageManager, '_safe_remove_path')
    @mock.patch('os.stat')
    @mock.patch('base64.b64decode')
    @mock.patch('gzip.GzipFile')
    @mock.patch('StringIO.StringIO')
    @mock.patch.object(base.BaseImageManager, '_configdrive_location')
    @mock.patch(OPEN_FUNCTION_NAME)
    def test__unpack_configdrive_fail_while_yielded(
            self, open_mock, loc_mock, stringio_mock, gzip_mock,
            b64_mock, stat_mock, remove_mock):
        cd_data = 'fake base64 encoded data'
        file_mock = mock.Mock()
        stat_mock.return_value.st_size = 64 * 1024 * 1024
        gzclose_mock = gzip_mock.return_value.close

        @contextlib.contextmanager
        def _open_side_effect(_fn, _mode):
            yield file_mock

        open_mock.side_effect = _open_side_effect

        def _test_it():
            with self.base_img_mgr._unpack_configdrive(cd_data) as loc:
                self.assertEqual(loc_mock.return_value, loc)
                raise TestingException()

        self.assertRaises(TestingException, _test_it)
        remove_mock.assert_called_once_with(loc_mock.return_value)
        gzclose_mock.assert_called_once_with()

    @mock.patch('ironic_python_agent.utils.execute')
    @mock.patch.object(base.BaseImageManager, '_path_to_script')
    @mock.patch.object(base.BaseImageManager, '_unpack_configdrive')
    def test_write_configdrive(self, unpack_mock, path_mock, exec_mock):
        cd_data = 'fake base64 encoded data'
        device = 'device'
        path_mock.return_value = 'fake path'
        exec_mock.return_value = (None, None)

        @contextlib.contextmanager
        def _unpack_side_effect(_data):
            yield 'fake location'

        unpack_mock.side_effect = _unpack_side_effect

        exp_command = ['/bin/bash', 'fake path',
                       'fake location', device]

        self.base_img_mgr.write_configdrive(cd_data, device)

        unpack_mock.assert_called_once_with(cd_data)
        path_mock.assert_called_once_with(
                'shell/copy_configdrive_to_disk.sh')
        exec_mock.assert_called_once_with(*exp_command,
                                          check_exit_code=[0])

    @mock.patch('ironic_python_agent.utils.execute')
    @mock.patch.object(base.BaseImageManager, '_path_to_script')
    @mock.patch.object(base.BaseImageManager, '_unpack_configdrive')
    def test_write_configdrive_exec_fail(self, unpack_mock, path_mock,
                                         exec_mock):
        cd_data = 'fake base64 encoded data'
        device = 'device'
        path_mock.return_value = 'fake path'
        exec_mock.side_effect = processutils.ProcessExecutionError()

        @contextlib.contextmanager
        def _unpack_side_effect(_data):
            yield 'fake location'

        unpack_mock.side_effect = _unpack_side_effect

        exp_command = ['/bin/bash', 'fake path',
                       'fake location', device]

        self.assertRaises(
                errors.ConfigDriveWriteError,
                self.base_img_mgr.write_configdrive,
                cd_data,
                device)

        unpack_mock.assert_called_once_with(cd_data)
        path_mock.assert_called_once_with(
                'shell/copy_configdrive_to_disk.sh')
        exec_mock.assert_called_once_with(*exp_command,
                                          check_exit_code=[0])
