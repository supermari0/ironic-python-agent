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

import mock
from oslotest import base as test_base

from ironic_python_agent import errors
from ironic_python_agent.imaging import base
from ironic_python_agent.imaging import vhd_util
from ironic_python_agent.openstack.common import processutils


class TestingException(Exception):
    pass


class TestVHDUtilModule(test_base.BaseTestCase):
    @mock.patch('os.chdir')
    @mock.patch('os.getcwd')
    def test__temporary_chdir(self, getcwd_mock, chdir_mock):
        orig_path = getcwd_mock.return_value
        with vhd_util._temporary_chdir('foo'):
            pass

        getcwd_mock.assert_called_once_with()
        self.assertEqual([mock.call('foo'), mock.call(orig_path)],
                         chdir_mock.call_args_list)

    @mock.patch('os.chdir')
    @mock.patch('os.getcwd')
    def test__temporary_chdir_exc(self, getcwd_mock, chdir_mock):
        orig_path = getcwd_mock.return_value

        def _test_it():
            with vhd_util._temporary_chdir('foo'):
                raise TestingException()

        self.assertRaises(TestingException, _test_it)

        getcwd_mock.assert_called_once_with()
        self.assertEqual([mock.call('foo'), mock.call(orig_path)],
                         chdir_mock.call_args_list)


class TestVHDUtilImageManager(test_base.BaseTestCase):
    def setUp(self):
        super(TestVHDUtilImageManager, self).setUp()
        self.vhdutil_img_mgr = vhd_util.VHDUtilImageManager()

    @mock.patch('ironic_python_agent.utils.execute')
    def test__exec_untar(self, exec_mock):
        exec_mock.return_value = (None, None)
        exp_command = ['tar', '-C', 'tar dir', '-xSf', 'fake location']

        self.vhdutil_img_mgr._exec_untar('fake location', 'tar dir')

        exec_mock.assert_called_once_with(*exp_command,
                                          check_exit_code=[0])

    @mock.patch('ironic_python_agent.utils.execute')
    def test__exec_untar_fails(self, exec_mock):
        exec_mock.side_effect = processutils.ProcessExecutionError()
        exp_command = ['tar', '-C', 'tar dir', '-xSf', 'fake location']

        self.assertRaises(errors.ImageFormatError,
                          self.vhdutil_img_mgr._exec_untar,
                          'fake location',
                          'tar dir')

        exec_mock.assert_called_once_with(*exp_command,
                                          check_exit_code=[0])

    @mock.patch.object(vhd_util.VHDUtilImageManager, '_exec_untar')
    @mock.patch('os.mkdir')
    @mock.patch.object(base.BaseImageManager, '_safe_remove_path')
    @mock.patch.object(base.BaseImageManager, '_download_image')
    def test__untar_image(self, dl_mock, remove_mock, mkdir_mock, untar_mock):
        image_info = 'fake image info'

        @contextlib.contextmanager
        def _dl_side_effect(_data):
            yield 'fake location'

        dl_mock.side_effect = _dl_side_effect
        tardir = 'fake location.tardir'

        with self.vhdutil_img_mgr._untar_image(image_info) as loc:
            self.assertEqual(tardir, loc)
            dl_mock.assert_called_once_with(image_info)
            remove_mock.assert_called_once_with(loc)
            mkdir_mock.assert_called_once_with(loc)
            untar_mock.assert_called_once_with('fake location', loc)

        self.assertEqual([mock.call(tardir), mock.call(tardir)],
                         remove_mock.call_args_list)

    @mock.patch('os.path.exists')
    def test__get_vhds_base_image(self, exists_mock):
        # First exists check for 'image.vhd' succeeds
        exists_mock.return_value = True
        resp = self.vhdutil_img_mgr._get_vhds()
        self.assertEqual(['image.vhd'], resp)
        exists_mock.assert_called_once_with('image.vhd')

    @mock.patch('os.path.exists')
    def test__get_vhds_snapshot(self, exists_mock):
        exp_results = ['0.vhd', '1.vhd', '2.vhd']

        def _exists_side_effect(path):
            return path in exp_results

        exists_mock.side_effect = _exists_side_effect

        resp = self.vhdutil_img_mgr._get_vhds()
        self.assertEqual(exp_results, resp)
        exp_calls = [mock.call('image.vhd')]
        for vhd in exp_results + ['3.vhd']:
            exp_calls.append(mock.call(vhd))
        self.assertEqual(exp_calls, exists_mock.call_args_list)

    @mock.patch('ironic_python_agent.utils.execute')
    def test__link_vhds_one_vhd(self, exec_mock):
        self.vhdutil_img_mgr._link_vhds(['image.vhd'])
        self.assertFalse(exec_mock.called)

    @mock.patch('ironic_python_agent.utils.execute')
    def test__link_vhds(self, exec_mock):
        exec_mock.return_value = (None, None)
        vhds = ['0.vhd', '1.vhd', '2.vhd']

        self.vhdutil_img_mgr._link_vhds(vhds)

        cmds = [
            [vhd_util.VHD_UTIL, 'modify', '-n', '1.vhd', '-p', '2.vhd'],
            [vhd_util.VHD_UTIL, 'modify', '-n', '0.vhd', '-p', '1.vhd']
        ]

        exp_calls = [mock.call(*cmd, check_exit_code=[0]) for cmd in cmds]
        self.assertEqual(exp_calls, exec_mock.call_args_list)

    @mock.patch('ironic_python_agent.utils.execute')
    def test__link_vhds_failure(self, exec_mock):
        exec_mock.side_effect = processutils.ProcessExecutionError()
        vhds = ['0.vhd', '1.vhd', '2.vhd']

        self.assertRaises(errors.ImageFormatError,
                          self.vhdutil_img_mgr._link_vhds,
                          vhds)

    @mock.patch('ironic_python_agent.utils.execute')
    @mock.patch.object(vhd_util.VHDUtilImageManager, '_link_vhds')
    def test__write_vhds(self, link_mock, exec_mock):
        exec_mock.return_value = (None, None)
        device = 'fake device'
        vhds = ['0.vhd', '1.vhd', '2.vhd']

        self.vhdutil_img_mgr._write_vhds(vhds, device)

        link_mock.assert_called_once_with(vhds)
        cmd = [vhd_util.VHD_UTIL, 'vhd2raw', '-d', '-b', '65536',
               '0.vhd', device]
        exec_mock.assert_called_once_with(*cmd, check_exit_code=[0])

    @mock.patch('ironic_python_agent.utils.execute')
    @mock.patch.object(vhd_util.VHDUtilImageManager, '_link_vhds')
    def test__write_vhds_failure(self, link_mock, exec_mock):
        exec_mock.side_effect = processutils.ProcessExecutionError()
        device = 'fake device'
        vhds = ['0.vhd', '1.vhd', '2.vhd']

        self.assertRaises(errors.ImageWriteError,
                          self.vhdutil_img_mgr._write_vhds,
                          vhds,
                          device)

        link_mock.assert_called_once_with(vhds)
        cmd = [vhd_util.VHD_UTIL, 'vhd2raw', '-d', '-b', '65536',
               '0.vhd', device]
        exec_mock.assert_called_once_with(*cmd, check_exit_code=[0])

    @mock.patch.object(vhd_util.VHDUtilImageManager, '_write_vhds')
    @mock.patch.object(vhd_util.VHDUtilImageManager, '_get_vhds')
    @mock.patch.object(vhd_util, '_temporary_chdir')
    @mock.patch.object(vhd_util.VHDUtilImageManager, '_untar_image')
    def test_write_os_image(self, untar_mock, chdir_mock, get_mock,
                            write_mock):
        image_info = 'fake image info'
        device = 'fake device'

        @contextlib.contextmanager
        def _untar_side_effect(_image_info):
            yield 'tar dir'

        @contextlib.contextmanager
        def _chdir_side_effect(_image_info):
            yield

        vhds = ['0.vhd', '1.vhd']

        untar_mock.side_effect = _untar_side_effect
        chdir_mock.side_effect = _chdir_side_effect
        get_mock.return_value = vhds

        self.vhdutil_img_mgr.write_os_image(image_info, device)

        untar_mock.assert_called_once_with(image_info)
        chdir_mock.assert_called_once_with('tar dir')
        get_mock.assert_called_once_with()
        write_mock.assert_called_once_with(vhds, device)

    @mock.patch.object(vhd_util.VHDUtilImageManager, '_write_vhds')
    @mock.patch.object(vhd_util.VHDUtilImageManager, '_get_vhds')
    @mock.patch.object(vhd_util, '_temporary_chdir')
    @mock.patch.object(vhd_util.VHDUtilImageManager, '_untar_image')
    def test_write_os_image_no_vhds(self, untar_mock, chdir_mock, get_mock,
                                    write_mock):
        image_info = 'fake image info'
        device = 'fake device'

        @contextlib.contextmanager
        def _untar_side_effect(_image_info):
            yield 'tar dir'

        @contextlib.contextmanager
        def _chdir_side_effect(_image_info):
            yield

        vhds = []

        untar_mock.side_effect = _untar_side_effect
        chdir_mock.side_effect = _chdir_side_effect
        get_mock.return_value = vhds

        self.assertRaises(errors.ImageFormatError,
                          self.vhdutil_img_mgr.write_os_image,
                          image_info,
                          device)

        untar_mock.assert_called_once_with(image_info)
        chdir_mock.assert_called_once_with('tar dir')
        get_mock.assert_called_once_with()
        self.assertFalse(write_mock.called)
